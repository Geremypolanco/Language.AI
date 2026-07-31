#!/usr/bin/env python3
"""Concurrency stress test for the academic mastery fast-track path
(backend/mastery.py, exercised through POST /{user_id}/courses/{course_id}/ask).

Simulates 50 students hitting that endpoint concurrently, each producing a
genuine 3-turn mastery streak, and checks for the failure modes that would
actually matter at higher user counts: exceptions, lost writes, or
duplicated academy_mastery_log/academy_course_progress rows.

Honest scope note: backend/db.py serializes every db.cursor() call behind a
single process-wide threading.RLock (see db.py's `_lock`) — by design, not
by accident, since SQLite (the default local backend) only supports one
writer at a time. That means this script can't "deadlock the database" the
way a naive multi-connection stress test might; a deadlock would require
two independent lock-acquisition orders, and there's only ever one lock
here. What it actually validates is that 50 concurrent async requests, each
making several serialized round-trips through that lock, all complete
correctly and promptly — no exceptions, no lost writes, no duplicate rows —
which is the real risk surface for this feature, not raw DB engine
concurrency.

Uses asyncio.gather over an in-process ASGI transport rather than
pytest-asyncio or a live HTTP server — no test framework or open port
needed, and it stays runnable as a plain script. hf_client.conversation_reply
is monkeypatched to a deterministic, near-instant fake so this runs fully
offline, consistent with the rest of this codebase's "runs without
HF_TOKEN" philosophy — it stress-tests this app's own concurrency handling,
not Hugging Face's.

Usage:
    python scripts/stress_test_academy.py [--students N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx  # noqa: E402

from backend import academy, db  # noqa: E402
from backend.hf_client import hf_client  # noqa: E402
from backend.main import app  # noqa: E402

STRONG_METRICS = {"academic_depth_score": 97, "structural_logical_fallacies": []}
MASTERY_STREAK_TURNS = 3


async def _fake_conversation_reply(system_prompt: str, history: list[dict], temperature: float = 0.8) -> dict:
    return {"spoken_response": "Excelente razonamiento — sigamos.", "critique_metrics": dict(STRONG_METRICS)}


async def _run_one_student(client: httpx.AsyncClient, index: int, field_id: str, course_id: str) -> dict:
    email = f"stress-student-{index}@example.com"
    t0 = time.monotonic()

    r = await client.get("/auth/dev-login", params={"email": email}, follow_redirects=False)
    if r.status_code != 303:
        raise RuntimeError(f"dev-login failed for student {index}: {r.status_code} {r.text}")

    r = await client.post(
        "/api/users",
        json={
            "display_name": f"Student {index}",
            "native_lang": "English",
            "target_lang": "Spanish",
            "level": "B1",
            "interests": [],
        },
    )
    if r.status_code != 200:
        raise RuntimeError(f"onboarding failed for student {index}: {r.status_code} {r.text}")
    user_id = r.json()["id"]

    r = await client.post(f"/api/academy/{user_id}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})
    if r.status_code != 200:
        raise RuntimeError(f"enroll failed for student {index}: {r.status_code} {r.text}")

    last_promotion = None
    for turn in range(MASTERY_STREAK_TURNS):
        r = await client.post(
            f"/api/academy/{user_id}/courses/{course_id}/ask", json={"question": f"Explain concept #{turn}."}
        )
        if r.status_code != 200:
            raise RuntimeError(f"/ask failed for student {index} turn {turn}: {r.status_code} {r.text}")
        last_promotion = r.json()["promotion"]

    return {
        "user_id": user_id,
        "elapsed_s": time.monotonic() - t0,
        "fast_tracked": last_promotion["course_fast_tracked"] if last_promotion else False,
    }


async def main(num_students: int) -> int:
    db.reset_for_tests("/tmp/lingua-stress-test.db")
    original_conversation_reply = hf_client.conversation_reply
    hf_client.conversation_reply = _fake_conversation_reply

    field = academy.all_fields()[0]
    course_id = f"{field.id}:ASSOCIATE:0"
    transport = httpx.ASGITransport(app=app)
    # One AsyncClient per student — the session cookie dev-login sets is
    # per-user, so a shared client/cookie-jar would have students collide.
    clients = [httpx.AsyncClient(transport=transport, base_url="http://stress-test") for _ in range(num_students)]

    try:
        start = time.monotonic()
        results = await asyncio.gather(
            *(_run_one_student(client, i, field.id, course_id) for i, client in enumerate(clients)),
            return_exceptions=True,
        )
        total_elapsed = time.monotonic() - start
    finally:
        await asyncio.gather(*(client.aclose() for client in clients))
        hf_client.conversation_reply = original_conversation_reply

    failures = [r for r in results if isinstance(r, Exception)]
    successes = [r for r in results if not isinstance(r, Exception)]

    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM academy_mastery_log")
        mastery_rows = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM academy_course_progress")
        progress_rows = cur.fetchone()["n"]

    elapsed_values = [r["elapsed_s"] for r in successes]
    summary = {
        "concurrent_students": num_students,
        "succeeded": len(successes),
        "failed": len(failures),
        "total_wall_time_s": round(total_elapsed, 3),
        "per_student_elapsed_s": {
            "min": round(min(elapsed_values), 3) if elapsed_values else None,
            "max": round(max(elapsed_values), 3) if elapsed_values else None,
            "mean": round(statistics.mean(elapsed_values), 3) if elapsed_values else None,
        },
        "all_fast_tracked": bool(successes) and all(r["fast_tracked"] for r in successes),
        "academy_mastery_log_rows": mastery_rows,
        "academy_mastery_log_rows_expected": num_students * MASTERY_STREAK_TURNS,
        "academy_course_progress_rows": progress_rows,
        "academy_course_progress_rows_expected": num_students,
    }
    print(json.dumps(summary, indent=2))

    ok = True
    if failures:
        ok = False
        print(f"\n{len(failures)} student(s) raised an exception:", file=sys.stderr)
        for f in failures[:5]:
            print(f"  {type(f).__name__}: {f}", file=sys.stderr)
    if mastery_rows != summary["academy_mastery_log_rows_expected"]:
        ok = False
        print("\nacademy_mastery_log row count mismatch — a write was lost or duplicated under concurrency.", file=sys.stderr)
    if progress_rows != summary["academy_course_progress_rows_expected"]:
        ok = False
        print("\nacademy_course_progress row count mismatch — a write was lost or duplicated under concurrency.", file=sys.stderr)

    if ok:
        print("\nOK: no exceptions, no lost/duplicated writes under concurrent load.")
    return 0 if ok else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--students", type=int, default=50, help="Number of concurrent simulated students (default 50).")
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.students)))
