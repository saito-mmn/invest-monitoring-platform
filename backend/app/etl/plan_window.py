"""データ提供プランの取得可能期間に、要求期間を収める。

J-Quantsは契約プランの範囲外を含むリクエストを部分的に返さず、リクエスト全体を
HTTP 400 で拒否する。実際のレスポンス例:

    Your subscription covers the following dates: 2024-06-20 ~ 2026-06-20

そのため、要求期間をプランの窓へあらかじめ収めてから送信する。
"""

from datetime import date, timedelta


class PlanWindow:
    """プランが提供する期間の窓。

    Attributes:
        lag_days: 直近この日数分は提供されない（Freeは84日=12週）。
        history_years: 遡れる年数（Freeは2年）。
    """

    def __init__(self, lag_days: int, history_years: int) -> None:
        self.lag_days = lag_days
        self.history_years = history_years

    def bounds(self, today: date) -> tuple[date, date]:
        """指定日時点で取得できる最古日と最新日を返す。"""
        latest = today - timedelta(days=self.lag_days)
        try:
            earliest = latest.replace(year=latest.year - self.history_years)
        except ValueError:  # 2月29日
            earliest = latest.replace(year=latest.year - self.history_years, day=28)
        return earliest, latest

    def clamp(self, date_from: date, date_to: date, *, today: date) -> tuple[date, date] | None:
        """要求期間を窓へ収める。重なりが無ければ None を返す。"""
        earliest, latest = self.bounds(today)
        start = max(date_from, earliest)
        end = min(date_to, latest)
        if start > end:
            return None
        return start, end
