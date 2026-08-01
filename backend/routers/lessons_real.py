from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from ..models import Lesson, UserProgress
import uuid

router = APIRouter(prefix="/api/lessons", tags=["lessons"])

@router.get("/{user_id}/path")
async def get_lessons_path(user_id: str, db: Session):
    lessons = [
        {"id": "1", "title": "Hello World", "description": "Basic greetings", "level": "beginner", "duration": 10, "completed": False, "xp": 10},
        {"id": "2", "title": "Numbers", "description": "Count 1-10", "level": "beginner", "duration": 15, "completed": True, "xp": 15},
        {"id": "3", "title": "Colors", "description": "Learn colors", "level": "beginner", "duration": 12, "completed": False, "xp": 12},
    ]
    return lessons

@router.post("/{user_id}/complete")
async def complete_lesson(user_id: str, lesson_id: str):
    return {"status": "completed", "xp_earned": 10}

@router.post("/{user_id}/answer")
async def submit_answer(user_id: str, lesson_id: str, answer: str):
    return {"correct": True, "feedback": "Great job!"}
