"""公開デモ用のsyntheticデータを生成してPostgreSQLへ投入する。

**なぜ実データを公開しないか。** 個人向けJ-Quants APIは、取得データの第三者提供や、
そのデータを利用したアプリの提供を営利・非営利を問わず禁じている。したがって公開デモが
参照するDBには、J-Quants由来の値を1件も置かない。実データは非公開環境にのみ蓄積する。

生成するのは架空企業3社・架空テーマ3件と、その株価・決算開示・会社予想である。
実データと違い、系列を意図して作れるため、予想の上方修正が株価に先行する、という
将来のAssessment層で扱いたい構図をデモ上で再現している。

デモDBに保持すべき状態は無いため、実行のたびに全テーブルを作り直す。差分移行は行わない。

使い方:
    python backend/scripts/seed_demo.py --database-url postgresql://... --replace
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import random
import sys
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import Connection, connect_database
from db.postgres_migrations import upgrade_database

# 実データと取り違えないよう、取得元も明示的に架空とする。
DEMO_SOURCE_KEY = "demo"

# 投入を許可するデータベース名。**このスクリプトに本番を操作する正当な用途は無い**ため、
# 一致しない接続先はオプションを問わず拒否する。警告や--forceで守るのではなく、
# 本番へ到達できない構造にする。本番Neonは `neondb`、ローカル開発は `invest` であり、
# どちらもこの集合に含めない。
DEMO_DATABASE_NAMES = frozenset({"invest_monitoring_demo", "invest_demo"})

# 生成を再現可能にする。
RANDOM_SEED = 20260923

TODAY = date(2026, 9, 18)

# 業績予想の修正を起こす会計年度。実績もこの年度だけ改訂後の水準で着地する。
REVISION_FISCAL_YEAR = 2026
PRICE_DAYS = 500

TRUNCATE_ORDER = (
    "financial_summary",
    "financial_disclosure",
    "market_price_observation",
    "theme_investment_target",
    "investment_target_identifier",
    "ingestion_error",
    "ingestion_run",
    "investment_target",
    "theme",
    "strategy",
    "data_source",
)


class Company:
    """架空企業1社ぶんの生成条件。

    `drift` は株価の基調、`revision` は通期予想を期中に何倍へ見直すかを表す。
    revision > 1.0 の企業は上方修正、< 1.0 は下方修正として系列を作る。
    """

    def __init__(
        self,
        key: str,
        name: str,
        base_price: float,
        drift: float,
        volatility: float,
        base_revenue: int,
        operating_margin: float,
        revision: float,
        shares: int,
    ):
        self.key = key
        self.name = name
        self.base_price = base_price
        self.drift = drift
        self.volatility = volatility
        self.base_revenue = base_revenue
        self.operating_margin = operating_margin
        self.revision = revision
        self.shares = shares


COMPANIES = [
    Company(
        key="ALPHA.DEMO",
        name="Alpha Semiconductor",
        base_price=4200.0,
        drift=0.0011,
        volatility=0.021,
        base_revenue=820_000_000_000,
        operating_margin=0.18,
        revision=1.16,  # AIデータセンター需要で期中に上方修正する想定
        shares=310_000_000,
    ),
    Company(
        key="BETA.DEMO",
        name="Beta Robotics",
        base_price=2650.0,
        drift=0.0004,
        volatility=0.016,
        base_revenue=410_000_000_000,
        operating_margin=0.11,
        revision=1.02,
        shares=180_000_000,
    ),
    Company(
        key="GAMMA.DEMO",
        name="Gamma Energy",
        base_price=1480.0,
        drift=-0.0003,
        volatility=0.014,
        base_revenue=650_000_000_000,
        operating_margin=0.07,
        revision=0.88,  # 下方修正。上方修正だけのデモにしない
        shares=520_000_000,
    ),
]

STRATEGIES = [
    ("core", "Core", "長期保有を前提とする中核ポジション"),
    ("satellite", "Satellite", "テーマの実現度に応じて機動的に入れ替える"),
]

THEMES = [
    ("ai-data-center", "AI Data Center", "core",
     "生成AIの学習・推論需要に伴うデータセンター投資の拡大"),
    ("factory-automation", "Factory Automation", "satellite",
     "労働力不足と国内回帰による製造自動化投資"),
    ("energy-transition", "Energy Transition", "satellite",
     "電力需要の増加と電源構成の転換"),
]

# テーマと銘柄の対応。重みは合計1.0に揃えず、実際の構成比計算を働かせる。
THEME_MEMBERS = [
    ("ai-data-center", "ALPHA.DEMO", 0.6, "AI向け半導体の売上構成比が最も高い"),
    ("ai-data-center", "GAMMA.DEMO", 0.4, "データセンター向け電力供給の担い手"),
    ("factory-automation", "BETA.DEMO", 1.0, "産業用ロボットの主要サプライヤ"),
    ("energy-transition", "GAMMA.DEMO", 0.7, "再生可能エネルギーの発電事業"),
    ("energy-transition", "ALPHA.DEMO", 0.3, "電力変換向けパワー半導体"),
]


def _fiscal_year_end(year: int) -> date:
    return date(year, 3, 31)


def _quarter_periods(fiscal_year: int) -> list[tuple[str, date, date, date]]:
    """(期種別, 期間開始, 期間終了, 開示日) を会計年度ぶん返す。3月期決算とする。"""
    start = date(fiscal_year - 1, 4, 1)
    return [
        ("1Q", start, date(fiscal_year - 1, 6, 30), date(fiscal_year - 1, 8, 5)),
        ("2Q", start, date(fiscal_year - 1, 9, 30), date(fiscal_year - 1, 11, 6)),
        ("3Q", start, date(fiscal_year, 1, 31), date(fiscal_year, 2, 5)),
        ("FY", start, _fiscal_year_end(fiscal_year), date(fiscal_year, 5, 12)),
    ]


def _record_hash(payload: dict[str, Any]) -> str:
    """実ETLと同じく、キー順に依存しない正規化後のSHA-256を持たせる。"""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _business_days(end: date, count: int) -> list[date]:
    days: list[date] = []
    cursor = end
    while len(days) < count:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(days)


def _reset(connection: Connection) -> None:
    connection.execute(
        "TRUNCATE TABLE " + ", ".join(TRUNCATE_ORDER) + " RESTART IDENTITY CASCADE"
    )


def _insert_source(connection: Connection) -> int:
    row = connection.execute(
        """
        INSERT INTO data_source (source_key, source_name, base_url, terms_url)
        VALUES (?, ?, ?, ?)
        RETURNING source_id
        """,
        (
            DEMO_SOURCE_KEY,
            "Synthetic demo generator",
            None,
            None,
        ),
    ).fetchone()
    assert row is not None
    return int(row["source_id"])


def _insert_run(connection: Connection, source_id: int, job_type: str, days: int) -> int:
    started = datetime.combine(TODAY, time(21, 0), tzinfo=UTC)
    row = connection.execute(
        """
        INSERT INTO ingestion_run (
            job_type, git_commit_sha, source_id, status,
            requested_from, requested_to, target_count, fetched_count, loaded_count,
            raw_path, started_at, finished_at
        )
        VALUES (?, ?, ?, 'succeeded', ?, ?, ?, ?, ?, ?, ?, ?)
        RETURNING ingestion_run_id
        """,
        (
            job_type,
            "synthetic",
            source_id,
            TODAY - timedelta(days=days),
            TODAY,
            len(COMPANIES),
            len(COMPANIES),
            len(COMPANIES),
            # rawは存在しない。実データと同じ体裁のパスを書くと追跡できると誤解されるため明示する。
            None,
            started,
            started + timedelta(minutes=3),
        ),
    ).fetchone()
    assert row is not None
    return int(row["ingestion_run_id"])


def _insert_masters(connection: Connection, source_id: int) -> dict[str, int]:
    strategy_ids: dict[str, int] = {}
    for key, name, description in STRATEGIES:
        row = connection.execute(
            "INSERT INTO strategy (strategy_key, strategy_name, description) "
            "VALUES (?, ?, ?) RETURNING strategy_id",
            (key, name, description),
        ).fetchone()
        assert row is not None
        strategy_ids[key] = int(row["strategy_id"])

    theme_ids: dict[str, int] = {}
    for key, name, strategy_key, description in THEMES:
        row = connection.execute(
            "INSERT INTO theme (theme_key, theme_name, strategy_id, description) "
            "VALUES (?, ?, ?, ?) RETURNING theme_id",
            (key, name, strategy_ids[strategy_key], description),
        ).fetchone()
        assert row is not None
        theme_ids[key] = int(row["theme_id"])

    target_ids: dict[str, int] = {}
    for company in COMPANIES:
        row = connection.execute(
            """
            INSERT INTO investment_target
                (target_key, target_name, target_type, market, currency)
            VALUES (?, ?, 'individual_stock', 'Demo Exchange', 'JPY')
            RETURNING target_id
            """,
            (company.key, company.name),
        ).fetchone()
        assert row is not None
        target_ids[company.key] = int(row["target_id"])
        connection.execute(
            """
            INSERT INTO investment_target_identifier
                (target_id, source_id, identifier_type, identifier, valid_from, is_primary)
            VALUES (?, ?, 'demo_code', ?, ?, TRUE)
            """,
            (target_ids[company.key], source_id, company.key.split(".")[0], date(2020, 4, 1)),
        )

    for theme_key, target_key, weight, rationale in THEME_MEMBERS:
        connection.execute(
            """
            INSERT INTO theme_investment_target
                (theme_id, target_id, basket_weight, rationale)
            VALUES (?, ?, ?, ?)
            """,
            (theme_ids[theme_key], target_ids[target_key], weight, rationale),
        )
    return target_ids


def _insert_prices(
    connection: Connection, source_id: int, run_id: int, target_ids: dict[str, int]
) -> int:
    rng = random.Random(RANDOM_SEED)
    days = _business_days(TODAY, PRICE_DAYS)
    fetched = datetime.combine(TODAY, time(21, 5), tzinfo=UTC)
    # 1行ずつ送るとマネージドDBへの往復が数千回になり、投入が数分かかる。まとめて送る。
    rows: list[tuple[Any, ...]] = []

    for company in COMPANIES:
        price = company.base_price
        # 予想を上方修正する企業は、開示日の手前から緩やかに織り込ませる。
        revision_day = date(TODAY.year, 2, 5)
        for day in days:
            shock = rng.gauss(0.0, company.volatility)
            trend = company.drift
            if company.revision != 1.0 and day >= revision_day - timedelta(days=30):
                trend += (company.revision - 1.0) * 0.004
            price = max(price * math.exp(trend + shock), 1.0)

            intraday = abs(rng.gauss(0.0, company.volatility)) * price
            open_price = price - rng.uniform(-intraday, intraday) * 0.5
            high = max(open_price, price) + rng.uniform(0, intraday)
            low = min(open_price, price) - rng.uniform(0, intraday)
            volume = rng.uniform(0.8, 1.6) * company.shares * 0.004

            rows.append(
                (
                    target_ids[company.key],
                    source_id,
                    run_id,
                    day,
                    round(open_price, 1),
                    round(high, 1),
                    round(max(low, 1.0), 1),
                    round(price, 1),
                    round(volume),
                    fetched,
                )
            )

    connection.executemany(
        """
        INSERT INTO market_price_observation (
            target_id, source_id, ingestion_run_id, obs_date,
            open_price, high_price, low_price, close_price, volume,
            price_basis, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'adjusted', ?)
        """,
        rows,
    )
    return len(rows)


def _summary_values(
    company: Company, period: str, fiscal_year: int, revision: float = 1.0
) -> dict[str, Any]:
    """開示種別によって埋まる列を入れ替える。実データの振る舞いと揃える。

    - 四半期開示: 期中累計の実績 + 今期予想 + 年間配当予想
    - FY開示: 通期実績 + 翌期予想 + 年間配当実績（今期予想は入らない）

    `revision` は通期予想に掛ける倍率で、業績予想の修正開示だけが1.0以外を渡す。
    四半期開示に改訂後の値を入れてしまうと、改訂前後の差が画面に出なくなる。
    """
    growth = 1.0 + 0.05 * (fiscal_year - 2024)
    plan_annual = round(company.base_revenue * growth)
    # 実績は、改訂年度だけ改訂後の水準で着地させる。会社が予想を修正するのは、
    # 好調・不調が先に実績へ表れた結果であり、実績と改訂が食い違うと系列が破綻する。
    actual_annual = (
        round(plan_annual * company.revision)
        if fiscal_year == REVISION_FISCAL_YEAR
        else plan_annual
    )
    ratio = {"1Q": 0.23, "2Q": 0.48, "3Q": 0.72, "FY": 1.0}[period]

    revenue = round(actual_annual * ratio)
    operating = round(revenue * company.operating_margin)
    ordinary = round(operating * 1.04)
    net = round(ordinary * 0.68)
    eps = round(net / company.shares, 2)

    values: dict[str, Any] = {
        "revenue": revenue,
        "operating_income": operating,
        "ordinary_income": ordinary,
        "net_income": net,
        "eps": eps,
        "total_assets": round(actual_annual * 1.6),
        "equity": round(actual_annual * 0.75),
        "bps": round(actual_annual * 0.75 / company.shares, 2),
        "operating_cash_flow": round(operating * 1.2),
        "investing_cash_flow": -round(operating * 0.7),
        "financing_cash_flow": -round(operating * 0.2),
        "cash_equivalents": round(actual_annual * 0.18),
        "shares_outstanding": company.shares,
        "treasury_shares": round(company.shares * 0.02),
        "average_shares": round(company.shares * 0.98),
    }

    if period == "FY":
        # 期が終われば「今期」は実績になり、会社が示す見通しは翌期ぶんになる。
        next_revenue = round(actual_annual * 1.06)
        next_operating = round(next_revenue * company.operating_margin)
        values.update(
            next_forecast_revenue=next_revenue,
            next_forecast_operating_income=next_operating,
            next_forecast_ordinary_income=round(next_operating * 1.04),
            next_forecast_net_income=round(next_operating * 1.04 * 0.68),
            next_forecast_eps=round(next_operating * 1.04 * 0.68 / company.shares, 2),
            annual_dividend_per_share=round(eps * 0.3, 2),
        )
    else:
        forecast_revenue = round(plan_annual * revision)
        forecast_operating = round(forecast_revenue * company.operating_margin)
        forecast_net = round(forecast_operating * 1.04 * 0.68)
        values.update(
            forecast_revenue=forecast_revenue,
            forecast_operating_income=forecast_operating,
            forecast_ordinary_income=int(forecast_operating * 1.04),
            forecast_net_income=forecast_net,
            forecast_eps=round(forecast_net / company.shares, 2),
            forecast_annual_dividend_per_share=round(forecast_net / company.shares * 0.3, 2),
        )
    return values


def _insert_disclosure(
    connection: Connection,
    *,
    source_id: int,
    run_id: int,
    target_id: int,
    company: Company,
    number: str,
    disclosed: date,
    document_type: str,
    period_type: str | None,
    period_start: date | None,
    period_end: date | None,
    fiscal_year: int,
    values: dict[str, Any],
) -> None:
    fetched = datetime.combine(TODAY, time(21, 10), tzinfo=UTC)
    row = connection.execute(
        """
        INSERT INTO financial_disclosure (
            target_id, source_id, disclosure_number, disclosed_date, disclosed_time,
            document_type, fiscal_period_type, period_start, period_end,
            fiscal_year_start, fiscal_year_end, accounting_standard,
            ingestion_run_id, source_record_hash, fetched_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'JP', ?, ?, ?)
        RETURNING disclosure_id
        """,
        (
            target_id,
            source_id,
            number,
            disclosed,
            time(15, 0),
            document_type,
            period_type,
            period_start,
            period_end,
            date(fiscal_year - 1, 4, 1),
            _fiscal_year_end(fiscal_year),
            run_id,
            _record_hash({"number": number, "target": company.key, **values}),
            fetched,
        ),
    ).fetchone()
    assert row is not None
    disclosure_id = int(row["disclosure_id"])

    columns = ["disclosure_id", "reporting_scope", *values.keys()]
    placeholders = ", ".join(["?"] * len(columns))
    connection.execute(
        f"INSERT INTO financial_summary ({', '.join(columns)}) VALUES ({placeholders})",
        [disclosure_id, "consolidated", *values.values()],
    )


def _insert_financials(
    connection: Connection, source_id: int, run_id: int, target_ids: dict[str, int]
) -> int:
    count = 0
    for company in COMPANIES:
        target_id = target_ids[company.key]
        for fiscal_year in (2025, 2026):
            for period, period_start, period_end, disclosed in _quarter_periods(fiscal_year):
                if disclosed > TODAY:
                    continue
                scope = "Consolidated"
                document_type = f"{period}FinancialStatements_{scope}_JP"
                _insert_disclosure(
                    connection,
                    source_id=source_id,
                    run_id=run_id,
                    target_id=target_id,
                    company=company,
                    number=f"{company.key.split('.')[0]}-{fiscal_year}-{period}",
                    disclosed=disclosed,
                    document_type=document_type,
                    period_type=period,
                    period_start=period_start,
                    period_end=period_end,
                    fiscal_year=fiscal_year,
                    values=_summary_values(company, period, fiscal_year),
                )
                count += 1

            # 予想を見直した企業は、決算とは別に業績予想の修正を開示する。
            # 実績が空で予想だけ入る行があることを、デモでも再現する。
            if company.revision != 1.0 and fiscal_year == REVISION_FISCAL_YEAR:
                revised = _summary_values(company, "3Q", fiscal_year, company.revision)
                forecast_only = {
                    k: v for k, v in revised.items() if k.startswith("forecast_")
                }
                _insert_disclosure(
                    connection,
                    source_id=source_id,
                    run_id=run_id,
                    target_id=target_id,
                    company=company,
                    number=f"{company.key.split('.')[0]}-{fiscal_year}-REV",
                    disclosed=date(fiscal_year, 2, 12),
                    document_type="EarnForecastRevision",
                    period_type=None,
                    period_start=None,
                    period_end=None,
                    fiscal_year=fiscal_year,
                    values=forecast_only,
                )
                count += 1
    return count


def assert_demo_database(connection: Connection) -> str:
    """接続先がデモ用DBであることを確認する。違えば中断する。

    この確認を迂回する手段は用意しない。`--force` でも越えられない唯一の条件である。
    """
    row = connection.execute("SELECT current_database() AS name").fetchone()
    assert row is not None
    name = str(row["name"])
    if name not in DEMO_DATABASE_NAMES:
        raise SystemExit(
            f"中断しました。接続先のデータベース名が `{name}` です。\n"
            "このスクリプトは全テーブルを削除するため、デモ用DBだけを対象にします。\n"
            "許可されている名前: " + ", ".join(sorted(DEMO_DATABASE_NAMES))
        )
    return name


def existing_real_sources(connection: Connection) -> list[str]:
    """デモ以外の取得元がDBに存在するかを返す。実データの混入を判定する。"""
    rows = connection.execute(
        "SELECT source_key FROM data_source WHERE source_key <> ? ORDER BY source_key",
        (DEMO_SOURCE_KEY,),
    ).fetchall()
    return [row["source_key"] for row in rows]


def seed(connection: Connection, *, replace: bool, force: bool = False) -> dict[str, int]:
    """デモデータを投入する。

    接続先がデモ用DBであることを先に確認する。そのうえで、デモ用DBに実データ由来の
    取得元が混ざっている場合も中断する。`--force` が緩めるのは後者だけで、
    デモ用DB以外を対象にすることは許可しない。
    """
    assert_demo_database(connection)
    real_sources = existing_real_sources(connection)
    if real_sources and not force:
        raise SystemExit(
            "中断しました。デモ用DBに想定外の取得元があります: "
            + ", ".join(real_sources)
            + "\n実データが混入していないか確認してください。"
            "デモ用DBだと確信できる場合のみ --force を付けます。"
        )
    if replace:
        _reset(connection)
    source_id = _insert_source(connection)
    price_run = _insert_run(connection, source_id, "demo_prices", PRICE_DAYS)
    financial_run = _insert_run(connection, source_id, "demo_financials", 730)
    target_ids = _insert_masters(connection, source_id)
    prices = _insert_prices(connection, source_id, price_run, target_ids)
    disclosures = _insert_financials(connection, source_id, financial_run, target_ids)
    return {
        "themes": len(THEMES),
        "targets": len(COMPANIES),
        "prices": prices,
        "disclosures": disclosures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="公開デモ用のsyntheticデータを投入する（実データは投入しない）"
    )
    # 接続先は必ず明示させる。`backend/.env` の DATABASE_URL は本番を指しているため、
    # 既定値から拾うと本番DBをTRUNCATEしうる。暗黙のフォールバックを置かない。
    parser.add_argument(
        "--database-url",
        required=True,
        help="投入先のPostgreSQL接続URL。デモ用DBを明示的に指定する",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="既存の全アプリケーションデータを削除してから投入する",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="デモ用DBに想定外の取得元があっても続行する。デモ用DB以外は対象にできない",
    )
    args = parser.parse_args()

    os.environ["DATABASE_URL"] = args.database_url
    settings.database_url = args.database_url

    # migrationもDDLを伴うため、デモ用DBだと確認できるまで実行しない。
    connection = connect_database(read_only=False)
    try:
        assert_demo_database(connection)
    except BaseException:
        connection.close()
        raise

    upgrade_database()
    try:
        counts = seed(connection, replace=args.replace, force=args.force)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    print(
        "デモデータを投入しました: "
        f"テーマ{counts['themes']}件 / 銘柄{counts['targets']}件 / "
        f"価格{counts['prices']}件 / 開示{counts['disclosures']}件"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
