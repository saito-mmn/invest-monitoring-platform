from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from db.provision_roles import connection_url_for_role, write_secret_file


def test_connection_url_for_role_preserves_endpoint_and_query() -> None:
    result = connection_url_for_role(
        "postgresql://owner:old@ep-example.neon.tech/neondb?sslmode=require",
        "app_reader",
        "p@ss/word",
    )
    parsed = urlparse(result)

    assert parsed.username == "app_reader"
    assert parsed.password == "p%40ss%2Fword"
    assert parsed.hostname == "ep-example.neon.tech"
    assert parsed.path == "/neondb"
    assert parse_qs(parsed.query) == {"sslmode": ["require"]}


def test_write_secret_file_is_private_and_refuses_overwrite(tmp_path: Path) -> None:
    output = tmp_path / ".env.neon"
    urls = {
        "app_reader": "reader-url",
        "app_writer": "writer-url",
        "etl_writer": "etl-url",
    }
    write_secret_file(output, urls)

    assert output.stat().st_mode & 0o777 == 0o600
    assert "DATABASE_READER_URL=reader-url" in output.read_text(encoding="utf-8")
    with pytest.raises(FileExistsError):
        write_secret_file(output, urls)
