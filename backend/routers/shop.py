"""Gem shop: spend gems earned from lessons on a streak freeze — Duolingo's
gem economy, minus any real-money purchase path (this app is entirely free,
so gems are earn-only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from .. import auth, srs

router = APIRouter(prefix="/api/shop", tags=["shop"])


@router.post("/{user_id}/streak-freeze")
def buy_streak_freeze(user_id: str, session: dict = Depends(auth.require_owner)) -> dict:
    try:
        return srs.buy_streak_freeze(user_id)
    except srs.ShopError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
