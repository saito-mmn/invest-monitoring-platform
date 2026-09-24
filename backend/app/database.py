"""PostgreSQL接続管理とDB-API差分の薄いアダプター。"""

from collections.abc import Generator, Iterator, Mapping, Sequence
from typing import Any, Protocol, overload

import psycopg
from fastapi import HTTPException, status

from app.config import settings


class Cursor(Protocol):
    rowcount: int
    lastrowid: int | None

    def execute(self, query: str, params: Sequence[Any] = ()) -> "Cursor": ...

    def fetchone(self) -> Mapping[str, Any] | None: ...

    def fetchall(self) -> list[Mapping[str, Any]]: ...

    def __iter__(self) -> Iterator[Mapping[str, Any]]: ...


class Connection(Protocol):
    def execute(self, query: str, params: Sequence[Any] = ()) -> Any: ...

    def cursor(self) -> Any: ...

    def executemany(self, query: str, params_seq: Sequence[Sequence[Any]]) -> Any: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def close(self) -> None: ...


class HybridRow(Mapping[str, Any]):
    """sqlite3.Row同様、列名と添字の両方で参照できるPostgreSQL行。"""

    def __init__(self, columns: tuple[str, ...], values: Sequence[Any]):
        self._columns = columns
        self._values = tuple(values)
        self._positions = {name: index for index, name in enumerate(columns)}

    @overload
    def __getitem__(self, key: str) -> Any: ...

    @overload
    def __getitem__(self, key: int) -> Any: ...

    def __getitem__(self, key: str | int) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return self._values[self._positions[key]]

    def __iter__(self) -> Iterator[str]:
        return iter(self._columns)

    def __len__(self) -> int:
        return len(self._columns)


def hybrid_row(cursor: psycopg.Cursor[Any]):
    columns = tuple(column.name for column in cursor.description or ())

    def make_row(values: Sequence[Any]) -> HybridRow:
        return HybridRow(columns, values)

    return make_row


def _postgres_sql(query: str) -> str:
    """qmarkプレースホルダーをpsycopg形式へドライバー境界で変換する。"""
    return query.replace("?", "%s")


class PostgresCursor:
    def __init__(self, cursor: psycopg.Cursor[HybridRow]):
        self._cursor = cursor

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> int | None:
        """SQLite移行期間中のfixture互換。新規実装はRETURNINGを使う。"""
        try:
            cursor = self._cursor.connection.cursor()
            cursor.execute("SELECT LASTVAL() AS lastrowid")
            row = cursor.fetchone()
            return int(row["lastrowid"]) if row else None
        except psycopg.Error:
            return None

    def execute(self, query: str, params: Sequence[Any] = ()) -> "PostgresCursor":
        self._cursor.execute(_postgres_sql(query), params)
        return self

    def fetchone(self) -> HybridRow | None:
        return self._cursor.fetchone()

    def fetchall(self) -> list[HybridRow]:
        return self._cursor.fetchall()

    def __iter__(self) -> Iterator[HybridRow]:
        return iter(self._cursor)


class PostgresConnection:
    def __init__(self, connection: psycopg.Connection[HybridRow]):
        self._connection = connection

    def execute(self, query: str, params: Sequence[Any] = ()) -> PostgresCursor:
        cursor = self._connection.cursor()
        cursor.execute(_postgres_sql(query), params)
        return PostgresCursor(cursor)

    def cursor(self) -> PostgresCursor:
        return PostgresCursor(self._connection.cursor())

    def executemany(
        self, query: str, params_seq: Sequence[Sequence[Any]]
    ) -> PostgresCursor:
        cursor = self._connection.cursor()
        cursor.executemany(_postgres_sql(query), params_seq)
        return PostgresCursor(cursor)

    def commit(self) -> None:
        self._connection.commit()

    def rollback(self) -> None:
        self._connection.rollback()

    def close(self) -> None:
        self._connection.close()


def connect_database(*, read_only: bool | None = None) -> PostgresConnection:
    connection = psycopg.connect(settings.database_url, row_factory=hybrid_row)
    connection.read_only = settings.database_read_only if read_only is None else read_only
    return PostgresConnection(connection)


def get_db() -> Generator[Connection, None, None]:
    conn = connect_database()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_readiness_db() -> Generator[Connection, None, None]:
    """Readiness確認用DB接続。接続不能はサービス準備未完了として扱う。"""
    try:
        yield from get_db()
    except psycopg.Error as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"status": "not_ready", "database": "unavailable"},
        ) from exc
