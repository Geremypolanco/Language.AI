#!/usr/bin/env python3
"""Admin CLI: materializes backend.personas.build_field_faculty()'s output
into the faculty_directory table (see backend/db.py) for SQL-side admin/BI
queries — "which professor teaches which subject, with which voice."

This table is deliberately NOT the source of truth. The app itself always
computes a field's faculty live, in Python, on every request — that's what
guarantees the mapping can never drift out of sync with the code that
actually assigns personas, and needs no migration when a persona's voice or
philosophy changes. This script exists only so a plain SQL client (e.g. a
BI tool connected to the Supabase Postgres database) can query the mapping
without embedding backend/personas.py's logic itself. Re-run it after any
change to personas.py or academy.py's field list to refresh the snapshot.

Usage:
    python scripts/export_faculty_directory.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import academy, db, personas  # noqa: E402
from backend.hf_client import PARLER_VOICE_SEED  # noqa: E402


def export_faculty_directory() -> int:
    fields = academy.all_fields()
    now = db.now_iso()
    with db.cursor() as cur:
        for field in fields:
            faculty = personas.build_field_faculty(field)
            cur.execute(
                """INSERT INTO faculty_directory
                   (field_id, field_name, category, persona_id, persona_name, persona_title,
                    archetype, correction_focus, motivational_style, voice_description,
                    voice_seed, sampling_temperature, oer_namespace, generated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (field_id) DO UPDATE SET
                       persona_id=excluded.persona_id, persona_name=excluded.persona_name,
                       persona_title=excluded.persona_title, archetype=excluded.archetype,
                       correction_focus=excluded.correction_focus,
                       motivational_style=excluded.motivational_style,
                       voice_description=excluded.voice_description, voice_seed=excluded.voice_seed,
                       sampling_temperature=excluded.sampling_temperature,
                       oer_namespace=excluded.oer_namespace, generated_at=excluded.generated_at""",
                (
                    field.id,
                    field.name,
                    field.category,
                    faculty.id,
                    faculty.name,
                    faculty.title,
                    faculty.archetype,
                    faculty.correction_focus,
                    faculty.motivational_style,
                    faculty.voice_description,
                    PARLER_VOICE_SEED,
                    faculty.sampling_temperature,
                    field.id,  # oer_namespace matches backend/oer/vectorstore.py's field_id metadata filter
                    now,
                ),
            )
    return len(fields)


def main() -> None:
    count = export_faculty_directory()
    print(f"Exported {count} field -> faculty mappings to faculty_directory.")


if __name__ == "__main__":
    main()
