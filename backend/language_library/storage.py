"""Storage for the pre-generated language library — reuses
academy_library.storage.FileSystemAcademyStore as-is rather than writing a
second, near-identical implementation: that store's interface was already
generic (a namespace id, a level string, and an item id, all just
strings), so the only thing genuinely different here is which directory it
points at and how a "namespace" is spelled for this domain.

Key mapping onto the reused (field_id, level, course_id) shape:
    field_id  -> language_pair_key(target_lang, native_lang), e.g. "en:es"
    level     -> CEFR level string ("A1", "A2", ...)
    course_id -> unit id (e.g. "A1-0")
"""

from __future__ import annotations

from ..academy_library.storage import FileSystemAcademyStore


def language_pair_key(target_lang: str, native_lang: str) -> str:
    return f"{target_lang}:{native_lang}"


_default_store: FileSystemAcademyStore | None = None


def get_default_store() -> FileSystemAcademyStore:
    """The store every request-path caller (routers/lessons.py) uses —
    lazily constructed so importing this module never touches settings or
    the filesystem. Tests should construct their own
    FileSystemAcademyStore(tmp_path) instead of calling this."""
    global _default_store
    if _default_store is None:
        from ..config import settings

        _default_store = FileSystemAcademyStore(settings.language_library_dir)
    return _default_store
