"""Multiple, ordered learning goals — richer than academy_enrollment's
single free-text career_goal (student_profile.py), which stays as-is for
backward compatibility. A student can hold several goals at once ("pasar
el examen B2", "terminar la especialización en IA", "practicar todos los
días") and mark each done independently; sort_order preserves the order
they were added in so the UI can show them as a stable, editable list.

milestones/milestone_progress (see mentor_engine/goal_planner.py, which
actually generates them) are stored here alongside the goal — this module
only reads/writes them as opaque JSON + an integer cursor; it never
decides WHAT the milestones are, keeping the "no AI in learning_engine"
boundary this package has held since it was first built."""

from __future__ import annotations

import json

from .. import db


def _row_to_dict(row: dict) -> dict:
    milestones = json.loads(row["milestones"]) if row["milestones"] else []
    progress = row["milestone_progress"]
    return {
        "id": row["id"],
        "text": row["text"],
        "sort_order": row["sort_order"],
        "completed": bool(row["completed"]),
        "created_at": row["created_at"],
        "milestones": milestones,
        "milestone_progress": progress,
        "current_milestone": milestones[progress] if progress < len(milestones) else None,
    }


def add_goal(user_id: str, text: str) -> dict:
    text = text.strip()
    with db.cursor() as cur:
        cur.execute("SELECT COALESCE(MAX(sort_order), -1) AS m FROM learning_goal WHERE user_id=?", (user_id,))
        next_order = cur.fetchone()["m"] + 1
        created_at = db.now_iso()
        cur.execute(
            "INSERT INTO learning_goal (user_id, text, sort_order, completed, created_at) VALUES (?, ?, ?, 0, ?)",
            (user_id, text, next_order, created_at),
        )
        cur.execute(
            "SELECT id FROM learning_goal WHERE user_id=? AND sort_order=?", (user_id, next_order)
        )
        goal_id = cur.fetchone()["id"]
    return {
        "id": goal_id,
        "text": text,
        "sort_order": next_order,
        "completed": False,
        "created_at": created_at,
        "milestones": [],
        "milestone_progress": 0,
        "current_milestone": None,
    }


def list_goals(user_id: str) -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, text, sort_order, completed, created_at, milestones, milestone_progress "
            "FROM learning_goal WHERE user_id=? ORDER BY sort_order ASC",
            (user_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    return [_row_to_dict(r) for r in rows]


def get_goal(user_id: str, goal_id: int) -> dict | None:
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, text, sort_order, completed, created_at, milestones, milestone_progress "
            "FROM learning_goal WHERE id=? AND user_id=?",
            (goal_id, user_id),
        )
        row = cur.fetchone()
        return _row_to_dict(dict(row)) if row else None


def complete_goal(user_id: str, goal_id: int, completed: bool = True) -> bool:
    """Returns False if goal_id doesn't belong to user_id (or doesn't
    exist) so the router can 404 instead of silently no-opping."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE learning_goal SET completed=? WHERE id=? AND user_id=?",
            (int(completed), goal_id, user_id),
        )
        return cur.rowcount > 0


def remove_goal(user_id: str, goal_id: int) -> bool:
    with db.cursor() as cur:
        cur.execute("DELETE FROM learning_goal WHERE id=? AND user_id=?", (goal_id, user_id))
        return cur.rowcount > 0


def set_milestones(user_id: str, goal_id: int, milestones: list[str]) -> bool:
    """Overwrites whatever milestones existed and resets progress to 0 —
    called once by goal_planner.py right after generating them for a goal
    that didn't have any yet. Returns False if goal_id doesn't belong to
    user_id."""
    with db.cursor() as cur:
        cur.execute(
            "UPDATE learning_goal SET milestones=?, milestone_progress=0 WHERE id=? AND user_id=?",
            (json.dumps(milestones), goal_id, user_id),
        )
        return cur.rowcount > 0


def advance_milestone(user_id: str, goal_id: int) -> dict | None:
    """Moves milestone_progress one step forward (capped at the number of
    milestones). Returns the updated goal, or None if it doesn't exist/
    doesn't belong to user_id."""
    goal = get_goal(user_id, goal_id)
    if goal is None:
        return None
    new_progress = min(goal["milestone_progress"] + 1, len(goal["milestones"]))
    with db.cursor() as cur:
        cur.execute(
            "UPDATE learning_goal SET milestone_progress=? WHERE id=? AND user_id=?",
            (new_progress, goal_id, user_id),
        )
    return get_goal(user_id, goal_id)
