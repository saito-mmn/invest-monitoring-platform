from datetime import date

import pandas as pd
import pytest

from scripts.daily_update import (
    REFETCH_OVERLAP_DAYS,
    partition_targets_by_price_source,
    resolve_fetch_start,
    upsert_price_frame,
)

ASSETS = [
    (1, "7203.T", "Toyota", "72030"),
    (2, "VT", "Vanguard Total World Stock ETF", None),
]


def test_assets_are_routed_per_symbol_when_jquants_is_enabled():
    codes, yfinance_targets = partition_targets_by_price_source(ASSETS, jquants_enabled=True)

    assert codes == ["72030"]
    assert yfinance_targets == [(2, "VT", "Vanguard Total World Stock ETF")]


def test_all_assets_use_yfinance_when_jquants_is_disabled():
    codes, yfinance_targets = partition_targets_by_price_source(ASSETS, jquants_enabled=False)

    assert codes == []
    assert yfinance_targets == [
        (1, "7203.T", "Toyota"),
        (2, "VT", "Vanguard Total World Stock ETF"),
    ]


@pytest.fixture
def price_db(db):
    """1銘柄・1取得元を登録した価格観測用のDB。"""
    db.execute(
        "INSERT INTO investment_target (target_key, target_name, target_type) "
        "VALUES ('7203.T', 'トヨタ', 'individual_stock')"
    )
    db.execute("INSERT INTO data_source (source_key, source_name) VALUES ('yfinance', 'yfinance')")
    db.commit()
    return db

def _price_frame(dates, volume=True):
    data = {
        "Open": [100.0 + i for i in range(len(dates))],
        "High": [110.0 + i for i in range(len(dates))],
        "Low": [90.0 + i for i in range(len(dates))],
        "Close": [105.0 + i for i in range(len(dates))],
    }
    if volume:
        data["Volume"] = [1000.0 * (i + 1) for i in range(len(dates))]
    return pd.DataFrame(data, index=pd.to_datetime(dates))


def test_fetch_start_uses_default_lookback_without_observations(price_db):
    """観測が無い銘柄は既定の遡及日数から取得する。"""
    start = resolve_fetch_start(price_db, 1, 1, today=date(2026, 9, 12), default_lookback_days=7)
    assert start == date(2026, 9, 5)


def test_fetch_start_resumes_from_last_observation_with_overlap(price_db):
    """最終観測日から重複分だけ遡って再取得する。"""
    upsert_price_frame(price_db, 1, 1, _price_frame(["2026-08-20"]))

    start = resolve_fetch_start(price_db, 1, 1, today=date(2026, 9, 12))

    assert start == date(2026, 8, 20) - pd.Timedelta(days=REFETCH_OVERLAP_DAYS).to_pytimedelta()


def test_fetch_start_is_independent_per_source(price_db):
    """取得元ごとに最終観測日を判定する。"""
    price_db.execute("INSERT INTO data_source (source_key, source_name) VALUES ('jquants', 'J-Quants')")
    upsert_price_frame(price_db, 1, 1, _price_frame(["2026-09-10"]))

    assert resolve_fetch_start(price_db, 1, 2, today=date(2026, 9, 12), default_lookback_days=7) == date(2026, 9, 5)


def test_all_fetched_rows_are_saved_with_volume(price_db):
    """取得した全営業日を保存し、出来高も記録する。"""
    saved = upsert_price_frame(price_db, 1, 1, _price_frame(["2026-09-08", "2026-09-09", "2026-09-10"]))

    rows = price_db.execute(
        "SELECT obs_date, close_price, volume FROM market_price_observation ORDER BY obs_date"
    ).fetchall()
    assert saved == 3
    assert [r[0] for r in rows] == [date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10)]
    assert [r[2] for r in rows] == [1000.0, 2000.0, 3000.0]


def test_refetching_the_same_range_is_idempotent(price_db):
    """同じ期間を取り直しても行は増えず、値が更新される。"""
    upsert_price_frame(price_db, 1, 1, _price_frame(["2026-09-08", "2026-09-09"]))
    updated = _price_frame(["2026-09-08", "2026-09-09"])
    updated["Close"] = [999.0, 888.0]
    upsert_price_frame(price_db, 1, 1, updated)

    rows = price_db.execute(
        "SELECT obs_date, close_price FROM market_price_observation ORDER BY obs_date"
    ).fetchall()
    assert [(row["obs_date"], row["close_price"]) for row in rows] == [
        (date(2026, 9, 8), 999.0),
        (date(2026, 9, 9), 888.0),
    ]


def test_jquants_daily_routing_is_disabled_by_default():
    """識別子があっても、日次のJ-Quants取得は明示的に有効化するまで使わない。

    プランの提供期間外だと、J-Quants経路へ振り分けた銘柄がどこからも取得できなくなる。
    """
    from app.config import Settings

    assert Settings().jquants_daily_enabled is False
