#!/usr/bin/env python3
"""Admin CLI to populate the OER vector store (backend/oer/).

Run from the repo root, with the same environment (HF_TOKEN, etc.) the app
itself uses. This is an offline batch step — it never runs on a user
request path.

Examples:

    # Live arXiv query, grounding Master/Doctorate content for a field
    python scripts/ingest_oer.py arxiv --field-id data-science \\
        --query "machine learning survey" --max-results 15

    # One of the curated seed corpora (ESCO skills, O*NET occupations,
    # Kaggle/UCI datasets) shipped in backend/oer/seed_data/
    python scripts/ingest_oer.py seed --name esco_skills
    python scripts/ingest_oer.py --list-seeds

    # A folder of OpenStax/MIT OCW/OER Commons/etc. exports you downloaded
    # yourself (.txt/.md files, or .json with [{"id","title","text","url"}])
    python scripts/ingest_oer.py folder --path data/oer_raw/economics --field-id economics

    python scripts/ingest_oer.py --status
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.oer import ingest, sources, vectorstore  # noqa: E402


async def _run(args: argparse.Namespace) -> None:
    if args.list_seeds:
        names = sources.list_seed_datasets()
        print("Seed datasets available:" if names else "No seed datasets found.")
        for name in names:
            print(f"  - {name}")
        return

    if args.status:
        print(f"OER vector store: {vectorstore.count()} chunk(s) at {vectorstore.settings.oer_chroma_dir}")
        return

    if args.command == "arxiv":
        docs = await sources.fetch_arxiv(args.query, field_id=args.field_id, max_results=args.max_results)
    elif args.command == "seed":
        docs = sources.load_seed_dataset(args.name, field_id=args.field_id)
    elif args.command == "folder":
        docs = sources.load_local_folder(args.path, field_id=args.field_id, source=args.source_label)
    else:
        raise SystemExit("Choose a command: arxiv | seed | folder (or --list-seeds / --status)")

    if not docs:
        print("No documents found for this source — nothing to ingest.")
        return

    print(f"Fetched {len(docs)} document(s): {', '.join(d.title for d in docs[:5])}"
          f"{' ...' if len(docs) > 5 else ''}")
    chunk_count = await ingest.ingest_documents(docs)
    print(f"Ingested {chunk_count} chunk(s). Vector store now has {vectorstore.count()} chunk(s) total.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list-seeds", action="store_true", help="List the curated seed datasets and exit.")
    parser.add_argument("--status", action="store_true", help="Print the vector store's chunk count and exit.")
    sub = parser.add_subparsers(dest="command")

    p_arxiv = sub.add_parser("arxiv", help="Live query against arXiv's public API.")
    p_arxiv.add_argument("--query", required=True, help="arXiv search query, e.g. 'machine learning survey'.")
    p_arxiv.add_argument("--field-id", default=None, help="Academy field id to tag these chunks with (see backend/academy.py).")
    p_arxiv.add_argument("--max-results", type=int, default=10)

    p_seed = sub.add_parser("seed", help="Load one of the curated seed corpora (see --list-seeds).")
    p_seed.add_argument("--name", required=True, help="Seed dataset name, e.g. esco_skills.")
    p_seed.add_argument("--field-id", default=None, help="Override the field id each seed item already carries.")

    p_folder = sub.add_parser("folder", help="Load .txt/.md/.json OER files from a local folder.")
    p_folder.add_argument("--path", required=True, help="Folder to read, e.g. data/oer_raw/economics.")
    p_folder.add_argument("--field-id", default=None)
    p_folder.add_argument("--source-label", default="local", help="Value stored in each chunk's 'source' metadata.")

    args = parser.parse_args()
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
