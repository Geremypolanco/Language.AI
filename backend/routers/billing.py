"""HTTP surface for Lingua Pro billing.

- POST /api/billing/checkout — authenticated; creates the Stripe Checkout
  Session and returns the hosted URL.
- POST /api/billing/webhook — unauthenticated by design (Stripe calls it);
  the Stripe signature is the authentication. Never grants anything on an
  unverifiable payload.
- GET /api/billing/status — authenticated; the frontend's source of truth
  for plan + remaining free Talk Live turns.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from .. import auth, billing
from ..config import settings

logger = logging.getLogger("lingua.billing_api")

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.get("/status")
def billing_status(session: dict = Depends(auth.require_session)) -> dict:
    user_id = session["user_id"]
    plan = billing.get_plan(user_id)
    allowed, remaining = billing.can_start_turn(user_id)
    return {
        "plan": plan,
        "is_pro": plan == billing.PLAN_PRO,
        "stripe_configured": settings.stripe_configured,
        "pro_price_usd": settings.pro_price_usd,
        "free_daily_turns": billing.FREE_DAILY_TURNS,
        "turns_used_today": billing.turns_used_today(user_id),
        "turns_remaining_today": remaining,
        "turn_allowed_now": allowed,
    }


@router.post("/checkout")
def create_checkout(session: dict = Depends(auth.require_session)) -> dict:
    if not settings.stripe_configured:
        raise HTTPException(
            status_code=503,
            detail="El cobro con tarjeta aún no está configurado — la app sigue siendo gratis",
        )
    try:
        url = billing.create_checkout_session(session["user_id"], session.get("email", ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # Stripe API failure — don't leak internals
        logger.exception("Stripe Checkout creation failed")
        raise HTTPException(status_code=502, detail="No se pudo iniciar el pago — inténtalo de nuevo") from exc
    return {"url": url}


@router.post("/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    # Signature verification IS the auth here. If the signing secret isn't
    # configured we must refuse everything rather than accept unsigned
    # events — a fail-open webhook would let anyone grant themselves Pro.
    if not settings.stripe_configured:
        logger.error("Webhook hit but Stripe is not configured — refusing")
        return JSONResponse({"error": "billing not configured"}, status_code=503)

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = billing.verify_webhook_event(payload, sig_header)
    except Exception:
        logger.warning("Webhook signature verification failed — ignoring payload")
        return JSONResponse({"error": "invalid signature"}, status_code=400)

    event_type = event.get("type")
    if event_type == "checkout.session.completed":
        upgraded = billing.handle_checkout_completed(event)
        return JSONResponse({"received": True, "upgraded": upgraded})
    # One-time payment product: no subscription lifecycle to track. Anything
    # else (payment_intent.*, charge.*) is informational — acknowledge it so
    # Stripe doesn't retry.
    logger.info("Webhook: ignoring event type %s", event_type)
    return JSONResponse({"received": True, "ignored": event_type})
