import subprocess
from pathlib import Path

import pytest

from app.database import Connection
from app.etl.raw_publisher import publish_pending_raw


def _ingestion_run(db: Connection, raw_path: str) -> int:
    source_id = db.execute(
        """
        INSERT INTO data_source (source_key, source_name)
        VALUES ('raw-test', 'Raw Test')
        RETURNING source_id
        """
    ).fetchone()["source_id"]
    return int(
        db.execute(
            """
            INSERT INTO ingestion_run (job_type, source_id, status, raw_path)
            VALUES ('raw_test_v1', ?, 'succeeded', ?)
            RETURNING ingestion_run_id
            """,
            (source_id, raw_path),
        ).fetchone()["ingestion_run_id"]
    )


def test_publish_pending_raw_uploads_then_rewrites_path(
    db: Connection, tmp_path: Path
) -> None:
    raw_dir = tmp_path / "data" / "raw"
    raw_file = raw_dir / "jquants" / "job" / "run-1.json.gz"
    raw_file.parent.mkdir(parents=True)
    raw_file.write_bytes(b"raw-content")
    raw_path = str(raw_file.relative_to(tmp_path))
    run_id = _ingestion_run(db, raw_path)
    commands: list[list[str]] = []

    def successful_runner(command, **_kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    result = publish_pending_raw(
        db,
        raw_dir=raw_dir,
        project_root=tmp_path,
        destination_base="gs://bucket/raw",
        runner=successful_runner,
    )

    row = db.execute(
        "SELECT raw_path FROM ingestion_run WHERE ingestion_run_id = ?", (run_id,)
    ).fetchone()
    assert result == {"uploaded": 1, "missing": 0}
    assert row["raw_path"] == "gs://bucket/raw/jquants/job/run-1.json.gz"
    assert commands[0][:3] == ["gcloud", "storage", "cp"]
    assert "--if-generation-match=0" in commands[0]
    assert any(part.startswith("--custom-metadata=sha256=") for part in commands[0])


def test_publish_pending_raw_rejects_path_outside_raw_dir(
    db: Connection, tmp_path: Path
) -> None:
    outside = tmp_path / "outside.json.gz"
    outside.write_bytes(b"raw")
    _ingestion_run(db, str(outside))

    with pytest.raises(RuntimeError, match="escapes configured raw directory"):
        publish_pending_raw(
            db,
            raw_dir=tmp_path / "data" / "raw",
            project_root=tmp_path,
            destination_base="gs://bucket/raw",
        )
