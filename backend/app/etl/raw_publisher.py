"""Publish locally staged raw responses to immutable object storage."""

from __future__ import annotations

import hashlib
import subprocess
from collections.abc import Callable
from pathlib import Path

from app.database import Connection

CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve_raw_path(raw_path: str, project_root: Path, raw_dir: Path) -> Path:
    path = Path(raw_path)
    resolved = (path if path.is_absolute() else project_root / path).resolve()
    try:
        resolved.relative_to(raw_dir.resolve())
    except ValueError as exc:
        raise RuntimeError(f"raw_path escapes configured raw directory: {raw_path}") from exc
    return resolved


def _upload_immutable(
    source: Path,
    destination: str,
    *,
    runner: CommandRunner,
) -> None:
    digest = _sha256(source)
    result = runner(
        [
            "gcloud",
            "storage",
            "cp",
            str(source),
            destination,
            "--if-generation-match=0",
            f"--custom-metadata=sha256={digest}",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return

    existing = runner(
        [
            "gcloud",
            "storage",
            "objects",
            "describe",
            destination,
            "--format=value(metadata.sha256)",
        ],
        capture_output=True,
        text=True,
    )
    if existing.returncode == 0 and existing.stdout.strip() == digest:
        return
    raise RuntimeError(
        f"Immutable raw upload failed for {destination}: {result.stderr.strip()}"
    )


def publish_pending_raw(
    connection: Connection,
    *,
    raw_dir: Path,
    project_root: Path,
    destination_base: str,
    runner: CommandRunner = subprocess.run,
) -> dict[str, int]:
    """Upload available local raw files, then replace DB paths with GCS URIs."""
    if not destination_base.startswith("gs://"):
        raise ValueError("RAW_DATA_URI must start with gs://")

    rows = connection.execute(
        """
        SELECT ingestion_run_id, raw_path
        FROM ingestion_run
        WHERE raw_path IS NOT NULL AND raw_path NOT LIKE ?
        ORDER BY ingestion_run_id
        """,
        ("gs://%",),
    ).fetchall()
    uploaded = 0
    missing = 0
    for row in rows:
        raw_path = str(row["raw_path"])
        source = _resolve_raw_path(raw_path, project_root, raw_dir)
        if not source.is_file():
            missing += 1
            continue
        relative = source.relative_to(raw_dir.resolve()).as_posix()
        destination = f"{destination_base.rstrip('/')}/{relative}"
        _upload_immutable(source, destination, runner=runner)
        cursor = connection.execute(
            """
            UPDATE ingestion_run
            SET raw_path = ?
            WHERE ingestion_run_id = ? AND raw_path = ?
            """,
            (destination, int(row["ingestion_run_id"]), raw_path),
        )
        if cursor.rowcount != 1:
            raise RuntimeError(
                f"ingestion_run changed while publishing raw: {row['ingestion_run_id']}"
            )
        uploaded += 1
    connection.commit()
    return {"uploaded": uploaded, "missing": missing}
