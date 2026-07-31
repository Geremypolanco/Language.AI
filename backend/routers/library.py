"""Library: a 500+ title on-demand AI-generated reading catalog in the
learner's target language. Catalog metadata (titles/genres/levels) is free,
static, and instant; the actual book text is generated once per (book, target
language) pair on first read and cached to disk from then on — see
HFClient.generate_book_content."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import auth
from ..hf_client import hf_client
from ..library import CATALOG, GENRES, get_book_stub
from ..models import BookContent, BookStub, CEFRLevel
from .users import get_user_by_id_or_404

router = APIRouter(prefix="/api/library", tags=["library"])

_DEFAULT_PAGE_SIZE = 30
_MAX_PAGE_SIZE = 100


@router.get("/genres")
def get_genres() -> list[dict]:
    return GENRES


@router.get("/{user_id}/catalog", response_model=list[BookStub])
def get_catalog(
    user_id: str,
    level: CEFRLevel | None = None,
    genre: str | None = None,
    offset: int = 0,
    limit: int = _DEFAULT_PAGE_SIZE,
    session: dict = Depends(auth.require_owner),
) -> list[BookStub]:
    get_user_by_id_or_404(user_id)
    items = CATALOG
    if level:
        items = [b for b in items if b.level == level]
    if genre:
        items = [b for b in items if b.genre == genre]
    offset = max(0, offset)
    limit = max(1, min(limit, _MAX_PAGE_SIZE))
    return items[offset : offset + limit]


@router.get("/{user_id}/books/{book_id}", response_model=BookContent)
async def get_book(user_id: str, book_id: str, session: dict = Depends(auth.require_owner)) -> BookContent:
    user = get_user_by_id_or_404(user_id)
    stub = get_book_stub(book_id)
    if not stub:
        raise HTTPException(status_code=404, detail="Libro no encontrado")
    content = await hf_client.generate_book_content(stub, user.target_lang, user.native_lang)
    return BookContent(id=stub.id, title=stub.title, genre_label=stub.genre_label, level=stub.level, content=content)
