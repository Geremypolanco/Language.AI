"""Academic knowledge graph: concepts and the relations between them (and
between the courses that teach them).

Concepts are deliberately NOT a new AI-generated content type — they're
derived directly from each course's already-generated, already-validated
glossary (see academy_library). Running a whole extra AI pass just to
extract "concepts" the glossary already names and defines would double a
build's AI-token cost for no real new information. A concept's course_id
column IS its "teaches"/"taught_by" edge — no separate relation row needed
for that — which keeps the graph from getting needlessly dense.

The relation table also holds COURSE-to-COURSE edges (using course ids as
the node id on both sides) — the sequential "prerequisite_of" chain implied
by curriculum order, matching the worked example in the request ("Data
Structures -> Algorithms -> OS -> Distributed Systems -> Cloud Computing").
Cross-field or non-sequential edges (a real curriculum sometimes needs
Statistics before Machine Learning even though they're not adjacent in one
field's own course list) aren't populated yet — that needs either manual
curation or a dedicated AI extraction pass over course content, and is a
clean extension point on top of this same table/relation_type scheme, not
a redesign.
"""

from __future__ import annotations

import re

from .. import db

# Every relation type the request named — build_graph_for_field_level only
# ever writes "prerequisite_of" for now (see module docstring), but the
# table itself and record_relation() below support all of them so a future
# curation/extraction step has somewhere to write without a schema change.
RELATION_TYPES = (
    "prerequisite_of",
    "depends_on",
    "related_to",
    "extends",
    "uses",
    "teaches",
    "reinforces",
)


def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def concept_id(course_id: str, term: str) -> str:
    return f"{course_id}::{_slugify(term)}"


def concepts_from_glossary(field_id: str, course_id: str, glossary: dict) -> list[dict]:
    return [
        {
            "id": concept_id(course_id, t["term"]),
            "field_id": field_id,
            "course_id": course_id,
            "term": t["term"],
            "definition": t["definition"],
        }
        for t in glossary.get("terms", [])
        if t.get("term")
    ]


def save_concepts(concepts: list[dict]) -> None:
    with db.cursor() as cur:
        for c in concepts:
            cur.execute(
                """
                INSERT INTO academic_concept (id, field_id, course_id, term, definition)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT (id) DO UPDATE SET
                    field_id=excluded.field_id, course_id=excluded.course_id,
                    term=excluded.term, definition=excluded.definition
                """,
                (c["id"], c["field_id"], c["course_id"], c["term"], c["definition"]),
            )


def record_relation(from_id: str, to_id: str, relation_type: str) -> None:
    if relation_type not in RELATION_TYPES:
        raise ValueError(f"unknown relation_type: {relation_type!r}")
    with db.cursor() as cur:
        cur.execute(
            """
            INSERT INTO academic_concept_relation (from_concept_id, to_concept_id, relation_type)
            VALUES (?, ?, ?)
            ON CONFLICT (from_concept_id, to_concept_id, relation_type) DO NOTHING
            """,
            (from_id, to_id, relation_type),
        )


def build_graph_for_field_level(field_id: str, level: str, course_ids_in_order: list[str], store) -> int:
    """Populates concepts for every course that has a built glossary, plus
    the sequential prerequisite chain implied by curriculum order. Returns
    how many courses actually contributed concepts (a course whose glossary
    isn't built yet is silently skipped, not an error — the graph fills in
    incrementally as more of the library gets built)."""
    concepts_added = 0
    for i, course_id in enumerate(course_ids_in_order):
        glossary = store.load_course_asset(field_id, level, course_id, "glossary")
        if glossary:
            save_concepts(concepts_from_glossary(field_id, course_id, glossary))
            concepts_added += 1
        if i > 0:
            record_relation(course_ids_in_order[i - 1], course_id, "prerequisite_of")
    return concepts_added


def concepts_for_course(course_id: str) -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, field_id, course_id, term, definition FROM academic_concept WHERE course_id=?",
            (course_id,),
        )
        return [dict(row) for row in cur.fetchall()]


def prerequisite_courses(course_id: str) -> list[str]:
    """Courses that must come before `course_id`, per prerequisite_of edges."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT from_concept_id FROM academic_concept_relation "
            "WHERE to_concept_id=? AND relation_type='prerequisite_of'",
            (course_id,),
        )
        return [row["from_concept_id"] for row in cur.fetchall()]


def get_concept(concept_id: str) -> dict | None:
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, field_id, course_id, term, definition FROM academic_concept WHERE id=?",
            (concept_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def graph_exists_for(field_id: str) -> bool:
    with db.cursor() as cur:
        cur.execute("SELECT 1 FROM academic_concept WHERE field_id=? LIMIT 1", (field_id,))
        return cur.fetchone() is not None
