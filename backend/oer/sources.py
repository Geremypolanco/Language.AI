"""Connectors that fetch real OER source documents for ingestion.

Each one maps to a source family from the "movimiento REA/OER" brief this
pipeline implements:

- `fetch_arxiv` — live, public, no-auth query against arXiv's Atom API.
  Grounds Master/Doctorate-depth content in technical/scientific fields
  with real paper titles and abstracts.
- `load_local_folder` — the practical integration point for source families
  whose real content ships as a bulk export rather than a small ergonomic
  API: MIT OpenCourseWare syllabi, OpenStax chapter exports, OER Commons/
  Hugging Face "OER"-tagged dataset dumps, OpenLearn units, PubMed Central
  full-text bulk sets, SciELO article exports. Download the source's own
  export once, drop the files under data/oer_raw/<field_id>/, and this
  loader picks them up — see scripts/ingest_oer.py --source folder.
- `load_seed_dataset` — ESCO (EU skills taxonomy), O*NET (US occupation
  database) and Kaggle/UCI (practical project datasets) each gate their
  full corpus behind a bulk CSV/RDF download or a registration-gated API.
  Rather than fake a live call against them, this ships a small, real,
  hand-picked sample per family (seed_data/*.json) so the pipeline has
  something genuine to retrieve today; swap in the full official dump via
  load_local_folder once you've downloaded it.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field as dc_field
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger("lingua.oer.sources")

_SEED_DIR = Path(__file__).resolve().parent / "seed_data"
_ARXIV_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass
class OERDocument:
    id: str
    title: str
    text: str
    source: str  # "arxiv" | "openstax" | "mit_ocw" | "esco" | "onet" | "kaggle_uci" | ...
    url: str
    field_id: str | None = None
    level_tags: list[str] = dc_field(default_factory=list)  # AcademicLevel values; empty = any level


async def fetch_arxiv(query: str, field_id: str | None = None, max_results: int = 10) -> list[OERDocument]:
    """Live query against arXiv's public Atom API (export.arxiv.org) — no
    API key required. Best suited to Master/Doctorate-depth grounding in
    technical and scientific fields."""
    params = {"search_query": f"all:{query}", "start": "0", "max_results": str(max_results)}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get("https://export.arxiv.org/api/query", params=params)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    docs = []
    for entry in root.findall("atom:entry", _ARXIV_NS):
        arxiv_id = (entry.findtext("atom:id", default="", namespaces=_ARXIV_NS) or "").strip()
        title = " ".join((entry.findtext("atom:title", default="", namespaces=_ARXIV_NS) or "").split())
        summary = " ".join((entry.findtext("atom:summary", default="", namespaces=_ARXIV_NS) or "").split())
        if not arxiv_id or not summary:
            continue
        docs.append(
            OERDocument(
                id=f"arxiv:{arxiv_id.rsplit('/', 1)[-1]}",
                title=title,
                text=f"{title}\n\n{summary}",
                source="arxiv",
                url=arxiv_id,
                field_id=field_id,
                level_tags=["MASTER", "DOCTORATE"],
            )
        )
    return docs


def load_local_folder(path: str | Path, field_id: str | None = None, source: str = "local") -> list[OERDocument]:
    """Reads every .txt/.md/.json file under `path` as one or more OER
    documents. A .json file may contain a list of
    `{"id", "title", "text", "url"}` objects (e.g. a dataset exported to
    JSON); .txt/.md files each become one document, titled by filename."""
    base = Path(path)
    docs: list[OERDocument] = []
    if not base.exists():
        return docs

    for file in sorted(base.rglob("*")):
        if not file.is_file():
            continue
        if file.suffix == ".json":
            try:
                items = json.loads(file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("Skipping unreadable OER JSON file %s", file)
                continue
            for item in items if isinstance(items, list) else [items]:
                text = item.get("text", "")
                if not text:
                    continue
                docs.append(
                    OERDocument(
                        id=f"{source}:{item.get('id', file.stem)}",
                        title=item.get("title", file.stem),
                        text=text,
                        source=source,
                        url=item.get("url", ""),
                        field_id=field_id,
                    )
                )
        elif file.suffix in (".txt", ".md"):
            text = file.read_text(encoding="utf-8", errors="ignore").strip()
            if not text:
                continue
            docs.append(
                OERDocument(
                    id=f"{source}:{file.stem}",
                    title=file.stem.replace("_", " ").replace("-", " ").title(),
                    text=text,
                    source=source,
                    url="",
                    field_id=field_id,
                )
            )
    return docs


def list_seed_datasets() -> list[str]:
    if not _SEED_DIR.exists():
        return []
    return sorted(p.stem for p in _SEED_DIR.glob("*.json"))


def load_seed_dataset(name: str, field_id: str | None = None) -> list[OERDocument]:
    """Loads one of the small, hand-curated seed corpora shipped in
    seed_data/ — real entries standing in for the full official bulk
    exports until those are downloaded and pointed at via
    load_local_folder instead."""
    path = _SEED_DIR / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"No seed dataset named {name!r} in {_SEED_DIR}")
    items = json.loads(path.read_text(encoding="utf-8"))
    return [
        OERDocument(
            id=f"{name}:{item['id']}",
            title=item["title"],
            text=item["text"],
            source=item.get("source", name),
            url=item.get("url", ""),
            field_id=field_id or item.get("field_id"),
        )
        for item in items
    ]
