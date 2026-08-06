"""JobManager: the only code in this app allowed to touch the `jobs` table
directly (backend/db.py). Every operation is a plain SQL statement or two
against whichever backend db.py has connected to (SQLite locally/in
tests, Supabase Postgres in production) — no separate broker, no new
infrastructure to provision, since a single Fly machine's worker loop
(worker.py) is the only consumer today. The row shape (dedupe_key,
status, attempts, run_after) is exactly what a broker-backed queue would
also need, so swapping the backend later (e.g. once traffic genuinely
needs more than one machine polling this table) is a manager.py rewrite
behind this same interface, not a rewrite of every caller.

Concurrency note: claim_next() uses SELECT-then-UPDATE-with-a-status-guard
rather than `SELECT ... FOR UPDATE SKIP LOCKED` (Postgres-only, no SQLite
equivalent) or `UPDATE ... RETURNING` (needs SQLite 3.35+, not guaranteed
across every deploy target). A lost race just means claim_next() returns
None and the caller's next poll tries again — correct, if not maximally
throughput-optimal, and correct is what matters at this app's actual
concurrency level (one worker loop, one machine, today)."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from .. import db
from .models import Job, JobStatus

logger = logging.getLogger("lingua.jobs.manager")

_MAX_BACKOFF_SECONDS = 300  # 5 minutes — a retrying job never waits longer than this between attempts.


def _row_to_job(row: Any) -> Job:
    d = dict(row)
    return Job(
        id=d["id"],
        job_type=d["job_type"],
        dedupe_key=d["dedupe_key"],
        payload=json.loads(d["payload"]),
        status=JobStatus(d["status"]),
        attempts=d["attempts"],
        max_attempts=d["max_attempts"],
        last_error=d["last_error"],
        created_at=d["created_at"],
        updated_at=d["updated_at"],
        run_after=d["run_after"],
    )


def enqueue(job_type: str, payload: dict, dedupe_key: str, max_attempts: int = 5) -> Job:
    """Idempotent: re-enqueueing the same dedupe_key while a job for it is
    pending/running/retrying/completed returns that row untouched — a
    build or a repair scan can call this unconditionally without
    coordinating with anything else that might have already queued the
    same unit of work.

    A dedupe_key whose job previously FAILED (exhausted every retry) is
    the one exception: enqueue() resets it back to pending instead. A
    scanner finding the same gap again after the underlying job gave up
    means either the root cause got fixed since then (e.g. a resumable-
    download bug) or an operator explicitly re-ran the scan hoping for a
    different outcome — either way, silently refusing to ever try that
    unit of work again would defeat the point of a self-healing queue."""
    now = db.now_iso()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM jobs WHERE dedupe_key = ?", (dedupe_key,))
        existing = cur.fetchone()
        if existing is not None:
            job = _row_to_job(existing)
            if job.status != JobStatus.FAILED:
                return job
            cur.execute(
                "UPDATE jobs SET status = ?, attempts = 0, last_error = '', updated_at = ?, run_after = ? WHERE id = ?",
                (JobStatus.PENDING, now, now, job.id),
            )
            cur.execute("SELECT * FROM jobs WHERE id = ?", (job.id,))
            return _row_to_job(cur.fetchone())
        cur.execute(
            "INSERT INTO jobs (job_type, dedupe_key, payload, status, attempts, max_attempts, last_error, "
            "created_at, updated_at, run_after) VALUES (?, ?, ?, ?, 0, ?, '', ?, ?, ?)",
            (job_type, dedupe_key, json.dumps(payload), JobStatus.PENDING, max_attempts, now, now, now),
        )
        cur.execute("SELECT * FROM jobs WHERE dedupe_key = ?", (dedupe_key,))
        row = cur.fetchone()
    return _row_to_job(row)


def claim_next(job_types: list[str]) -> Job | None:
    """Atomically (enough — see module docstring) claims one due job of
    any of the given types, oldest first. Returns None when nothing is
    claimable right now (queue empty, or every candidate's run_after is
    still in the future, or another worker won the race)."""
    if not job_types:
        return None
    now = db.now_iso()
    placeholders = ",".join("?" for _ in job_types)
    with db.cursor() as cur:
        cur.execute(
            f"SELECT * FROM jobs WHERE job_type IN ({placeholders}) "
            "AND status IN (?, ?) AND run_after <= ? ORDER BY id LIMIT 1",
            (*job_types, JobStatus.PENDING, JobStatus.RETRYING, now),
        )
        row = cur.fetchone()
        if row is None:
            return None
        job = _row_to_job(row)
        cur.execute(
            "UPDATE jobs SET status = ?, updated_at = ? WHERE id = ? AND status = ?",
            (JobStatus.RUNNING, now, job.id, job.status),
        )
        if cur.rowcount != 1:
            return None  # another worker claimed it between our SELECT and UPDATE
    job.status = JobStatus.RUNNING
    return job


def complete(job_id: int) -> None:
    now = db.now_iso()
    with db.cursor() as cur:
        cur.execute("UPDATE jobs SET status = ?, updated_at = ? WHERE id = ?", (JobStatus.COMPLETED, now, job_id))


def fail(job_id: int, error: str, attempts: int, max_attempts: int) -> None:
    """Called with the job's attempts/max_attempts as already known by the
    caller (claim_next's returned Job) rather than re-reading them, so a
    worker that already has the row in hand doesn't need a second query
    just to decide retry-vs-give-up."""
    now_dt = datetime.now(UTC)
    now = now_dt.isoformat()
    new_attempts = attempts + 1
    if new_attempts >= max_attempts:
        status = JobStatus.FAILED
        run_after = now
    else:
        status = JobStatus.RETRYING
        backoff = min(2**new_attempts, _MAX_BACKOFF_SECONDS)
        run_after = (now_dt + timedelta(seconds=backoff)).isoformat()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE jobs SET status = ?, attempts = ?, last_error = ?, updated_at = ?, run_after = ? WHERE id = ?",
            (status, new_attempts, error[:2000], now, run_after, job_id),
        )
    if status == JobStatus.FAILED:
        logger.error("job %d exhausted %d attempts, giving up: %s", job_id, new_attempts, error[:500])
    else:
        logger.warning("job %d failed (attempt %d/%d), retrying in %ds: %s", job_id, new_attempts, max_attempts, backoff, error[:500])


def get_job(job_id: int) -> Job | None:
    with db.cursor() as cur:
        cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
        row = cur.fetchone()
    return _row_to_job(row) if row is not None else None


def counts_by_status(job_type: str | None = None) -> dict[str, int]:
    """For observability (see routers/admin_jobs.py) — how many jobs of
    each status exist right now, optionally scoped to one job_type."""
    with db.cursor() as cur:
        if job_type is None:
            cur.execute("SELECT status, COUNT(*) as n FROM jobs GROUP BY status")
        else:
            cur.execute("SELECT status, COUNT(*) as n FROM jobs WHERE job_type = ? GROUP BY status", (job_type,))
        rows = cur.fetchall()
    return {dict(r)["status"]: dict(r)["n"] for r in rows}


def list_jobs(job_type: str | None = None, status: str | None = None, limit: int = 50) -> list[Job]:
    query = "SELECT * FROM jobs"
    conditions = []
    params: list[Any] = []
    if job_type is not None:
        conditions.append("job_type = ?")
        params.append(job_type)
    if status is not None:
        conditions.append("status = ?")
        params.append(status)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    with db.cursor() as cur:
        cur.execute(query, tuple(params))
        rows = cur.fetchall()
    return [_row_to_job(r) for r in rows]
