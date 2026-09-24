"""
データ管理 API
- 日次更新 (BackgroundTasks 経由)
- DB 初期化
"""
import subprocess
import sys
from pathlib import Path
from threading import Lock

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from app.config import settings
from app.database import Connection, get_db
from app.security import require_management_access
from db.postgres_migrations import upgrade_database

router = APIRouter(
    prefix="/data",
    tags=["data"],
    dependencies=[Depends(require_management_access)],
)

_active_jobs: set[str] = set()
_active_jobs_lock = Lock()


def _run_script(job_name: str, script_path: Path, arguments: list[str] | None = None) -> None:
    try:
        result = subprocess.run(
            [sys.executable, str(script_path), *(arguments or [])],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            print(f"Script error ({job_name}):\n{result.stderr}")
    finally:
        with _active_jobs_lock:
            _active_jobs.discard(job_name)


def _schedule_script(
    background_tasks: BackgroundTasks,
    job_name: str,
    script_path: Path,
    arguments: list[str] | None = None,
) -> None:
    with _active_jobs_lock:
        if job_name in _active_jobs:
            raise HTTPException(status_code=409, detail=f"{job_name} is already running")
        _active_jobs.add(job_name)
    background_tasks.add_task(_run_script, job_name, script_path, arguments)


@router.post("/daily-update")
def daily_update(background_tasks: BackgroundTasks):
    """日次データ更新をバックグラウンドで実行"""
    if not settings.daily_update_script.exists():
        raise HTTPException(status_code=500, detail="daily_update.py not found")
    _schedule_script(background_tasks, "daily-update", settings.daily_update_script)
    return {"status": "started", "job_type": "daily-update"}


@router.post("/backfill")
def backfill_prices(
    background_tasks: BackgroundTasks,
    years: int = Query(default=1, ge=1, le=20),
    code: list[str] | None = Query(default=None),
):
    """J-Quantsの日次株価をバックグラウンドで再取得する。"""
    if not settings.jquants_sync_script.exists():
        raise HTTPException(status_code=500, detail="jquants_sync.py not found")
    arguments = ["prices", "--years", str(years)]
    for item in code or []:
        arguments.extend(["--code", item])
    _schedule_script(
        background_tasks,
        "backfill-prices",
        settings.jquants_sync_script,
        arguments,
    )
    return {"status": "started", "job_type": "backfill-prices"}


@router.post("/init-db")
def init_db():
    """PostgreSQLへ未適用のAlembic migrationを適用する。"""
    upgrade_database()
    return {"status": "ok", "revision": "head"}


@router.get("/runs")
def list_ingestion_runs(
    limit: int = Query(default=50, ge=1, le=200),
    db: Connection = Depends(get_db),
):
    rows = db.execute("""
        SELECT ingestion_run_id, job_type, git_commit_sha, status,
               requested_from, requested_to, target_count, fetched_count,
               loaded_count, skipped_count, failed_count, raw_path,
               started_at, finished_at
        FROM ingestion_run
        ORDER BY started_at DESC, ingestion_run_id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    return [dict(row) for row in rows]


@router.get("/runs/{run_id}")
def get_ingestion_run(run_id: int, db: Connection = Depends(get_db)):
    row = db.execute("""
        SELECT ingestion_run_id, job_type, git_commit_sha, status,
               requested_from, requested_to, target_count, fetched_count,
               loaded_count, skipped_count, failed_count, raw_path,
               error_message, started_at, finished_at
        FROM ingestion_run
        WHERE ingestion_run_id = ?
    """, (run_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Ingestion run not found")
    return dict(row)
