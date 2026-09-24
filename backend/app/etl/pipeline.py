import gzip
import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.database import Connection
from app.etl.fetchers.jquants import JQuantsClient
from app.etl.loaders import (
    ensure_data_source,
    record_ingestion_errors,
    resolve_target_id,
    upsert_financial_disclosures,
    upsert_investment_target_master,
    upsert_prices,
)
from app.etl.models import ValidationIssue
from app.etl.normalizers import (
    normalize_jquants_financial,
    normalize_jquants_master,
    normalize_jquants_price,
)
from app.etl.validators import validate_price


def _git_commit_sha(project_root: Path) -> str | None:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=project_root,
            check=True, capture_output=True, text=True,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def _write_raw(raw_dir: Path, job_type: str, run_id: int, records: list[dict[str, Any]]) -> Path:
    now = datetime.now(UTC)
    target = raw_dir / "jquants" / job_type / now.strftime("%Y/%m/%d") / f"run-{run_id}.json.gz"
    target.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(target, "wt", encoding="utf-8") as stream:
        json.dump(records, stream, ensure_ascii=False, separators=(",", ":"))
    return target


def _display_path(path: Path, project_root: Path) -> str:
    try:
        return str(path.relative_to(project_root))
    except ValueError:
        return str(path)


def _start_run(conn: Connection, source_id: int, job_type: str, project_root: Path,
               date_from: str | None = None, date_to: str | None = None, target_count: int = 0) -> int:
    row = conn.execute(
        """
        INSERT INTO ingestion_run (
            job_type, git_commit_sha, source_id, status, requested_from, requested_to, target_count
        ) VALUES (?, ?, ?, 'running', ?, ?, ?)
        RETURNING ingestion_run_id
        """,
        (job_type, _git_commit_sha(project_root), source_id, date_from, date_to, target_count),
    ).fetchone()
    if row is None:
        raise RuntimeError("ingestion_run の作成に失敗しました")
    return int(row["ingestion_run_id"])


def _finish_run(conn: Connection, run_id: int, *, status: str, fetched: int,
                loaded: int, skipped: int, failed: int, raw_path: str | None,
                error_message: str | None = None) -> None:
    conn.execute(
        """
        UPDATE ingestion_run SET status=?, fetched_count=?, loaded_count=?, skipped_count=?,
            failed_count=?, raw_path=?, error_message=?, finished_at=CURRENT_TIMESTAMP
        WHERE ingestion_run_id=?
        """,
        (status, fetched, loaded, skipped, failed, raw_path, error_message, run_id),
    )


class JQuantsMarketPipeline:
    def __init__(self, conn: Connection, client: JQuantsClient, raw_dir: Path, project_root: Path) -> None:
        self.conn = conn
        self.client = client
        self.raw_dir = raw_dir
        self.project_root = project_root
        self.source_id = ensure_data_source(conn, "jquants", "J-Quants", client.base_url)

    def sync_master(self, *, code: str | None = None, date: str | None = None) -> dict[str, int]:
        job_type = "jquants_equities_master_v1"
        run_id = _start_run(self.conn, self.source_id, job_type, self.project_root, target_count=1 if code else 0)
        try:
            raw = self.client.equities_master(code=code, date=date)
            path = _write_raw(self.raw_dir, job_type, run_id, raw)
            records = [normalize_jquants_master(row) for row in raw]
            loaded = upsert_investment_target_master(self.conn, self.source_id, records)
            _finish_run(self.conn, run_id, status="succeeded", fetched=len(raw), loaded=loaded,
                        skipped=0, failed=0, raw_path=_display_path(path, self.project_root))
            self.conn.commit()
            return {"run_id": run_id, "fetched": len(raw), "loaded": loaded, "failed": 0}
        except Exception as exc:
            _finish_run(self.conn, run_id, status="failed", fetched=0, loaded=0, skipped=0,
                        failed=1, raw_path=None, error_message=str(exc))
            self.conn.commit()
            raise

    def sync_prices(self, *, codes: list[str], date_from: str | None = None,
                    date_to: str | None = None) -> dict[str, int]:
        job_type = "jquants_daily_prices_v1"
        run_id = _start_run(self.conn, self.source_id, job_type, self.project_root,
                            date_from, date_to, len(codes))
        raw: list[dict[str, Any]] = []
        fetch_errors = []
        for code in codes:
            try:
                raw.extend(self.client.daily_prices(code=code, date_from=date_from, date_to=date_to))
            except Exception as exc:
                fetch_errors.append(ValidationIssue(code, "fetch_error", str(exc), True))

        path = _write_raw(self.raw_dir, job_type, run_id, raw)
        valid = []
        validation_errors = []
        for row in raw:
            try:
                record = normalize_jquants_price(row)
                issues = validate_price(record)
                if issues:
                    validation_errors.extend(issues)
                else:
                    valid.append(record)
            except (KeyError, TypeError, ValueError) as exc:
                validation_errors.append(ValidationIssue(str(row.get("Code", "unknown")), "normalize_error", str(exc)))

        loaded, load_errors = upsert_prices(
            self.conn,
            self.source_id,
            valid,
            ingestion_run_id=run_id,
        )
        record_ingestion_errors(self.conn, run_id, "fetch", fetch_errors)
        record_ingestion_errors(self.conn, run_id, "validate", validation_errors)
        record_ingestion_errors(self.conn, run_id, "load", load_errors)
        failed = len(fetch_errors) + len(validation_errors) + len(load_errors)
        status = "succeeded" if failed == 0 else "partial" if loaded else "failed"
        _finish_run(self.conn, run_id, status=status, fetched=len(raw), loaded=loaded,
                    skipped=len(validation_errors) + len(load_errors), failed=failed,
                    raw_path=_display_path(path, self.project_root))
        self.conn.commit()
        return {"run_id": run_id, "fetched": len(raw), "loaded": loaded, "failed": failed}

    def sync_financials(self, *, codes: list[str] | None = None,
                        date: str | None = None) -> dict[str, int]:
        """開示単位の財務サマリーを取得して保存する。

        銘柄指定（`codes`）では契約プランの範囲にある全開示を銘柄ごとに取得する。
        開示日指定（`date`）ではその日の全銘柄の開示を1リクエストで取得するため、
        日次の増分取り込みに向く。どちらか一方だけを指定する。

        開示日指定では追跡していない銘柄の開示も返るため、対応が無いものは
        エラーではなく対象外として数える。
        """
        if (codes is None) == (date is None):
            raise ValueError("codes と date はどちらか一方を指定してください")

        job_type = "jquants_financial_summary_v1"
        run_id = _start_run(self.conn, self.source_id, job_type, self.project_root,
                            date, date, len(codes) if codes else 0)
        raw: list[dict[str, Any]] = []
        fetch_errors = []
        # 開示日指定では1リクエストで済むため、ループ対象を1件だけにする。
        targets: list[str | None] = list(codes) if codes else [None]
        for target in targets:
            try:
                raw.extend(self.client.financial_summaries(code=target, date=date))
            except Exception as exc:
                fetch_errors.append(
                    ValidationIssue(target or date or "unknown", "fetch_error", str(exc), True)
                )

        path = _write_raw(self.raw_dir, job_type, run_id, raw)
        records = []
        normalize_errors = []
        for row in raw:
            try:
                records.append(normalize_jquants_financial(row))
            except (KeyError, TypeError, ValueError) as exc:
                normalize_errors.append(
                    ValidationIssue(str(row.get("DiscNo", "unknown")), "normalize_error", str(exc))
                )

        untracked = 0
        if date is not None:
            tracked = [r for r in records if resolve_target_id(self.conn, self.source_id, r.jpx_code)]
            untracked = len(records) - len(tracked)
            records = tracked

        loaded, load_errors = upsert_financial_disclosures(
            self.conn, self.source_id, records, ingestion_run_id=run_id
        )
        record_ingestion_errors(self.conn, run_id, "fetch", fetch_errors)
        record_ingestion_errors(self.conn, run_id, "normalize", normalize_errors)
        record_ingestion_errors(self.conn, run_id, "load", load_errors)
        failed = len(fetch_errors) + len(normalize_errors) + len(load_errors)
        status = "succeeded" if failed == 0 else "partial" if loaded else "failed"
        _finish_run(self.conn, run_id, status=status, fetched=len(raw), loaded=loaded,
                    skipped=untracked + len(normalize_errors) + len(load_errors), failed=failed,
                    raw_path=_display_path(path, self.project_root))
        self.conn.commit()
        return {
            "run_id": run_id, "fetched": len(raw), "loaded": loaded,
            "untracked": untracked, "failed": failed,
        }
