from fastapi import APIRouter

router = APIRouter(prefix="/api/academy", tags=["academy"])

@router.get("/fields")
async def get_fields():
    return [
        {"id": "1", "title": "Business", "icon": "💼", "description": "Professional communication", "courses": 12},
        {"id": "2", "title": "Travel", "icon": "✈️", "description": "Conversational travel", "courses": 8},
        {"id": "3", "title": "Tech", "icon": "💻", "description": "Technical vocabulary", "courses": 10},
    ]

@router.post("/{user_id}/enroll")
async def enroll(user_id: str, field_id: str):
    return {"status": "enrolled", "field_id": field_id}
