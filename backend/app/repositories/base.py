"""
BaseRepository
FastAPI の Depends(get_db) から渡されるDB接続を使用
"""
from typing import Any

from app.database import Connection


class BaseRepository:
    def __init__(self, conn: Connection):
        self.conn = conn

    def _row_to_dict(self, row) -> dict[str, Any] | None:
        return dict(row) if row else None

    def _rows_to_dicts(self, rows) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def execute_query(self, query: str, params: tuple = ()) -> list[dict[str, Any]]:
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return self._rows_to_dicts(cursor.fetchall())

    def execute_single(self, query: str, params: tuple = ()) -> dict[str, Any] | None:
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return self._row_to_dict(cursor.fetchone())

    def execute_write(self, query: str, params: tuple = ()) -> int:
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor.rowcount

    def execute_insert(self, query: str, id_column: str, params: tuple = ()) -> int:
        cursor = self.conn.cursor()
        cursor.execute(f"{query.rstrip()} RETURNING {id_column}", params)
        row = cursor.fetchone()
        if row is None:
            raise RuntimeError(f"INSERT did not return {id_column}")
        return int(row[id_column])
