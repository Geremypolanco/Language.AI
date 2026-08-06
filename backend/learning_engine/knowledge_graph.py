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

import logging
import re
from typing import TYPE_CHECKING

from .. import db
from . import graph_algorithms

if TYPE_CHECKING:
    from ..models import AcademicField, AcademicLevel

logger = logging.getLogger("lingua.knowledge_graph")

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


def concepts_for_field(field_id: str) -> list[dict]:
    """Every concept across every course this field has a built glossary
    for — used by mentor_engine/knowledge_profile.py to build a field-wide
    mastery map without a second per-course loop at the call site."""
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, field_id, course_id, term, definition FROM academic_concept WHERE field_id=?",
            (field_id,),
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


# ── Real DAG traversal (Curriculum Engine Phase 1) ───────────────────────
#
# Everything below builds on the same academic_concept_relation edges above
# — course ids self-describe their owning (field, level) as
# "<field_id>:<level>:<index>", which is what lets these helpers work
# transparently across a specialization's merged curriculum (base field's
# course ids + the specialization's own) without the caller needing to know
# it's actually two field namespaces: just pass the full course id list.


def _field_levels_from_course_ids(course_ids: list[str]) -> set[tuple[str, str]]:
    result: set[tuple[str, str]] = set()
    for cid in course_ids:
        parts = cid.split(":")
        if len(parts) == 3:
            result.add((parts[0], parts[1]))
    return result


def prerequisite_edges_for(course_ids: list[str]) -> list[tuple[str, str]]:
    """Every prerequisite_of edge whose target course belongs to one of the
    (field, level) namespaces implied by `course_ids`. Spans multiple
    fields transparently — pass a specialization's already-merged course id
    list (base field's ids + its own) and edges from both are included."""
    field_levels = _field_levels_from_course_ids(course_ids)
    if not field_levels:
        return []
    edges: list[tuple[str, str]] = []
    with db.cursor() as cur:
        for field_id, level in field_levels:
            cur.execute(
                "SELECT from_concept_id, to_concept_id FROM academic_concept_relation "
                "WHERE relation_type='prerequisite_of' AND to_concept_id LIKE ?",
                (f"{field_id}:{level}:%",),
            )
            edges.extend((row["from_concept_id"], row["to_concept_id"]) for row in cur.fetchall())
    return edges


def topological_course_order(course_ids_in_order: list[str]) -> list[str]:
    """The order a student could actually study these courses in, honoring
    every recorded prerequisite edge — falls back to `course_ids_in_order`
    itself (the curriculum's own generated order) if the graph somehow has
    a cycle, since enrich_prerequisite_graph already refuses to persist any
    edge that would create one; this is a defensive fallback, not the
    expected path."""
    edges = prerequisite_edges_for(course_ids_in_order)
    try:
        return graph_algorithms.topological_order(course_ids_in_order, edges)
    except ValueError:
        logger.exception("Prerequisite graph for %s has a cycle — serving curriculum order instead", course_ids_in_order[:1])
        return course_ids_in_order


def unlocked_courses(user_id: str, course_ids: list[str]) -> set[str]:
    """Courses this student can start right now — everything with no
    unmet prerequisite (see graph_algorithms.locked_courses). A course
    with no recorded prerequisite edges at all is always unlocked, same
    "nothing is locked by default" default the language skill-tree uses."""
    all_ids = set(course_ids)
    edges = prerequisite_edges_for(course_ids)
    completed: set[str] = set()
    with db.cursor() as cur:
        for field_id, level in _field_levels_from_course_ids(course_ids):
            cur.execute(
                "SELECT course_id FROM academy_course_progress WHERE user_id=? AND course_id LIKE ?",
                (user_id, f"{field_id}:{level}:%"),
            )
            completed.update(row["course_id"] for row in cur.fetchall())
    return all_ids - graph_algorithms.locked_courses(all_ids, edges, completed)


def ancestor_closure(course_id: str, course_ids: list[str]) -> set[str]:
    """Every course (direct or transitive) this one requires."""
    return graph_algorithms.ancestors(course_id, prerequisite_edges_for(course_ids))


def unlocks(course_id: str, course_ids: list[str]) -> set[str]:
    """Every course (direct or transitive) that becomes reachable once this
    one is completed — "what does finishing X unlock.\""""
    return graph_algorithms.descendants(course_id, prerequisite_edges_for(course_ids))


async def enrich_prerequisite_graph(
    field: "AcademicField",
    level: "AcademicLevel",
    course_ids_in_order: list[str],
    curriculum_courses: list[dict],
    native_lang: str,
) -> int:
    """AI-driven enrichment on top of the guaranteed sequential baseline
    build_graph_for_field_level already writes (course[i-1] -> course[i]):
    proposes real, non-adjacent prerequisite edges (e.g. "Statistics"
    required by a much-later "Machine Learning" course, not just the one
    immediately before it), and persists only the edges that don't
    introduce a cycle — checked incrementally against the running edge set,
    so one bad proposed edge in the batch doesn't sink the rest of it.

    Never raises: a build must never fail over this enrichment step, since
    the sequential chain alone is already a valid (if less rich) DAG on its
    own. Returns how many new edges were actually recorded."""
    from ..academy_library import generators as academy_generators
    from ..academy_library.generators import GenerationError

    try:
        proposal = await academy_generators.generate_prerequisite_graph(field, level, native_lang, curriculum_courses)
    except GenerationError:
        logger.exception(
            "Prerequisite-graph enrichment failed for %s/%s — sequential baseline stands alone", field.id, level.value
        )
        return 0

    existing_edges = prerequisite_edges_for(course_ids_in_order)
    recorded = 0
    for item in proposal.get("prerequisites", []):
        try:
            from_id = course_ids_in_order[item["requires_index"]]
            to_id = course_ids_in_order[item["course_index"]]
        except (KeyError, IndexError, TypeError):
            continue  # validators.validate_prerequisite_graph already bounds-checks this, but stay defensive
        candidate_edges = existing_edges + [(from_id, to_id)]
        if graph_algorithms.has_cycle(course_ids_in_order, candidate_edges):
            logger.warning(
                "Skipping prerequisite edge %s -> %s for %s/%s: would introduce a cycle", from_id, to_id, field.id, level.value
            )
            continue
        record_relation(from_id, to_id, "prerequisite_of")
        existing_edges = candidate_edges
        recorded += 1
    return recorded
