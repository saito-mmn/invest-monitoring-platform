import pytest
from psycopg.errors import UniqueViolation

from app.database import Connection


def _insert_source_and_asset(db: Connection) -> tuple[int, int]:
    source_id = db.execute(
        "INSERT INTO data_source (source_key, source_name) VALUES (?, ?)",
        ("jquants", "J-Quants"),
    ).lastrowid
    target_id = db.execute(
        """
        INSERT INTO investment_target (target_key, target_name, target_type)
        VALUES (?, ?, ?)
        """,
        ("8697.T", "Japan Exchange Group", "individual_stock"),
    ).lastrowid
    assert source_id is not None and target_id is not None
    return source_id, target_id


def test_financial_disclosures_keep_corrections_as_separate_records(db):
    source_id, target_id = _insert_source_and_asset(db)

    def insert_disclosure(number: str) -> int:
        return db.execute(
            """
            INSERT INTO financial_disclosure (
                target_id, source_id, disclosure_number, disclosed_date,
                document_type, fiscal_period_type, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (target_id, source_id, number, "2026-05-15", "FY", "FY", "2026-08-27T00:00:00Z"),
        ).lastrowid

    original_id = insert_disclosure("DISC-001")
    correction_id = insert_disclosure("DISC-002")

    assert correction_id != original_id
    assert db.execute("SELECT COUNT(*) FROM financial_disclosure").fetchone()[0] == 2


def test_investment_target_identifier_is_unique_for_source_and_validity_period(db):
    source_id, target_id = _insert_source_and_asset(db)
    values = (target_id, source_id, "jpx_code", "86970", True)
    sql = """
        INSERT INTO investment_target_identifier (
            target_id, source_id, identifier_type, identifier, is_primary
        ) VALUES (?, ?, ?, ?, ?)
    """
    db.execute(sql, values)

    with pytest.raises(UniqueViolation):
        db.execute(sql, values)


def test_financial_disclosure_number_is_idempotency_key(db):
    source_id, target_id = _insert_source_and_asset(db)
    values = (
        target_id,
        source_id,
        "DISC-001",
        "2026-05-15",
        "FY",
        "2026-08-27T00:00:00Z",
    )
    sql = """
        INSERT INTO financial_disclosure (
            target_id, source_id, disclosure_number, disclosed_date,
            document_type, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?)
    """
    db.execute(sql, values)

    with pytest.raises(UniqueViolation):
        db.execute(sql, values)


def test_financial_summary_is_deleted_with_disclosure(db):
    source_id, target_id = _insert_source_and_asset(db)
    disclosure_id = db.execute(
        """
        INSERT INTO financial_disclosure (
            target_id, source_id, disclosure_number, disclosed_date,
            document_type, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (target_id, source_id, "DISC-001", "2026-05-15", "FY", "2026-08-27T00:00:00Z"),
    ).lastrowid
    db.execute(
        """
        INSERT INTO financial_summary (disclosure_id, reporting_scope, revenue, eps)
        VALUES (?, ?, ?, ?)
        """,
        (disclosure_id, "consolidated", 123_000_000, 42.5),
    )

    db.execute("DELETE FROM financial_disclosure WHERE disclosure_id = ?", (disclosure_id,))
    assert db.execute("SELECT COUNT(*) FROM financial_summary").fetchone()[0] == 0


def test_schema_does_not_persist_derived_direction(db):
    rows = db.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'market_price_observation'"
    ).fetchall()
    assert "direction" not in {row["column_name"] for row in rows}


def test_investment_target_prices_keep_source_specific_observations(db):
    source_a = db.execute(
        "INSERT INTO data_source (source_key, source_name) VALUES ('source-a', 'Source A')"
    ).lastrowid
    source_b = db.execute(
        "INSERT INTO data_source (source_key, source_name) VALUES ('source-b', 'Source B')"
    ).lastrowid
    target_id = db.execute(
        "INSERT INTO investment_target (target_key, target_name) VALUES ('TEST.T', 'Test')"
    ).lastrowid
    db.executemany(
        """
        INSERT INTO market_price_observation (
            target_id, source_id, obs_date, close_price, price_basis
        ) VALUES (?, ?, '2026-09-04', ?, 'adjusted')
        """,
        [(target_id, source_a, 100.0), (target_id, source_b, 101.0)],
    )

    assert db.execute(
        "SELECT COUNT(*) FROM market_price_observation WHERE target_id=? AND obs_date='2026-09-04'",
        (target_id,),
    ).fetchone()[0] == 2
