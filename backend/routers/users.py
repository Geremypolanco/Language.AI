"""User profile / onboarding endpoints — identity comes from Google Sign-In,
not client-supplied data. A profile can only be created for the email that
just completed the Google OAuth flow (see routers/auth.py), and can only be
read/updated by the session that owns it.
"""

from __future__ import annotations

import json
import logging
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from .. import auth, db
from ..config import settings
from ..models import CEFRLevel, UserProfile

logger = logging.getLogger("lingua.users")

router = APIRouter(prefix="/api/users", tags=["users"])

# How many of a level's units to warm the exercise cache for right after
# onboarding — small on purpose: this is "make the learner's very next few
# clicks feel instant," not "pre-generate the whole curriculum for someone
# who might never open it." lessons.py's complete_lesson keeps one unit
# ahead of an active learner from here on.
_PREFETCH_UNIT_COUNT = 3


async def _prefetch_units(native_lang: str, target_lang: str, level: CEFRLevel, interests: list[str], count: int) -> None:
    """Warms generate_exercises' disk cache for a learner's upcoming units
    so Path feels instant on first open instead of generating on demand.
    Fire-and-forget via FastAPI's BackgroundTasks: runs after the response
    has already been sent, so it never adds latency to onboarding itself,
    and a failure here just means the affected unit falls back to
    generating on demand like before — never a broken app."""
    from ..curriculum import LessonRequest, units_for_level
    from ..hf_client import hf_client

    for unit in units_for_level(level)[:count]:
        try:
            await hf_client.generate_exercises(
                LessonRequest(unit=unit, native_lang=native_lang, target_lang=target_lang, interests=interests, recent_mistakes=[])
            )
        except Exception:
            logger.exception("Background exercise prefetch failed for unit %s", unit.id)


def get_user_by_id_or_404(user_id: str) -> UserProfile:
    """Plain data fetch, no auth check — used internally by other routers
    whose own route already enforced ownership via `auth.require_owner`."""
    with db.cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
        row = db.row_to_dict(cur.fetchone())
    if row is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return UserProfile(**row)


def _set_session_cookie(response: Response, user_id: str, email: str) -> None:
    response.set_cookie(
        auth.SESSION_COOKIE,
        auth.sign_session(user_id, email),
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=auth.SESSION_MAX_AGE,
    )


class CreateUserRequest(BaseModel):
    display_name: str = ""
    native_lang: str
    target_lang: str
    level: CEFRLevel = CEFRLevel.A1
    interests: list[str] = Field(default_factory=list)
    daily_goal_minutes: int = 15


@router.post("", response_model=UserProfile)
def create_user(
    payload: CreateUserRequest, request: Request, response: Response, background_tasks: BackgroundTasks
) -> UserProfile:
    pending = auth.verify_pending(request.cookies.get(auth.PENDING_COOKIE))
    if not pending:
        raise HTTPException(status_code=401, detail="Inicia sesión con Google primero")
    email = pending["email"]

    with db.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE email=?", (email,))
        existing = cur.fetchone()
    if existing:
        # Already onboarded on another device/tab — just re-establish the session.
        _set_session_cookie(response, existing["id"], email)
        response.delete_cookie(auth.PENDING_COOKIE)
        return get_user_by_id_or_404(existing["id"])

    user_id = uuid.uuid4().hex[:12]
    now = db.now_iso()
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO users
               (id, email, display_name, native_lang, target_lang, level, interests, xp, streak_days,
                daily_goal_minutes, created_at, last_active_date)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?)""",
            (
                user_id,
                email,
                payload.display_name.strip() or pending.get("name") or "Learner",
                payload.native_lang,
                payload.target_lang,
                payload.level.value,
                json.dumps(payload.interests),
                max(1, payload.daily_goal_minutes),
                now,
                "",  # last_active_date starts empty, not today — it tracks actual
                # activity (lesson completion), not account creation. Seeding it to
                # today would make srs.record_lesson_result's `!= today` check false
                # on the user's very first lesson, so their first-day streak would
                # never tick up from 0.
            ),
        )

    _set_session_cookie(response, user_id, email)
    response.delete_cookie(auth.PENDING_COOKIE)
    background_tasks.add_task(
        _prefetch_units, payload.native_lang, payload.target_lang, payload.level, payload.interests, _PREFETCH_UNIT_COUNT
    )
    return get_user_by_id_or_404(user_id)


@router.get("/me", response_model=UserProfile)
def get_me(session: dict = Depends(auth.require_session)) -> UserProfile:
    return get_user_by_id_or_404(session["user_id"])


@router.get("/{user_id}", response_model=UserProfile)
def get_user(user_id: str, session: dict = Depends(auth.require_owner)) -> UserProfile:
    return get_user_by_id_or_404(user_id)


class UpdateUserRequest(BaseModel):
    display_name: str | None = None
    native_lang: str | None = None
    target_lang: str | None = None
    interests: list[str] | None = None
    level: CEFRLevel | None = None
    daily_goal_minutes: int | None = None
    tutor_persona_id: str | None = None


@router.patch("/{user_id}", response_model=UserProfile)
def update_user(
    user_id: str, payload: UpdateUserRequest, background_tasks: BackgroundTasks, session: dict = Depends(auth.require_owner)
) -> UserProfile:
    if payload.tutor_persona_id is not None:
        from .. import personas

        if payload.tutor_persona_id and not personas.get_core_teacher(payload.tutor_persona_id):
            raise HTTPException(status_code=400, detail="Maestro no encontrado")

    with db.cursor() as cur:
        if payload.display_name is not None:
            name = payload.display_name.strip()
            if not name:
                raise HTTPException(status_code=400, detail="El nombre no puede estar vacío")
            cur.execute("UPDATE users SET display_name=? WHERE id=?", (name, user_id))
        if payload.native_lang is not None:
            cur.execute("UPDATE users SET native_lang=? WHERE id=?", (payload.native_lang, user_id))
        if payload.target_lang is not None:
            cur.execute("UPDATE users SET target_lang=? WHERE id=?", (payload.target_lang, user_id))
        if payload.interests is not None:
            cur.execute("UPDATE users SET interests=? WHERE id=?", (json.dumps(payload.interests), user_id))
        if payload.level is not None:
            cur.execute("UPDATE users SET level=? WHERE id=?", (payload.level.value, user_id))
        if payload.daily_goal_minutes is not None:
            cur.execute(
                "UPDATE users SET daily_goal_minutes=? WHERE id=?", (max(1, payload.daily_goal_minutes), user_id)
            )
        if payload.tutor_persona_id is not None:
            cur.execute("UPDATE users SET tutor_persona_id=? WHERE id=?", (payload.tutor_persona_id, user_id))

    updated = get_user_by_id_or_404(user_id)
    # Changing target/native language, level, or interests changes
    # generate_exercises' cache key entirely — the learner's existing
    # prefetched/cached units (from onboarding or normal play) are for a
    # combination that no longer applies, so warm the new one the same way
    # onboarding does, instead of leaving Path to generate on demand again.
    if payload.native_lang is not None or payload.target_lang is not None or payload.level is not None or payload.interests is not None:
        background_tasks.add_task(
            _prefetch_units, updated.native_lang, updated.target_lang, updated.level, updated.interests, _PREFETCH_UNIT_COUNT
        )
    return updated
