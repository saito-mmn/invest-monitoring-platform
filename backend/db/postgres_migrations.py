"""PostgreSQL migration entry point shared by CLI and management API."""

from pathlib import Path

from alembic import command
from alembic.config import Config


def upgrade_database(revision: str = "head") -> None:
    backend_dir = Path(__file__).parent.parent
    config = Config(str(backend_dir / "alembic.ini"))
    command.upgrade(config, revision)
