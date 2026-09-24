import pytest
from psycopg.errors import ReadOnlySqlTransaction

from app.database import connect_database


def test_read_only_connection_can_select_but_cannot_write():
    connection = connect_database(read_only=True)
    try:
        assert connection.execute("SELECT 1 AS value").fetchone()["value"] == 1
        with pytest.raises(ReadOnlySqlTransaction):
            connection.execute(
                "INSERT INTO data_source (source_key, source_name) VALUES ('blocked', 'Blocked')"
            )
    finally:
        connection.rollback()
        connection.close()
