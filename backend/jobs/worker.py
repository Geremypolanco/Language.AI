"""The loop that claims and executes jobs — the "Worker Scheduler".

Runs as a background asyncio task inside the same process as the HTTP
server today (see main.py's lifespan), which is the honest choice for
this app's actual deployment (one Fly machine, no separately-provisioned
worker fleet) rather than a distributed-systems setup nothing here needs
yet. It is NOT coupled to that topology: run_worker_loop takes no
dependency on FastAPI or the HTTP server at all, so scripts/run_worker.py
runs the exact same loop as its own standalone process — the move to a
dedicated worker machine, if/when this app's actual scale ever justifies
it, is a deployment change (a second Fly process group), not a rewrite.

Multiple callers of run_worker_loop (in-process + a standalone process,
or several standalone processes) polling the same queue concurrently is
safe — see manager.claim_next's docstring on why a lost claim race is a
correct, harmless outcome rather than something this loop needs to avoid."""

from __future__ import annotations

import asyncio
import logging

from . import manager, registry

logger = logging.getLogger("lingua.jobs.worker")


async def run_once(job_types: list[str]) -> bool:
    """Claims and runs at most one job. Returns whether it found one to
    run at all (so the caller's poll loop knows whether to back off)."""
    job = manager.claim_next(job_types)
    if job is None:
        return False

    executor = registry.get_executor(job.job_type)
    if executor is None:
        manager.fail(job.id, f"no executor registered for job_type={job.job_type!r}", job.attempts, job.max_attempts)
        return True

    validator = registry.get_validator(job.job_type)
    try:
        result = await executor(job.payload)
        problems = validator(result) if validator else []
        if problems:
            raise RuntimeError("validation failed: " + "; ".join(problems))
    except Exception as exc:
        manager.fail(job.id, repr(exc), job.attempts, job.max_attempts)
        return True

    manager.complete(job.id)
    logger.info("job %d (%s) completed: %s", job.id, job.job_type, result)
    return True


async def run_worker_loop(job_types: list[str], poll_interval: float = 5.0) -> None:
    """Runs forever (until cancelled) — start this as a background task,
    never awaited to completion. Every iteration is isolated in its own
    try/except so one bad claim/execute cycle can't kill the loop, same
    convention as cache_gc.run_periodic_gc."""
    logger.info("worker loop starting for job types: %s", job_types)
    while True:
        try:
            worked = await run_once(job_types)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("worker loop iteration failed unexpectedly")
            worked = False
        if not worked:
            await asyncio.sleep(poll_interval)
