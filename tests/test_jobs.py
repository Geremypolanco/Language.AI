"""Tests for the persistent job-queue infrastructure (backend/jobs/) that
replaced "run a build script over flyctl ssh console and hope the
session survives" — see backend/jobs/__init__.py's module docstring for
the overall shape (JobManager -> registry -> worker -> executors)."""

from __future__ import annotations

import asyncio
import hashlib
import os

import pytest

from backend.jobs import manager, model_manager, registry, scanner, worker
from backend.jobs.models import JobStatus


# ── JobManager ───────────────────────────────────────────────────────────


def test_enqueue_creates_a_pending_job():
    job = manager.enqueue("audio_unit", {"unit_id": "A1-0"}, dedupe_key="dk-1")
    assert job.status == JobStatus.PENDING
    assert job.attempts == 0
    assert job.payload == {"unit_id": "A1-0"}


def test_enqueue_is_idempotent_for_a_pending_job():
    first = manager.enqueue("audio_unit", {"unit_id": "A1-0"}, dedupe_key="dk-2")
    second = manager.enqueue("audio_unit", {"unit_id": "A1-0", "different": "payload"}, dedupe_key="dk-2")
    assert first.id == second.id
    assert second.payload == {"unit_id": "A1-0"}  # untouched — the original payload wins
    assert len(manager.list_jobs(job_type="audio_unit")) == 1


def test_enqueue_resets_a_previously_failed_job():
    job = manager.enqueue("audio_unit", {"unit_id": "A1-0"}, dedupe_key="dk-3", max_attempts=1)
    manager.fail(job.id, "boom", job.attempts, job.max_attempts)
    assert manager.get_job(job.id).status == JobStatus.FAILED

    re_enqueued = manager.enqueue("audio_unit", {"unit_id": "A1-0"}, dedupe_key="dk-3")
    assert re_enqueued.id == job.id
    assert re_enqueued.status == JobStatus.PENDING
    assert re_enqueued.attempts == 0
    assert re_enqueued.last_error == ""


def test_claim_next_returns_none_when_queue_empty():
    assert manager.claim_next(["audio_unit"]) is None


def test_claim_next_claims_oldest_pending_job_of_matching_type():
    manager.enqueue("audio_unit", {}, dedupe_key="dk-a")
    manager.enqueue("some_other_type", {}, dedupe_key="dk-b")
    job = manager.claim_next(["audio_unit"])
    assert job is not None
    assert job.dedupe_key == "dk-a"
    assert job.status == JobStatus.RUNNING
    assert manager.claim_next(["audio_unit"]) is None  # already claimed, nothing else matches


def test_claim_next_does_not_claim_a_job_whose_run_after_is_in_the_future():
    job = manager.enqueue("audio_unit", {}, dedupe_key="dk-future", max_attempts=5)
    manager.fail(job.id, "transient", job.attempts, job.max_attempts)  # -> retrying, run_after in the future
    assert manager.get_job(job.id).status == JobStatus.RETRYING
    assert manager.claim_next(["audio_unit"]) is None


def test_complete_marks_a_claimed_job_completed():
    job = manager.enqueue("audio_unit", {}, dedupe_key="dk-complete")
    claimed = manager.claim_next(["audio_unit"])
    manager.complete(claimed.id)
    assert manager.get_job(job.id).status == JobStatus.COMPLETED


def test_fail_retries_until_max_attempts_then_gives_up():
    job = manager.enqueue("audio_unit", {}, dedupe_key="dk-retry", max_attempts=2)
    manager.fail(job.id, "first failure", attempts=0, max_attempts=2)
    after_first = manager.get_job(job.id)
    assert after_first.status == JobStatus.RETRYING
    assert after_first.attempts == 1

    manager.fail(job.id, "second failure", attempts=1, max_attempts=2)
    after_second = manager.get_job(job.id)
    assert after_second.status == JobStatus.FAILED
    assert after_second.attempts == 2
    assert "second failure" in after_second.last_error


# ── Worker loop ──────────────────────────────────────────────────────────


def test_run_once_returns_false_when_nothing_to_claim():
    assert asyncio.run(worker.run_once(["nonexistent_type"])) is False


def test_run_once_executes_and_completes_a_registered_job(monkeypatch):
    calls = []

    async def fake_executor(payload):
        calls.append(payload)
        return {"ok": True}

    registry.register("test_job_type", fake_executor, lambda result: [])
    job = manager.enqueue("test_job_type", {"x": 1}, dedupe_key="dk-worker-ok")

    worked = asyncio.run(worker.run_once(["test_job_type"]))
    assert worked is True
    assert calls == [{"x": 1}]
    assert manager.get_job(job.id).status == JobStatus.COMPLETED


def test_run_once_fails_the_job_when_the_executor_raises():
    async def exploding_executor(payload):
        raise ValueError("synthesis failed")

    registry.register("test_job_type_explode", exploding_executor, lambda result: [])
    job = manager.enqueue("test_job_type_explode", {}, dedupe_key="dk-worker-explode", max_attempts=1)

    asyncio.run(worker.run_once(["test_job_type_explode"]))
    updated = manager.get_job(job.id)
    assert updated.status == JobStatus.FAILED
    assert "synthesis failed" in updated.last_error


def test_run_once_fails_the_job_when_the_validator_rejects_the_result():
    async def executor(payload):
        return {"bad": "shape"}

    registry.register("test_job_type_invalid", executor, lambda result: ["missing required field"])
    job = manager.enqueue("test_job_type_invalid", {}, dedupe_key="dk-worker-invalid", max_attempts=1)

    asyncio.run(worker.run_once(["test_job_type_invalid"]))
    updated = manager.get_job(job.id)
    assert updated.status == JobStatus.FAILED
    assert "missing required field" in updated.last_error


def test_run_once_fails_immediately_for_an_unregistered_job_type():
    job = manager.enqueue("nobody_registered_this", {}, dedupe_key="dk-unregistered", max_attempts=1)
    asyncio.run(worker.run_once(["nobody_registered_this"]))
    assert manager.get_job(job.id).status == JobStatus.FAILED


# ── Model Manager (resumable, verified, download-once) ──────────────────


class _FakeStreamResponse:
    def __init__(self, status_code: int, headers: dict, chunks: list[bytes]):
        self.status_code = status_code
        self.headers = headers
        self._chunks = chunks

    async def aiter_bytes(self, chunk_size: int = 1024 * 1024):
        for chunk in self._chunks:
            yield chunk


class _FakeStreamContextManager:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, *exc_info):
        return False


def test_ensure_file_downloads_and_verifies_matching_etag(tmp_path, monkeypatch):
    content = b"fake model weights " * 10
    etag = hashlib.sha256(content).hexdigest()

    def fake_stream(method, url, headers=None):
        return _FakeStreamContextManager(_FakeStreamResponse(200, {"etag": etag}, [content]))

    monkeypatch.setattr(model_manager._http, "stream", fake_stream)
    dest = str(tmp_path / "model.bin")

    ok = asyncio.run(model_manager.ensure_file("https://example.test/model.bin", dest))
    assert ok is True
    assert open(dest, "rb").read() == content
    assert os.path.exists(f"{dest}.meta.json")
    assert not os.path.exists(f"{dest}.part")


def test_ensure_file_rejects_checksum_mismatch(tmp_path, monkeypatch):
    content = b"fake model weights"
    wrong_etag = hashlib.sha256(b"different content entirely").hexdigest()

    def fake_stream(method, url, headers=None):
        return _FakeStreamContextManager(_FakeStreamResponse(200, {"etag": wrong_etag}, [content]))

    monkeypatch.setattr(model_manager._http, "stream", fake_stream)
    dest = str(tmp_path / "model.bin")

    ok = asyncio.run(model_manager.ensure_file("https://example.test/model.bin", dest))
    assert ok is False
    assert not os.path.exists(dest)


def test_ensure_file_returns_false_on_http_error(tmp_path, monkeypatch):
    def fake_stream(method, url, headers=None):
        return _FakeStreamContextManager(_FakeStreamResponse(404, {}, []))

    monkeypatch.setattr(model_manager._http, "stream", fake_stream)
    dest = str(tmp_path / "model.bin")

    ok = asyncio.run(model_manager.ensure_file("https://example.test/model.bin", dest))
    assert ok is False


def test_ensure_file_reuses_already_verified_file_without_network(tmp_path, monkeypatch):
    dest = tmp_path / "model.bin"
    content = b"already here"
    dest.write_bytes(content)
    sidecar = tmp_path / "model.bin.meta.json"
    sidecar.write_text(f'{{"url": "x", "size": {len(content)}, "etag": ""}}')

    def explode(*args, **kwargs):
        raise AssertionError("must not touch the network for an already-verified file")

    monkeypatch.setattr(model_manager._http, "stream", explode)
    ok = asyncio.run(model_manager.ensure_file("https://example.test/model.bin", str(dest)))
    assert ok is True


def test_ensure_file_resumes_a_partial_download(tmp_path, monkeypatch):
    already_have = b"first half "
    the_rest = b"second half"
    full_content = already_have + the_rest
    etag = hashlib.sha256(full_content).hexdigest()

    dest = tmp_path / "model.bin"
    part = tmp_path / "model.bin.part"
    part.write_bytes(already_have)

    seen_headers = {}

    def fake_stream(method, url, headers=None):
        seen_headers.update(headers or {})
        return _FakeStreamContextManager(_FakeStreamResponse(206, {"etag": etag}, [the_rest]))

    monkeypatch.setattr(model_manager._http, "stream", fake_stream)
    ok = asyncio.run(model_manager.ensure_file("https://example.test/model.bin", str(dest)))

    assert ok is True
    assert seen_headers.get("Range") == f"bytes={len(already_have)}-"
    assert dest.read_bytes() == full_content


# ── Scanner ──────────────────────────────────────────────────────────────


def test_scan_missing_audio_enqueues_jobs_for_gaps_and_skips_pairs_without_metadata(tmp_path, monkeypatch):
    from backend.config import settings
    from backend.curriculum import units_for_level as real_units_for_level
    from backend.language_library import build as language_build
    from backend.language_library.storage import FileSystemAcademyStore, language_pair_key
    from backend.models import CEFRLevel

    object.__setattr__(settings, "language_library_dir", str(tmp_path))
    store = FileSystemAcademyStore(str(tmp_path))
    monkeypatch.setattr(
        "backend.language_library.build.curriculum.units_for_level",
        lambda level: real_units_for_level(level)[0:1],
    )

    pair_key = language_pair_key("English", "Spanish")
    unit_id = real_units_for_level(CEFRLevel.A1)[0].id
    store.save_course_asset(
        pair_key, "A1", "v1", unit_id, "content",
        [
            {
                "id": "ex-0", "type": "vocab_intro", "prompt": "p", "target_text": "hola", "native_text": "hello",
                "options": [], "correct_answer": "hola", "image_prompt": "", "audio_text": "hola", "audio_url": "",
                "vocab_key": "greetings.hello",
            },
        ],
    )
    store.set_latest_version(pair_key, "A1", "v1")
    language_build._ensure_pair_metadata(store, pair_key, "English", "Spanish")

    # A second pair built by a hypothetical older version of this app,
    # before pair_meta.json existed — must be skipped, not crash the scan.
    no_meta_pair = language_pair_key("French", "German")
    store.save_course_asset(no_meta_pair, "A1", "v1", unit_id, "content", [])
    store.set_latest_version(no_meta_pair, "A1", "v1")

    scanned = asyncio.run(scanner.scan_missing_audio())
    assert scanned == 1  # only the pair with metadata was scannable

    from backend.jobs import manager as job_manager

    jobs = job_manager.list_jobs(job_type="audio_unit")
    assert len(jobs) == 1
    assert jobs[0].payload["pair_key"] == pair_key
    assert jobs[0].payload["target_lang"] == "English"
