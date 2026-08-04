"""Permanent, versioned storage for pre-generated academic content — the
persistence layer behind build.py's build pipeline.

Deliberately NOT a SQL schema or a specific cloud backend: AcademyStore is a
small Protocol any storage engine can implement (local files, Postgres,
Firestore, S3, ...) so swapping the backend later never touches the build
pipeline or the API router, only which store gets constructed at startup.
FileSystemAcademyStore is the only implementation shipped here — plain JSON
files, since content is generated once at build time and only ever read (
never written) at request time, so there is no concurrency/transaction need
a database would actually justify. A PostgresAcademyStore/FirestoreAcademyStore
implementing the same methods is a drop-in swap whenever that need shows up.

Disk layout (FileSystemAcademyStore), rooted at settings.academy_library_dir:

    <field_id>/<level>/<version>/curriculum.json
    <field_id>/<level>/<version>/courses/<course_id>.json              (modules)
    <field_id>/<level>/<version>/courses/<course_id>.glossary.json
    <field_id>/<level>/<version>/courses/<course_id>.quiz.json
    <field_id>/<level>/<version>/courses/<course_id>.exam.json
    <field_id>/<level>/<version>/courses/<course_id>.assignments.json
    <field_id>/<level>/<version>/courses/<course_id>.scenario.json
    <field_id>/<level>/latest.txt        <- just the current version string

`latest.txt` is what makes versioning atomic from a reader's point of view:
a rebuild writes an entirely new <version> directory tree first, and only
flips latest.txt to point at it once every course in that version saved
successfully — a reader never sees a half-written version, and rolling back
is just pointing latest.txt at the previous version string again.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Protocol


class AcademyStore(Protocol):
    def save_curriculum(self, field_id: str, level: str, version: str, data: dict) -> None: ...

    def load_curriculum(self, field_id: str, level: str, version: str | None = None) -> dict | None: ...

    def save_course_asset(
        self, field_id: str, level: str, version: str, course_id: str, kind: str, data: Any
    ) -> None: ...

    def load_course_asset(
        self, field_id: str, level: str, course_id: str, kind: str, version: str | None = None
    ) -> Any | None: ...

    def get_latest_version(self, field_id: str, level: str) -> str | None: ...

    def set_latest_version(self, field_id: str, level: str, version: str) -> None: ...

    def is_built(self, field_id: str, level: str) -> bool: ...


# Every non-"content" course asset is saved as "<course_id>.<kind>.json" so
# the 6+ files belonging to one course sort and glob together on disk; the
# base module content keeps the bare "<course_id>.json" name since it's the
# asset every course has always had, from before this library existed.
_KIND_SUFFIX = {
    "content": "",
    "glossary": ".glossary",
    "quiz": ".quiz",
    "exam": ".exam",
    "assignments": ".assignments",
    "scenario": ".scenario",
}


def _safe_component(value: str) -> str:
    """Course ids look like "computer-science:BACHELOR:3" — ':' is valid on
    Linux but not worth risking on every possible future storage backend
    (Windows dev machines, some cloud object stores' key conventions), so
    filenames use a sanitized form throughout this module."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)


class FileSystemAcademyStore:
    def __init__(self, base_dir: str) -> None:
        self.base_dir = base_dir

    def _field_level_dir(self, field_id: str, level: str) -> str:
        return os.path.join(self.base_dir, _safe_component(field_id), _safe_component(level))

    def _version_dir(self, field_id: str, level: str, version: str) -> str:
        return os.path.join(self._field_level_dir(field_id, level), _safe_component(version))

    def _latest_path(self, field_id: str, level: str) -> str:
        return os.path.join(self._field_level_dir(field_id, level), "latest.txt")

    def get_latest_version(self, field_id: str, level: str) -> str | None:
        path = self._latest_path(field_id, level)
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            version = f.read().strip()
        return version or None

    def set_latest_version(self, field_id: str, level: str, version: str) -> None:
        path = self._latest_path(field_id, level)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(version)

    def is_built(self, field_id: str, level: str) -> bool:
        return self.get_latest_version(field_id, level) is not None

    def _resolve_version(self, field_id: str, level: str, version: str | None) -> str | None:
        return version or self.get_latest_version(field_id, level)

    def save_curriculum(self, field_id: str, level: str, version: str, data: dict) -> None:
        version_dir = self._version_dir(field_id, level, version)
        os.makedirs(version_dir, exist_ok=True)
        with open(os.path.join(version_dir, "curriculum.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_curriculum(self, field_id: str, level: str, version: str | None = None) -> dict | None:
        resolved = self._resolve_version(field_id, level, version)
        if resolved is None:
            return None
        path = os.path.join(self._version_dir(field_id, level, resolved), "curriculum.json")
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def save_course_asset(
        self, field_id: str, level: str, version: str, course_id: str, kind: str, data: Any
    ) -> None:
        suffix = _KIND_SUFFIX[kind]
        courses_dir = os.path.join(self._version_dir(field_id, level, version), "courses")
        os.makedirs(courses_dir, exist_ok=True)
        path = os.path.join(courses_dir, f"{_safe_component(course_id)}{suffix}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load_course_asset(
        self, field_id: str, level: str, course_id: str, kind: str, version: str | None = None
    ) -> Any | None:
        resolved = self._resolve_version(field_id, level, version)
        if resolved is None:
            return None
        suffix = _KIND_SUFFIX[kind]
        path = os.path.join(
            self._version_dir(field_id, level, resolved), "courses", f"{_safe_component(course_id)}{suffix}.json"
        )
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)


_default_store: FileSystemAcademyStore | None = None


def get_default_store() -> FileSystemAcademyStore:
    """The store every request-path caller (routers/academy.py) uses —
    lazily constructed so importing this module never touches settings or
    the filesystem, and easy to bypass in tests by constructing your own
    FileSystemAcademyStore(tmp_path) instead of calling this."""
    global _default_store
    if _default_store is None:
        from ..config import settings

        _default_store = FileSystemAcademyStore(settings.academy_library_dir)
    return _default_store
