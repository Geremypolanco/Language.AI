"""Tests for backend/cache_gc.py — pure filesystem logic, no network."""

import os
import time

from backend import cache_gc


def _write_file(path: str, size: int, atime_offset: float) -> None:
    with open(path, "wb") as f:
        f.write(b"x" * size)
    now = time.time()
    os.utime(path, (now - atime_offset, now - atime_offset))


def test_enforce_cache_budget_does_nothing_under_budget(tmp_path):
    _write_file(str(tmp_path / "a.bin"), 100, atime_offset=10)

    freed = cache_gc.enforce_cache_budget(max_bytes=1_000_000, cache_dir=str(tmp_path))

    assert freed == 0
    assert (tmp_path / "a.bin").exists()


def test_enforce_cache_budget_evicts_oldest_accessed_first(tmp_path):
    # oldest -> newest by access time
    _write_file(str(tmp_path / "oldest.bin"), 500, atime_offset=300)
    _write_file(str(tmp_path / "middle.bin"), 500, atime_offset=200)
    _write_file(str(tmp_path / "newest.bin"), 500, atime_offset=100)

    freed = cache_gc.enforce_cache_budget(max_bytes=1000, cache_dir=str(tmp_path))

    assert freed == 500
    assert not (tmp_path / "oldest.bin").exists()
    assert (tmp_path / "middle.bin").exists()
    assert (tmp_path / "newest.bin").exists()


def test_enforce_cache_budget_evicts_across_subdirectories(tmp_path):
    subdir = tmp_path / "piper-voices"
    subdir.mkdir()
    _write_file(str(subdir / "old_voice.onnx"), 800, atime_offset=500)
    _write_file(str(tmp_path / "recent.jpg"), 800, atime_offset=10)

    freed = cache_gc.enforce_cache_budget(max_bytes=1000, cache_dir=str(tmp_path))

    assert freed == 800
    assert not (subdir / "old_voice.onnx").exists()
    assert (tmp_path / "recent.jpg").exists()
