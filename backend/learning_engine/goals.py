"""Multiple, ordered learning goals — richer than academy_enrollment's
single free-text career_goal (student_profile.py), which stays as-is for
backward compatibility. A student can hold several goals at once ("pasar
el examen B2", "terminar la especialización en IA", "practicar todos los
días") and mark each done independently; sort_order preserves the order
they were added in so the UI can show them as a stable, editable list."""

from __future__ import annotations

from .. import db


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
    }


def list_goals(user_id: str) -> list[dict]:
    with db.cursor() as cur:
        cur.execute(
            "SELECT id, text, sort_order, completed, created_at FROM learning_goal "
            "WHERE user_id=? ORDER BY sort_order ASC",
            (user_id,),
        )
        rows = [dict(r) for r in cur.fetchall()]
    for row in rows:
        row["completed"] = bool(row["completed"])
    return rows


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
