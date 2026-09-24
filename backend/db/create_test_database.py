"""テスト専用データベースを作成する。

pytestは全テーブルをTRUNCATEするため、開発用DBを対象にすると開発データが毎回消える。
`compose.yaml` は初回起動時に作るが、既存ボリュームには存在しないのでこれで追加する。
"""

import sys
from pathlib import Path
from urllib.parse import urlparse, urlunparse

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings

TEST_DATABASE_NAME = "invest_test"


def main() -> int:
    parsed = urlparse(settings.database_url)
    # 作成対象へは接続できないため、同じサーバの既定DBへ繋いでから CREATE する。
    admin_url = urlunparse(parsed._replace(path="/postgres"))
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DATABASE_NAME,)
        ).fetchone()
        if exists:
            print(f"既に存在します: {TEST_DATABASE_NAME}")
            return 0
        connection.execute(f'CREATE DATABASE "{TEST_DATABASE_NAME}"')
    print(f"作成しました: {TEST_DATABASE_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
