from dataclasses import dataclass


@dataclass(frozen=True)
class InvestmentTargetMasterRecord:
    jpx_code: str
    target_key: str
    target_name: str
    target_type: str | None
    market: str | None
    currency: str = "JPY"


@dataclass(frozen=True)
class PriceRecord:
    jpx_code: str
    obs_date: str
    open_price: float | None
    high_price: float | None
    low_price: float | None
    close_price: float | None
    volume: float | None


@dataclass(frozen=True)
class FinancialRecord:
    """1開示ぶんの財務サマリー。

    `values` は `financial_summary` の列名から値への対応で、未提供項目は含めない。
    """

    jpx_code: str
    disclosure_number: str
    disclosed_date: str
    disclosed_time: str | None
    document_type: str
    fiscal_period_type: str | None
    period_start: str | None
    period_end: str | None
    fiscal_year_start: str | None
    fiscal_year_end: str | None
    accounting_standard: str | None
    reporting_scope: str
    values: dict[str, int | float]
    source_record_hash: str


@dataclass(frozen=True)
class ValidationIssue:
    entity_key: str
    error_type: str
    message: str
    retryable: bool = False
