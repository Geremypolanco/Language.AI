#!/usr/bin/env python3
"""Inspects the job queue (backend/jobs/) — counts by status, and the most
recent rows of a given type/status. Deliberately a CLI script rather than
an HTTP endpoint: this app has no admin-role concept anywhere (see
backend/auth.py — only require_owner, a per-resource ownership check), so
an open route for "what's in the queue" would be one more thing to secure
for no real benefit when this already works, unauthenticated by
construction, for anyone who can reach this environment's database
credentials (the same bar every other operational script here — build_
academy.py, build_languages.py — already assumes).

Usage:
    python scripts/inspect_jobs.py                        # counts by status, all types
    python scripts/inspect_jobs.py --job-type audio_unit   # counts for one type
    python scripts/inspect_jobs.py --status failed --limit 20
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.jobs import manager  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--job-type", default=None, help="Only show this job_type (default: all).")
    parser.add_argument("--status", default=None, help="List recent jobs with this status (pending/running/completed/failed/retrying).")
    parser.add_argument("--limit", type=int, default=20, help="Max rows to list when --status is given (default: 20).")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    counts = manager.counts_by_status(args.job_type)
    scope = f"job_type={args.job_type}" if args.job_type else "all job types"
    print(f"Counts by status ({scope}):")
    for status in ("pending", "running", "retrying", "completed", "failed"):
        print(f"  {status:>10}: {counts.get(status, 0)}")

    if args.status:
        print(f"\nMost recent {args.limit} job(s) with status={args.status}:")
        for job in manager.list_jobs(job_type=args.job_type, status=args.status, limit=args.limit):
            print(f"  #{job.id} {job.job_type} attempts={job.attempts}/{job.max_attempts} payload={job.payload} last_error={job.last_error[:200]!r}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
