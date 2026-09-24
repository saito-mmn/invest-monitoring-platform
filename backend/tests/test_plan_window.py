"""プラン提供期間へのクランプを検証する。"""

from datetime import date

from app.etl.plan_window import PlanWindow

FREE = PlanWindow(lag_days=84, history_years=2)
TODAY = date(2026, 9, 12)


def test_bounds_match_the_observed_free_plan_window():
    """実測したFreeプランの窓（2024-06-20〜2026-06-20）と一致する。"""
    assert FREE.bounds(TODAY) == (date(2024, 6, 20), date(2026, 6, 20))


def test_recent_end_is_clamped_to_the_available_date():
    """提供されない直近期間を含む要求は、取得できる最新日まで縮める。"""
    assert FREE.clamp(date(2025, 9, 12), TODAY, today=TODAY) == (
        date(2025, 9, 12),
        date(2026, 6, 20),
    )


def test_old_end_is_clamped_to_the_history_limit():
    """遡れる範囲を超える要求は、取得できる最古日まで縮める。"""
    assert FREE.clamp(date(2018, 1, 1), date(2026, 1, 31), today=TODAY) == (
        date(2024, 6, 20),
        date(2026, 1, 31),
    )


def test_range_inside_the_window_is_unchanged():
    """窓の内側だけを要求した場合はそのまま使う。"""
    requested = (date(2026, 1, 6), date(2026, 1, 10))
    assert FREE.clamp(*requested, today=TODAY) == requested


def test_range_entirely_outside_the_window_returns_none():
    """窓と重ならない要求は取得対象なしとして扱う。"""
    assert FREE.clamp(date(2026, 7, 1), date(2026, 9, 1), today=TODAY) is None


def test_paid_plan_without_lag_reaches_today():
    """遅延なしのプランでは当日まで取得できる。"""
    paid = PlanWindow(lag_days=0, history_years=18)
    assert paid.clamp(date(2026, 9, 1), TODAY, today=TODAY) == (date(2026, 9, 1), TODAY)
