#!/usr/bin/env python3
"""Build (or rebuild) the pre-generated academic library.

Run this whenever academic content needs to exist before students can use
it — the whole point of backend/academy_library/ is that routers/academy.py
never has to call Hugging Face while a student is actually studying; this
script is where all of that generation happens instead, ahead of time.

Examples:

    # Build everything (all ~60+ fields, all 3 academic levels) — this is a
    # substantial one-time AI-token cost; see --fields to scope it down.
    python scripts/build_academy.py

    # Build just one field, one level — the fast way to try the pipeline or
    # test a prompt change before committing to a full run.
    python scripts/build_academy.py --fields computer-science --levels BACHELOR

    # A field's content needs a refresh (prompt tweak, stale info): only
    # that field gets a new version; nothing else in the library is touched.
    python scripts/build_academy.py --fields computer-science --force

Requires HF_TOKEN (or another configured chat provider — see
backend/hf_client.py's chat()) to actually generate anything; this is meant
to be run from an environment with real AI credentials and budget, not from
a CI job or a sandbox with LINGUA_TESTING set. Also writes to the app's own
database (LINGUA_DB_PATH or SUPABASE_DB_URL) — run it against the same
database the deployed app actually uses, since the knowledge graph it
populates (concepts + prerequisite edges, see backend/learning_engine/
knowledge_graph.py) is read live by routers/academy.py's recommendation
and competency endpoints.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.academy_library import build  # noqa: E402
from backend.academy_library.storage import FileSystemAcademyStore  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.learning_engine import knowledge_graph  # noqa: E402
from backend.models import AcademicLevel  # noqa: E402

logger = logging.getLogger("lingua.build_academy")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--fields", nargs="+", default=None,
        help="Academic field ids to build (default: every field — see backend/academy.py's all_fields()).",
    )
    parser.add_argument(
        "--levels", nargs="+", default=None, choices=[lvl.value for lvl in AcademicLevel],
        help="Academic levels to build (default: all of ASSOCIATE/BACHELOR/MASTER).",
    )
    parser.add_argument(
        "--native-lang", default="Español",
        help="Language the generated content is written in (default: Español).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate every asset even if already present in the target version (default: skip existing "
        "assets, so an interrupted run can resume where it left off).",
    )
    parser.add_argument(
        "--version", default=None,
        help="Pin every built (field, level) to this exact version string instead of each auto-incrementing "
        "its own v1/v2/v3/... independently.",
    )
    parser.add_argument(
        "--library-dir", default=None,
        help="Override settings.academy_library_dir (default: LINGUA_ACADEMY_LIBRARY_DIR env var, or "
        "data/academy_library).",
    )
    return parser.parse_args()


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    try:
        fields = build.resolve_fields(args.fields)
    except ValueError as exc:
        logger.error("%s", exc)
        return 1
    levels = [AcademicLevel(lvl) for lvl in args.levels] if args.levels else list(AcademicLevel)

    store = FileSystemAcademyStore(args.library_dir or settings.academy_library_dir)

    logger.info(
        "Building %d field(s) x %d level(s) into %s ...", len(fields), len(levels), store.base_dir
    )
    reports = await build.build_all(store, fields, levels, args.native_lang, version=args.version, force=args.force)

    ok = [r for r in reports if r.ok]
    failed = [r for r in reports if not r.ok]

    for report in ok:
        curriculum = store.load_curriculum(report.field_id, report.level)
        if not curriculum:
            continue
        course_ids = [f"{report.field_id}:{report.level}:{i}" for i in range(len(curriculum["courses"]))]
        added = knowledge_graph.build_graph_for_field_level(report.field_id, report.level, course_ids, store)
        logger.info("Knowledge graph: %s/%s contributed concepts from %d course(s).", report.field_id, report.level, added)

    logger.info("Done: %d succeeded, %d had failures.", len(ok), len(failed))
    for report in failed:
        logger.error(
            "%s/%s (version=%s): %d/%d courses built, %d failure(s):",
            report.field_id, report.level, report.version, report.courses_built, report.courses_attempted,
            len(report.failures),
        )
        for item, error in report.failures:
            logger.error("  - %s: %s", item, error)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
