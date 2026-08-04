#!/usr/bin/env python3
"""Build (or rebuild) the pre-generated language-lesson library.

Run this whenever a language pair's unit content needs to exist before
students study it — the whole point of backend/language_library/ is that
routers/lessons.py never has to call Hugging Face for the fixed unit
curriculum while a student is actually learning; this script is where all
of that generation happens instead, ahead of time. Free-form practice mode
(get_practice_exercises) is NOT covered by this — it deliberately stays
on-demand/personalized (see backend/language_library/__init__.py).

Unlike scripts/build_academy.py, there is no fixed catalog of "all
languages" to default to — curriculum content is language-agnostic and
filled in for whatever target/native language pair a real user picks.
--target-langs/--native-langs are paired positionally (first target with
first native, etc.) and must be the same length.

Examples:

    # Build English (for Spanish speakers) and Spanish (for English
    # speakers) — the two most common pairs — across every CEFR level.
    python scripts/build_languages.py \
        --target-langs English Spanish --native-langs Spanish English

    # Just one pair, one level — the fast way to try the pipeline.
    python scripts/build_languages.py \
        --target-langs Korean --native-langs Spanish --levels A1

    # A unit's prompt changed: only that pair/level gets a new version;
    # nothing else in the library is touched.
    python scripts/build_languages.py \
        --target-langs English --native-langs Spanish --force

Requires HF_TOKEN (or another configured chat provider — see
backend/hf_client.py's chat()) to actually generate anything; run this
from an environment with real AI credentials and budget, not from a CI
job or a sandbox with LINGUA_TESTING set.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.academy_library.storage import FileSystemAcademyStore  # noqa: E402
from backend.config import settings  # noqa: E402
from backend.language_library import build  # noqa: E402
from backend.models import CEFRLevel  # noqa: E402

logger = logging.getLogger("lingua.build_languages")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--target-langs", nargs="+", required=True,
        help="Target languages to build, paired positionally with --native-langs (e.g. English Spanish).",
    )
    parser.add_argument(
        "--native-langs", nargs="+", required=True,
        help="Native languages to build for, paired positionally with --target-langs.",
    )
    parser.add_argument(
        "--levels", nargs="+", default=None, choices=[lvl.value for lvl in CEFRLevel],
        help="CEFR levels to build (default: all of them).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Regenerate every unit even if already present in the target version (default: skip existing "
        "units, so an interrupted run can resume where it left off).",
    )
    parser.add_argument(
        "--version", default=None,
        help="Pin every built (pair, level) to this exact version string instead of each auto-incrementing "
        "its own v1/v2/v3/... independently.",
    )
    parser.add_argument(
        "--library-dir", default=None,
        help="Override settings.language_library_dir (default: LINGUA_LANGUAGE_LIBRARY_DIR env var, or "
        "data/language_library).",
    )
    return parser.parse_args()


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    args = parse_args()

    if len(args.target_langs) != len(args.native_langs):
        logger.error(
            "--target-langs (%d) and --native-langs (%d) must be the same length — they're paired positionally.",
            len(args.target_langs), len(args.native_langs),
        )
        return 1
    language_pairs = list(zip(args.target_langs, args.native_langs))
    levels = [CEFRLevel(lvl) for lvl in args.levels] if args.levels else list(CEFRLevel)

    store = FileSystemAcademyStore(args.library_dir or settings.language_library_dir)

    logger.info(
        "Building %d language pair(s) x %d level(s) into %s ...", len(language_pairs), len(levels), store.base_dir
    )
    reports = await build.build_all(store, language_pairs, levels, version=args.version, force=args.force)

    ok = [r for r in reports if r.ok]
    failed = [r for r in reports if not r.ok]

    logger.info("Done: %d succeeded, %d had failures.", len(ok), len(failed))
    for report in failed:
        logger.error(
            "%s/%s (version=%s): %d/%d units built, %d failure(s):",
            report.language_pair, report.level, report.version, report.units_built, report.units_attempted,
            len(report.failures),
        )
        for item, error in report.failures:
            logger.error("  - %s: %s", item, error)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
