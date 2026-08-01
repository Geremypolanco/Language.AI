from fastapi import APIRouter

router = APIRouter(prefix="/api/progress", tags=["progress"])

@router.get("/{user_id}")
async def get_progress(user_id: str):
    return {
        "level": 3,
        "total_xp": 450,
        "days_learned": 15,
        "streak": 7,
        "weekly_activity": [
            {"day": "Mon", "minutes": 25},
            {"day": "Tue", "minutes": 30},
            {"day": "Wed", "minutes": 20},
            {"day": "Thu", "minutes": 35},
            {"day": "Fri", "minutes": 40},
            {"day": "Sat", "minutes": 45},
            {"day": "Sun", "minutes": 30},
        ],
        "skills": [
            {"skill": "Listening", "progress": 78},
            {"skill": "Speaking", "progress": 65},
            {"skill": "Reading", "progress": 82},
            {"skill": "Writing", "progress": 58},
            {"skill": "Grammar", "progress": 71},
            {"skill": "Vocabulary", "progress": 89},
        ]
    }
