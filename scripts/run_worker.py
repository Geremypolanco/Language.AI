#!/usr/bin/env python3
"""Standalone job-queue worker process.

backend/main.py already starts this exact loop (backend/jobs/worker.py's
run_worker_loop) as a background task inside the web server process,
which is the right default for this app's actual deployment today (one
Fly machine, no separately-provisioned worker fleet). This script exists
so that default isn't load-bearing: the day this app's scale genuinely
justifies separating job execution from HTTP serving (see backend/jobs/
worker.py's module docstring, and the "separar generación y serving"
requirement it was written for), running this as its own Fly process
group (or any other always-on process) is the same code, unchanged.

Running this *in addition to* main.py's in-process worker is safe (both
just poll the same `jobs` table — see JobManager.claim_next) but
redundant for a single-machine deployment; it isn't the recommended
default, just the escape hatch.

Usage:
    python scripts/run_worker.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.jobs import bootstrap, worker  # noqa: E402

logger = logging.getLogger("lingua.run_worker")


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bootstrap.register_all()
    logger.info("standalone worker starting")
    await worker.run_worker_loop(["audio_unit"])


if __name__ == "__main__":
    asyncio.run(main())
