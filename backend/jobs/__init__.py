"""Persistent job queue infrastructure for the Content Production Pipeline
(see backend/academy_library/ and backend/language_library/'s module
docstrings for the two-phase architecture this plugs into).

Replaces "run a build script over `flyctl ssh console` and hope the
session survives" with: API/scanner enqueues a row in the `jobs` table
(backend/db.py) -> a worker running inside the always-on backend process
(worker.py) claims it whenever it gets to it -> the registered executor
for that job_type (registry.py) does the actual work -> the registered
validator checks the result -> the row is marked completed or, on
failure, retrying (with backoff) or failed. None of this depends on any
particular invoking process staying connected — a build script's job is
just to INSERT rows, which takes milliseconds, not to do the generation
itself.

Modules:
    models.py    - Job, JobStatus
    manager.py   - JobManager: enqueue/claim_next/complete/fail/list_jobs
    registry.py  - per-job_type executor/validator registration
    model_manager.py - resumable, verified, download-once model files
                   (Piper voice models today; the interface isn't Piper-
                   specific — see its own docstring)
    executors/   - one module per job_type's actual generation logic
    scanner.py   - startup/periodic scan for missing assets -> enqueue
    worker.py    - the loop that claims and runs jobs
"""
