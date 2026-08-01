from fastapi import APIRouter

router = APIRouter(prefix="/api/library", tags=["library"])

@router.get("/genres")
async def get_genres():
    return ["Fiction", "Adventure", "Mystery", "Romance", "Science Fiction"]

@router.get("/{user_id}/catalog")
async def get_catalog(user_id: str):
    return [
        {"id": "1", "title": "The Lost City", "author": "AI Author", "level": "Intermediate", "genre": "Adventure", "readTime": 15, "rating": 4.8},
        {"id": "2", "title": "Mystery in Paris", "author": "AI Author", "level": "Advanced", "genre": "Mystery", "readTime": 20, "rating": 4.6},
        {"id": "3", "title": "Love in Spain", "author": "AI Author", "level": "Beginner", "genre": "Romance", "readTime": 10, "rating": 4.5},
    ]
