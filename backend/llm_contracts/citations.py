"""U5 — provenance for facts shown to the learner.

Rule: a fact shown to the user carries its provenance in `fuente:id`
format (e.g. `wikipedia:Photosynthesis`, `arxiv:quantum-tunneling`);
without provenance it is not shown. `require_citations()` is the
fail-fast gate — it THROWS, so an unattributed finding cannot be
persisted or served by accident.

U3 companion rule, enforced by construction: provenance is COMPUTED from
the retrieval step (see grounding_citations), never extracted from the
LLM's own output — asking the model "cite your sources" just produces
plausible-looking fabricated citations.
"""

from __future__ import annotations

import re

# Machine citation format: `fuente:id` — lowercase source namespace, then
# an id slug. Mirrors the roi-engine CITATION_RE from the reference
# standard.
CITATION_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*:[A-Za-z0-9][A-Za-z0-9_.\-/]*$")


class CitationError(ValueError):
    """Raised when a finding lacks the required provenance."""


def is_valid_citation(citation: str) -> bool:
    return bool(CITATION_RE.match(citation))


def source_to_citation(source: str) -> str:
    """Normalizes an evidence source id to `fuente:id` form. Sources
    already in `a:b` form pass through; `a.b.c` becomes `a:b.c`."""
    if ":" in source:
        return source
    dot = source.find(".")
    if dot > 0:
        return f"{source[:dot]}:{source[dot + 1:]}"
    return source


def _slugify(title: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9]+", "-", title.strip()).strip("-")
    return slug[:80]


def grounding_citations(context: str, source: str) -> list[str]:
    """Derives citations from RAG grounding text — PURE and deterministic.

    Both rag.py formatters emit one `- {title}: {summary}` line per source,
    so the titles are recoverable without a second network call and
    without trusting the LLM. Returns `["wikipedia:Photosynthesis", …]`,
    deduplicated, in order. Anything that doesn't parse is skipped, never
    guessed.
    """
    seen: set[str] = set()
    out: list[str] = []
    for line in context.splitlines():
        line = line.strip()
        if not line.startswith("- "):
            continue
        title = line[2:].split(":", 1)[0].strip()
        slug = _slugify(title)
        if not slug:
            continue
        citation = f"{source}:{slug}"
        if is_valid_citation(citation) and citation not in seen:
            seen.add(citation)
            out.append(citation)
    return out


def require_citations(
    findings: list[dict], min_citations: int = 3, *, label_key: str = "label"
) -> None:
    """Fail-fast U5 gate: every finding must carry at least `min_citations`
    valid `fuente:id` citations. Raises CitationError otherwise — the
    caller must refuse to persist or serve the finding. Each finding is a
    dict with a label and a `citations` list."""
    for finding in findings:
        label = finding.get(label_key, "?")
        citations = finding.get("citations") or []
        invalid = [c for c in citations if not is_valid_citation(c)]
        if len(citations) < min_citations or invalid:
            raise CitationError(
                f"CITATIONS_REQUIRED: {label!r} has {len(citations)} citations "
                f"(need >= {min_citations}; invalid: {invalid})"
            )
