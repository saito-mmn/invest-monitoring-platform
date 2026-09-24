"""One-time migration CLI from the legacy SQLite database to PostgreSQL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings
from app.database import connect_database
from db.postgres_migrations import upgrade_database
from db.sqlite_import import import_sqlite_database


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import the legacy SQLite database into PostgreSQL"
    )
    parser.add_argument(
        "source",
        nargs="?",
        type=Path,
        default=settings.legacy_db_path,
        help="SQLite source path (default: LEGACY_SQLITE_PATH)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace all existing PostgreSQL application data",
    )
    args = parser.parse_args()

    upgrade_database()
    connection = connect_database(read_only=False)
    try:
        counts = import_sqlite_database(args.source.resolve(), connection, replace=args.replace)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    total = sum(counts.values())
    print(f"Migrated {total} rows from {args.source.resolve()}")
    for table, count in counts.items():
        print(f"  {table}: {count}")


if __name__ == "__main__":
    main()
