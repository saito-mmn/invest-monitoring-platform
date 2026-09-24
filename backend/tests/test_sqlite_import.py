import sqlite3
from datetime import date, datetime
from pathlib import Path

from app.database import Connection
from db.sqlite_import import import_sqlite_database


def _legacy_database(path: Path) -> None:
    schema_path = Path(__file__).parents[1] / "db" / "schema.sql"
    connection = sqlite3.connect(path)
    try:
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        connection.execute(
            """
            INSERT INTO strategy (strategy_key, strategy_name, is_active)
            VALUES ('legacy', 'Legacy', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO investment_target (
                target_key, target_name, target_type, market, currency, is_active
            ) VALUES ('8697.T', 'JPX', 'individual_stock', 'TSE', 'JPY', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO data_source (source_key, source_name, is_active)
            VALUES ('legacy', 'Legacy source', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO market_price_observation (
                target_id, source_id, obs_date, close_price, price_basis, fetched_at
            ) VALUES (1, 1, '2026-09-19', 1234.5, 'adjusted', '2026-09-20 00:00:00')
            """
        )
        connection.commit()
    finally:
        connection.close()


def test_import_sqlite_converts_types_and_counts(
    db: Connection, tmp_path: Path
) -> None:
    source = tmp_path / "legacy.db"
    _legacy_database(source)

    counts = import_sqlite_database(source, db, replace=True)
    db.commit()

    assert counts["strategy"] == 4
    assert counts["market_price_observation"] == 1
    strategy = db.execute(
        "SELECT * FROM strategy WHERE strategy_key = ?", ("legacy",)
    ).fetchone()
    price = db.execute("SELECT * FROM market_price_observation").fetchone()
    assert strategy is not None
    assert strategy["is_active"] is True
    assert isinstance(strategy["created_at"], datetime)
    assert price is not None
    assert price["obs_date"] == date(2026, 9, 19)
    assert isinstance(price["fetched_at"], datetime)


def test_import_sqlite_refuses_non_empty_destination(
    db: Connection, tmp_path: Path
) -> None:
    source = tmp_path / "legacy.db"
    _legacy_database(source)
    db.execute(
        "INSERT INTO investment_target (target_key, target_name) VALUES (?, ?)",
        ("existing", "Existing"),
    )
    db.commit()

    try:
        import_sqlite_database(source, db)
    except RuntimeError as exc:
        assert "--replace" in str(exc)
    else:
        raise AssertionError("non-empty destination must be rejected")
