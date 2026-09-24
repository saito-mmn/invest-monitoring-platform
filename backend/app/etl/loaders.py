from datetime import UTC, datetime

from app.database import Connection
from app.etl.models import (
    FinancialRecord,
    InvestmentTargetMasterRecord,
    PriceRecord,
    ValidationIssue,
)


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_data_source(conn: Connection, key: str, name: str, base_url: str | None = None) -> int:
    conn.execute(
        """
        INSERT INTO data_source (source_key, source_name, base_url)
        VALUES (?, ?, ?)
        ON CONFLICT(source_key) DO UPDATE SET
            source_name = excluded.source_name,
            base_url = COALESCE(excluded.base_url, data_source.base_url),
            updated_at = CURRENT_TIMESTAMP
        """,
        (key, name, base_url),
    )
    row = conn.execute("SELECT source_id FROM data_source WHERE source_key = ?", (key,)).fetchone()
    if row is None:
        raise RuntimeError(f"data_source was not created: {key}")
    return int(row["source_id"])


def upsert_investment_target_master(
    conn: Connection, source_id: int, records: list[InvestmentTargetMasterRecord]
) -> int:
    now = utc_now()
    for record in records:
        conn.execute(
            """
            INSERT INTO investment_target (
                target_key, target_name, target_type, market, currency, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(target_key) DO UPDATE SET
                target_name = excluded.target_name,
                target_type = COALESCE(excluded.target_type, investment_target.target_type),
                market = COALESCE(excluded.market, investment_target.market),
                currency = excluded.currency,
                updated_at = excluded.updated_at
            """,
            (record.target_key, record.target_name, record.target_type, record.market, record.currency, now, now),
        )
        target_row = conn.execute(
            "SELECT target_id FROM investment_target WHERE target_key = ?", (record.target_key,)
        ).fetchone()
        if target_row is None:
            raise RuntimeError(f"investment_target was not created: {record.target_key}")
        target_id = int(target_row["target_id"])
        conn.execute(
            """
            INSERT INTO investment_target_identifier (target_id, source_id, identifier_type, identifier, is_primary)
            VALUES (?, ?, 'jpx_code', ?, TRUE)
            ON CONFLICT(source_id, identifier_type, identifier, valid_from) DO UPDATE SET
                target_id = excluded.target_id, is_primary = TRUE, updated_at = CURRENT_TIMESTAMP
            """,
            (target_id, source_id, record.jpx_code),
        )
    return len(records)


def active_jquants_codes(conn: Connection) -> list[str]:
    """有効な投資対象に紐づく、現在有効なJ-Quants Codeを返す。"""
    return [
        str(row["identifier"])
        for row in conn.execute(
            """
            SELECT DISTINCT ai.identifier
            FROM investment_target_identifier ai
            JOIN investment_target a ON a.target_id = ai.target_id
            JOIN data_source ds ON ds.source_id = ai.source_id
            WHERE ds.source_key = 'jquants'
              AND ai.identifier_type = 'jpx_code'
              AND ai.is_primary = TRUE
              AND a.is_active = TRUE
              AND ai.valid_from <= CURRENT_DATE
              AND (ai.valid_to IS NULL OR ai.valid_to >= CURRENT_DATE)
            ORDER BY ai.identifier
            """
        ).fetchall()
    ]


def resolve_target_id(conn: Connection, source_id: int, jpx_code: str) -> int | None:
    row = conn.execute(
        """
        SELECT target_id FROM investment_target_identifier
        WHERE source_id = ? AND identifier_type = 'jpx_code' AND identifier = ?
          AND valid_from <= CURRENT_DATE AND (valid_to IS NULL OR valid_to >= CURRENT_DATE)
        ORDER BY is_primary DESC, valid_from DESC LIMIT 1
        """,
        (source_id, jpx_code),
    ).fetchone()
    return int(row["target_id"]) if row else None


def upsert_prices(
    conn: Connection,
    source_id: int,
    records: list[PriceRecord],
    ingestion_run_id: int | None = None,
) -> tuple[int, list[ValidationIssue]]:
    loaded = 0
    issues: list[ValidationIssue] = []
    for record in records:
        target_id = resolve_target_id(conn, source_id, record.jpx_code)
        if target_id is None:
            issues.append(ValidationIssue(record.jpx_code, "unknown_investment_target", "No active jpx_code mapping"))
            continue
        conn.execute(
            """
            INSERT INTO market_price_observation (
                target_id, source_id, ingestion_run_id, obs_date,
                open_price, high_price, low_price, close_price, volume,
                price_basis, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'adjusted', CURRENT_TIMESTAMP)
            ON CONFLICT(target_id, source_id, obs_date) DO UPDATE SET
                ingestion_run_id = excluded.ingestion_run_id,
                open_price = excluded.open_price, high_price = excluded.high_price,
                low_price = excluded.low_price, close_price = excluded.close_price,
                volume = excluded.volume, price_basis = excluded.price_basis,
                fetched_at = excluded.fetched_at
            """,
            (target_id, source_id, ingestion_run_id, record.obs_date,
             record.open_price, record.high_price,
             record.low_price, record.close_price, record.volume),
        )
        loaded += 1
    return loaded, issues


def record_ingestion_errors(conn: Connection, run_id: int, stage: str, issues: list[ValidationIssue]) -> None:
    conn.executemany(
        """
        INSERT INTO ingestion_error (
            ingestion_run_id, entity_type, entity_key, stage,
            error_type, error_message, retryable
        ) VALUES (?, 'record', ?, ?, ?, ?, ?)
        """,
        [(run_id, item.entity_key, stage, item.error_type, item.message, item.retryable) for item in issues],
    )


def upsert_financial_disclosures(
    conn: Connection,
    source_id: int,
    records: list[FinancialRecord],
    ingestion_run_id: int | None = None,
) -> tuple[int, list[ValidationIssue]]:
    """開示単位で財務サマリーを保存する。

    冪等キーは `(source_id, disclosure_number)`。訂正開示は開示番号が異なるため
    元の開示を上書きせず別レコードとして残る。同じ開示番号の再取得は更新になる。
    """
    loaded = 0
    issues: list[ValidationIssue] = []
    now = utc_now()
    for record in records:
        target_id = resolve_target_id(conn, source_id, record.jpx_code)
        if target_id is None:
            issues.append(
                ValidationIssue(
                    record.jpx_code, "unknown_investment_target", "No active jpx_code mapping"
                )
            )
            continue

        conn.execute(
            """
            INSERT INTO financial_disclosure (
                target_id, source_id, disclosure_number, disclosed_date, disclosed_time,
                document_type, fiscal_period_type, period_start, period_end,
                fiscal_year_start, fiscal_year_end, accounting_standard,
                ingestion_run_id, source_record_hash, fetched_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, disclosure_number) DO UPDATE SET
                target_id = excluded.target_id,
                disclosed_date = excluded.disclosed_date,
                disclosed_time = excluded.disclosed_time,
                document_type = excluded.document_type,
                fiscal_period_type = excluded.fiscal_period_type,
                period_start = excluded.period_start,
                period_end = excluded.period_end,
                fiscal_year_start = excluded.fiscal_year_start,
                fiscal_year_end = excluded.fiscal_year_end,
                accounting_standard = excluded.accounting_standard,
                ingestion_run_id = excluded.ingestion_run_id,
                source_record_hash = excluded.source_record_hash,
                fetched_at = excluded.fetched_at,
                updated_at = excluded.updated_at
            """,
            (
                target_id, source_id, record.disclosure_number, record.disclosed_date,
                record.disclosed_time, record.document_type, record.fiscal_period_type,
                record.period_start, record.period_end, record.fiscal_year_start,
                record.fiscal_year_end, record.accounting_standard,
                ingestion_run_id, record.source_record_hash, now, now, now,
            ),
        )
        disclosure_row = conn.execute(
            "SELECT disclosure_id FROM financial_disclosure "
            "WHERE source_id = ? AND disclosure_number = ?",
            (source_id, record.disclosure_number),
        ).fetchone()
        if disclosure_row is None:
            raise RuntimeError(f"financial_disclosure was not created: {record.disclosure_number}")
        disclosure_id = int(disclosure_row["disclosure_id"])

        if not record.values:
            issues.append(
                ValidationIssue(
                    record.disclosure_number,
                    "empty_financial_summary",
                    "採用できる財務値がありませんでした",
                )
            )
            continue

        columns = ["disclosure_id", "reporting_scope", *record.values.keys()]
        assignments = ", ".join(f"{column} = excluded.{column}" for column in record.values)
        conn.execute(
            f"""
            INSERT INTO financial_summary ({", ".join(columns)}, created_at, updated_at)
            VALUES ({", ".join("?" for _ in columns)}, ?, ?)
            ON CONFLICT(disclosure_id) DO UPDATE SET
                reporting_scope = excluded.reporting_scope,
                {assignments},
                updated_at = excluded.updated_at
            """,
            (disclosure_id, record.reporting_scope, *record.values.values(), now, now),
        )
        loaded += 1
    return loaded, issues
