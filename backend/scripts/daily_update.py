"""
日次データ更新スクリプト
アクティブ投資対象の価格 (market_price_observation) を更新する。

使い方:
    python backend/scripts/daily_update.py
"""
import sys
from datetime import date, timedelta
from pathlib import Path

import yfinance as yf

sys.path.insert(0, str(Path(__file__).parent.parent))
from app.config import settings
from app.database import Connection, connect_database
from app.etl.loaders import ensure_data_source
from app.etl.runtime import build_jquants_pipeline


def partition_targets_by_price_source(
    investment_targets: list[tuple[int, str, str, str | None]],
    *,
    jquants_enabled: bool,
) -> tuple[list[str], list[tuple[int, str, str]]]:
    """J-Quants対応銘柄とyfinance対象銘柄を重複なく分ける。"""
    if not jquants_enabled:
        return [], [
            (target_id, target_key, target_name)
            for target_id, target_key, target_name, _ in investment_targets
        ]
    return (
        [jpx_code for _, _, _, jpx_code in investment_targets if jpx_code],
        [
            (target_id, target_key, target_name)
            for target_id, target_key, target_name, jpx_code in investment_targets
            if not jpx_code
        ],
    )


DEFAULT_LOOKBACK_DAYS = 7
REFETCH_OVERLAP_DAYS = 3


def resolve_fetch_start(
    conn: Connection,
    target_id: int,
    source_id: int,
    *,
    today: date,
    overlap_days: int = REFETCH_OVERLAP_DAYS,
    default_lookback_days: int = DEFAULT_LOOKBACK_DAYS,
) -> date:
    """銘柄・取得元ごとの最終観測日から、再取得の開始日を決める。

    固定窓では実行が飛んだ期間の穴が埋まらないため、最終観測日を起点にする。
    直近数日は訂正や確定遅れがあるため `overlap_days` だけ遡って取り直す。
    その取得元での観測がまだ無い銘柄は既定の遡及日数しか遡らない。取得元ごとの初期投入は
    日次更新ではなくバックフィルの役割とし、ここで長期間を取りにいかない。
    """
    row = conn.execute(
        "SELECT max(obs_date) AS latest_obs_date FROM market_price_observation "
        "WHERE target_id = ? AND source_id = ?",
        (target_id, source_id),
    ).fetchone()
    if not row or not row["latest_obs_date"]:
        print(
            f"  ! target_id={target_id} はこの取得元での観測が無いため直近{default_lookback_days}日のみ取得します"
            "（過去分が必要ならバックフィルを実行してください）"
        )
        return today - timedelta(days=default_lookback_days)
    latest = row["latest_obs_date"]
    return (latest if isinstance(latest, date) else date.fromisoformat(str(latest))) - timedelta(
        days=overlap_days
    )


def upsert_price_frame(conn: Connection, target_id: int, source_id: int, frame) -> int:
    """yfinanceの取得結果を1行も捨てずにUPSERTし、保存した行数を返す。"""
    saved = 0
    for index, row in frame.iterrows():
        conn.execute(
            """
            INSERT INTO market_price_observation (
                target_id, source_id, obs_date, open_price, high_price,
                low_price, close_price, volume, price_basis, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'adjusted', CURRENT_TIMESTAMP)
            ON CONFLICT(target_id, source_id, obs_date) DO UPDATE SET
                open_price = excluded.open_price,
                high_price = excluded.high_price,
                low_price = excluded.low_price,
                close_price = excluded.close_price,
                volume = excluded.volume,
                price_basis = excluded.price_basis,
                fetched_at = excluded.fetched_at
            """,
            (
                target_id,
                source_id,
                index.strftime("%Y-%m-%d"),
                float(row["Open"]),
                float(row["High"]),
                float(row["Low"]),
                float(row["Close"]),
                float(row["Volume"]) if "Volume" in frame.columns else None,
            ),
        )
        saved += 1
    return saved


def update_investment_target_prices() -> None:
    conn = connect_database(read_only=False)
    cursor = conn.cursor()
    yfinance_source_id = ensure_data_source(
        conn,
        "yfinance",
        "Yahoo Finance via yfinance",
    )

    cursor.execute("""
        SELECT a.target_id, a.target_key, a.target_name,
               (
                   SELECT ai.identifier
                   FROM investment_target_identifier ai
                   JOIN data_source ds ON ds.source_id = ai.source_id
                   WHERE ai.target_id = a.target_id
                     AND ds.source_key = 'jquants'
                     AND ai.identifier_type = 'jpx_code'
                     AND ai.is_primary = TRUE
                     AND ai.valid_from <= CURRENT_DATE
                     AND (ai.valid_to IS NULL OR ai.valid_to >= CURRENT_DATE)
                   ORDER BY ai.valid_from DESC
                   LIMIT 1
               ) AS jpx_code
        FROM investment_target a
        WHERE a.is_active = TRUE
        ORDER BY a.target_id
    """)
    investment_targets = [
        (
            int(row["target_id"]),
            str(row["target_key"]),
            str(row["target_name"]),
            str(row["jpx_code"]) if row["jpx_code"] is not None else None,
        )
        for row in cursor.fetchall()
    ]

    # 対応(jpx_code)があっても、日次取得に使うかは設定で明示する。プランの提供期間外だと
    # J-Quants経路へ振り分けた銘柄がどこからも取得できなくなるため。
    jquants_daily = bool(settings.jquants_api_key) and settings.jquants_daily_enabled
    jquants_codes, yfinance_targets = partition_targets_by_price_source(
        investment_targets, jquants_enabled=jquants_daily
    )

    if settings.jquants_api_key and not settings.jquants_daily_enabled:
        print("J-Quantsの日次取得は無効（JQUANTS_DAILY_ENABLED=false）。yfinanceで取得します")

    if jquants_daily:
        if jquants_codes:
            jquants_source_id = ensure_data_source(conn, "jquants", "J-Quants")
            # 対象銘柄で最も古い開始日に合わせ、実行が飛んだ期間の穴も埋める。
            start = min(
                resolve_fetch_start(conn, target_id, jquants_source_id, today=date.today())
                for target_id, _, _, jpx_code in investment_targets
                if jpx_code
            )
            try:
                result = build_jquants_pipeline(conn).sync_prices(
                    codes=jquants_codes,
                    date_from=start.strftime("%Y-%m-%d"),
                    date_to=date.today().strftime("%Y-%m-%d"),
                )
                print(f"J-Quants価格更新: {result}")
            except Exception as exc:
                conn.rollback()
                print(f"J-Quants価格更新に失敗: {exc}")
        if not jquants_codes:
            print("J-Quantsの日次取得は有効だが、jpx_codeの対応がある有効銘柄がありません")
    print(f"\n=== yfinance対象銘柄の価格取得 ({len(yfinance_targets)}件) ===\n")

    success = error = 0
    today = date.today()
    for target_id, target_key, target_name in yfinance_targets:
        try:
            start = resolve_fetch_start(conn, target_id, yfinance_source_id, today=today)
            df = yf.Ticker(target_key).history(
                start=start, end=today + timedelta(days=1), auto_adjust=True
            )
            if df.empty:
                print(f"  - {target_name}: {start} 以降の取得結果なし")
                error += 1
                continue

            saved = upsert_price_frame(conn, target_id, yfinance_source_id, df)
            latest = df.index[-1].strftime("%Y-%m-%d")
            print(f"  ✓ {target_name} [{start}〜{latest}] {saved}件 C:{float(df['Close'].iloc[-1]):.2f}")
            success += 1

        except Exception as e:
            print(f"  ✗ {target_name}: {e}")
            error += 1

    conn.commit()
    conn.close()
    print(f"\n完了: 成功={success} 失敗={error}")


if __name__ == "__main__":
    print("=" * 60)
    print("投資監視システム - 日次データ更新")
    print("=" * 60)

    print("\n=== アクティブ投資対象の価格取得 ===")
    update_investment_target_prices()

    print("\n" + "=" * 60 + "\nデータ更新完了\n" + "=" * 60)
