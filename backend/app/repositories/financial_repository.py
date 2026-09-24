"""FinancialRepository — 開示単位の財務サマリーの読み取り。

開示種別によって値が入る列が入れ替わるため、最新値の組み立てもここで行う。
規則は docs/traceability/jquants-financial-summary.md を参照。
"""

from typing import Any

from app.repositories.base import BaseRepository

# 各予想が「入っている」と判定するための列。いずれかが非NULLなら、その開示は当該予想を持つ。
# 業績予想と配当予想は会社が別々に開示する。実データでは、業績予想を出さず配当予想だけ
# 出す企業があるため、同じ括りにすると「予想はあるが中身が空」に見えてしまう。
_CURRENT_FORECAST_COLUMNS = (
    "forecast_revenue",
    "forecast_operating_income",
    "forecast_ordinary_income",
    "forecast_net_income",
    "forecast_eps",
)
_DIVIDEND_FORECAST_COLUMNS = ("forecast_annual_dividend_per_share",)
# 実績が「入っている」と判定するための列。配当修正や業績予想の修正だけの開示は
# これらを持たないため、最新の開示がそのまま最新の実績とは限らない。
_ACTUAL_COLUMNS = (
    "revenue",
    "operating_income",
    "ordinary_income",
    "net_income",
    "eps",
    "total_assets",
    "equity",
    "bps",
)
_NEXT_FORECAST_COLUMNS = (
    "next_forecast_revenue",
    "next_forecast_operating_income",
    "next_forecast_ordinary_income",
    "next_forecast_net_income",
    "next_forecast_eps",
)

_DISCLOSURE_SELECT = """
    SELECT d.disclosure_id, d.target_id, d.disclosure_number, d.disclosed_date,
           d.disclosed_time, d.document_type, d.fiscal_period_type,
           d.period_start, d.period_end, d.fiscal_year_start, d.fiscal_year_end,
           d.accounting_standard, d.ingestion_run_id, d.fetched_at,
           ds.source_key, s.*
    FROM financial_disclosure d
    JOIN data_source ds ON ds.source_id = d.source_id
    LEFT JOIN financial_summary s USING (disclosure_id)
"""

# 開示の新しい順。同日の複数開示は時刻、それも同じなら開示番号で決める。
_LATEST_FIRST = "ORDER BY d.disclosed_date DESC, d.disclosed_time DESC, d.disclosure_number DESC"


class FinancialRepository(BaseRepository):

    def find_disclosures(self, target_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """銘柄の開示履歴を新しい順に返す。訂正開示も別レコードとして含む。"""
        return self.execute_query(
            f"{_DISCLOSURE_SELECT} WHERE d.target_id = ? {_LATEST_FIRST} LIMIT ?",
            (target_id, limit),
        )

    def _latest_with_any(self, target_id: int, columns: tuple[str, ...]) -> dict[str, Any] | None:
        condition = " OR ".join(f"s.{column} IS NOT NULL" for column in columns)
        return self.execute_single(
            f"{_DISCLOSURE_SELECT} WHERE d.target_id = ? AND ({condition}) {_LATEST_FIRST} LIMIT 1",
            (target_id,),
        )

    def find_forecast_history(self, target_id: int, limit: int = 50) -> list[dict[str, Any]]:
        """会社予想を含む開示を新しい順に返す。

        予想は決算短信だけでなく業績予想の修正でも更新される。実績を伴わない開示も
        含めるため、実績列ではなく予想列の有無で抽出する。配当予想だけを修正する
        開示もあるため、業績予想と配当予想のどちらかがあれば対象とする。
        """
        columns = (*_CURRENT_FORECAST_COLUMNS, *_DIVIDEND_FORECAST_COLUMNS)
        condition = " OR ".join(f"s.{column} IS NOT NULL" for column in columns)
        return self.execute_query(
            f"{_DISCLOSURE_SELECT} WHERE d.target_id = ? AND ({condition}) "
            f"{_LATEST_FIRST} LIMIT ?",
            (target_id, limit),
        )

    def find_latest(self, target_id: int) -> dict[str, Any] | None:
        """最新の実績・今期業績予想・翌期業績予想・配当予想を組み立てて返す。

        開示種別によって値が入る列が入れ替わるため、どの区分も「その値を持つ最新の開示」
        から取り、出所の開示も併せて返す。実績も例外ではない。配当修正だけの開示が
        最新であっても、`latest_actual` には実績を含む直近の開示が入る。

        `latest_disclosure` は種別を問わない最新の開示で、最終更新日の表示に使う。
        実績値の参照には `latest_actual` を使うこと。
        """
        latest = self.execute_single(
            f"{_DISCLOSURE_SELECT} WHERE d.target_id = ? {_LATEST_FIRST} LIMIT 1",
            (target_id,),
        )
        if latest is None:
            return None
        return {
            "target_id": target_id,
            "latest_disclosure": latest,
            "latest_actual": self._latest_with_any(target_id, _ACTUAL_COLUMNS),
            "current_forecast": self._latest_with_any(target_id, _CURRENT_FORECAST_COLUMNS),
            "next_forecast": self._latest_with_any(target_id, _NEXT_FORECAST_COLUMNS),
            "dividend_forecast": self._latest_with_any(target_id, _DIVIDEND_FORECAST_COLUMNS),
        }
