import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

# Tests must never inherit a production/Neon DATABASE_URL from .env.
# Every test truncates all tables, so the target must be a throwaway test database.
# The default deliberately differs from the development database (`invest`): pointing
# the suite at it would silently destroy local development data on every run.
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql://invest:invest@localhost:5432/invest_test",
)

from app.database import Connection, connect_database, get_db, get_readiness_db
from app.main import app
from db.postgres_migrations import upgrade_database

# Databases this suite is allowed to truncate. Development (`invest`) and production
# (`neondb`) are excluded on purpose; there is no option to override this.
TEST_DATABASE_NAMES = frozenset({"invest_test"})

_TABLES = (
    "financial_summary",
    "financial_disclosure",
    "market_price_observation",
    "theme_investment_target",
    "investment_target_identifier",
    "ingestion_error",
    "ingestion_run",
    "data_source",
    "investment_target",
    "theme",
    "strategy",
)


def _reset_database(conn: Connection) -> None:
    conn.execute(f"TRUNCATE {', '.join(_TABLES)} RESTART IDENTITY CASCADE")
    conn.execute("""
        INSERT INTO strategy (strategy_key, strategy_name, description)
        VALUES
            ('core', 'Core', '中核となる長期保有戦略'),
            ('satellite', 'Satellite', '成長機会を取り込む補完戦略'),
            ('alternatives', 'Alternatives', '伝統資産以外の分散戦略')
    """)
    conn.commit()


@pytest.fixture(scope="session", autouse=True)
def migrated_postgres() -> None:
    # 接続先を確かめてからDDLとTRUNCATEへ進む。名前が違えば何も実行しない。
    conn = connect_database(read_only=False)
    try:
        row = conn.execute("SELECT current_database() AS name").fetchone()
        assert row is not None
        name = str(row["name"])
    finally:
        conn.close()
    if name not in TEST_DATABASE_NAMES:
        pytest.exit(
            f"テストの接続先が `{name}` です。テストは全テーブルをTRUNCATEするため、"
            "専用のテストDBだけを対象にします。\n"
            "許可されている名前: " + ", ".join(sorted(TEST_DATABASE_NAMES)) + "\n"
            "ローカルでは `make db-test-create` で作成できます。",
            returncode=1,
        )
    upgrade_database()


@pytest.fixture
def db(migrated_postgres) -> Iterator[Connection]:
    conn = connect_database(read_only=False)
    _reset_database(conn)
    try:
        yield conn
    finally:
        conn.rollback()
        _reset_database(conn)
        conn.close()


@pytest.fixture
def client(db: Connection):
    def override_get_db():
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_readiness_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
