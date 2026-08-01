from fastapi import APIRouter, HTTPException, Cookie
from pydantic import BaseModel
from sqlalchemy.orm import Session
from ..models import User
import uuid

router = APIRouter(prefix="/auth", tags=["auth"])

class ProfileCreate(BaseModel):
    display_name: str
    native_lang: str
    target_lang: str
    level: int
    interests: list
    daily_goal_minutes: int

@router.post("/logout")
async def logout():
    return {"status": "logged out"}

@router.get("/google/login")
async def google_login():
    return {"redirect": "https://accounts.google.com/o/oauth2/v2/auth?..."}

@router.post("/api/users")
async def create_profile(data: ProfileCreate, db: Session):
    user_id = str(uuid.uuid4())
    user = User(
        id=user_id,
        email=f"user_{user_id}@language.ai",
        display_name=data.display_name,
        native_lang=data.native_lang,
        target_lang=data.target_lang,
        level=data.level,
        interests=data.interests,
        daily_goal_minutes=data.daily_goal_minutes
    )
    db.add(user)
    db.commit()
    return {"id": user.id, "display_name": user.display_name}

@router.get("/api/session")
async def get_session():
    return {"authenticated": True, "user_id": "test_user", "email": "test@example.com"}
