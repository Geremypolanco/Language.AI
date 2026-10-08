"""Lingua Pro — the one paid tier, wired to real Stripe Checkout.

The app is free by design for everything that costs us nothing at serving
time (lessons, practice, the library, university courses — all pre-generated
content). What costs real money per use is the on-demand AI behind Talk Live:
every conversation turn burns one streaming chat call, one TTS synthesis,
and usually one speech-to-text call (see backend/routers/conversation.py and
the Pollinations/HF quota notes in backend/config.py). So that's what the
paid tier gates:

- **Free** (`plan='free'`): 20 Talk Live conversation turns per day.
- **Pro** (`plan='pro'`): unlimited Talk Live turns, forever — a single
  one-time payment, not a subscription.

One-time (not subscription) is a deliberate product call: a solo operator's
first sellable tier should have the smallest possible billing surface — one
webhook event (`checkout.session.completed`), no renewal/dunning/cancellation
lifecycle to support — and the marginal cost per user is near-zero (free
inference tiers are the primary path, Piper TTS is self-hosted and
unlimited), so a lifetime deal is economically sustainable. A monthly plan
can be added later once this one is proven to sell.

Money flow:
1. Frontend POSTs /api/billing/checkout (authenticated) -> we create a
   Stripe Checkout Session (mode=payment) with metadata.user_id and redirect
   the buyer to session.url.
2. Stripe POSTs checkout.session.completed to /api/billing/webhook. The
   signature is verified with the webhook signing secret (no unsigned event
   is ever trusted), then grant_pro() flips the user's plan. The operation
   is idempotent — a redelivered event just sets 'pro' again.

Env (see backend/config.py): LINGUA_STRIPE_SECRET_KEY,
LINGUA_STRIPE_WEBHOOK_SECRET, optional LINGUA_STRIPE_PRICE_ID (dashboard-
managed Price; otherwise the $LINGUA_PRO_PRICE_USD inline price_data is
used), LINGUA_PRO_PRICE_USD (default 39).
"""

from __future__ import annotations

import logging

from . import db
from .config import settings

logger = logging.getLogger("lingua.billing")

# Talk Live turns a free account gets per UTC day. Pro is unlimited.
FREE_DAILY_TURNS = 20

PLAN_FREE = "free"
PLAN_PRO = "pro"


# ── plan reads ──────────────────────────────────────────────────────────────


def get_plan(user_id: str) -> str:
    """Returns 'free' or 'pro'. Unknown users read as free — a missing row
    must never accidentally unlock paid features."""
    with db.cursor() as cur:
        cur.execute("SELECT plan FROM users WHERE id=?", (user_id,))
        row = cur.fetchone()
    plan = (row["plan"] if row else None) or PLAN_FREE
    return plan if plan == PLAN_PRO else PLAN_FREE


def is_pro(user_id: str) -> bool:
    return get_plan(user_id) == PLAN_PRO


# ── daily usage accounting ──────────────────────────────────────────────────


def turns_used_today(user_id: str) -> int:
    with db.cursor() as cur:
        cur.execute(
            "SELECT convo_turns FROM usage_daily WHERE user_id=? AND day=?",
            (user_id, db.today_str()),
        )
        row = cur.fetchone()
    return int(row["convo_turns"]) if row else 0


def can_start_turn(user_id: str) -> tuple[bool, int]:
    """Whether this user may start another Talk Live turn right now, plus how
    many free turns remain today (0 for Pro — the concept doesn't apply)."""
    if is_pro(user_id):
        return True, 0
    used = turns_used_today(user_id)
    remaining = max(0, FREE_DAILY_TURNS - used)
    return used < FREE_DAILY_TURNS, remaining


def record_convo_turn(user_id: str) -> None:
    """Counts one completed assistant turn against today's budget. Pro users
    are recorded too (cheap, and it keeps the analytics honest) — the gate
    is in can_start_turn(), not here."""
    with db.cursor() as cur:
        cur.execute(
            """INSERT INTO usage_daily (user_id, day, convo_turns) VALUES (?, ?, 1)
               ON CONFLICT (user_id, day) DO UPDATE SET convo_turns = usage_daily.convo_turns + 1""",
            (user_id, db.today_str()),
        )


# ── granting Pro ────────────────────────────────────────────────────────────


def grant_pro(user_id: str, stripe_customer_id: str = "") -> bool:
    """Flips a user to Pro. Idempotent — safe to call for a redelivered
    webhook. Returns False when the user id doesn't exist (so the webhook
    can log loudly instead of silently swallowing a paid order)."""
    with db.cursor() as cur:
        if stripe_customer_id:
            cur.execute(
                "UPDATE users SET plan=?, stripe_customer_id=?, plan_updated_at=? WHERE id=?",
                (PLAN_PRO, stripe_customer_id, db.now_iso(), user_id),
            )
        else:
            cur.execute(
                "UPDATE users SET plan=?, plan_updated_at=? WHERE id=?",
                (PLAN_PRO, db.now_iso(), user_id),
            )
        if cur.rowcount == 0:
            logger.error("grant_pro: unknown user_id %s — paid order has no account to unlock", user_id)
            return False
    logger.info("grant_pro: user %s upgraded to Pro", user_id)
    return True


# ── Stripe Checkout ─────────────────────────────────────────────────────────


def _stripe() -> object:
    """Import is lazy and the key is set per call so tests can run without
    the stripe package installed and without any credentials configured."""
    import stripe

    stripe.api_key = settings.stripe_secret_key
    return stripe


def create_checkout_session(user_id: str, email: str) -> str:
    """Creates a one-time-payment Checkout Session for Lingua Pro and returns
    the hosted URL the buyer must be redirected to. Raises RuntimeError when
    billing isn't configured and ValueError when the user is already Pro."""
    if not settings.stripe_configured:
        raise RuntimeError("El cobro con tarjeta no está configurado en este despliegue")
    if is_pro(user_id):
        raise ValueError("Esta cuenta ya es Pro")

    stripe = _stripe()
    base = settings.public_base_url
    line_items: list[dict] = (
        [{"price": settings.stripe_price_id, "quantity": 1}]
        if settings.stripe_price_id
        else [
            {
                "price_data": {
                    "currency": "usd",
                    "unit_amount": settings.pro_price_cents,
                    "product_data": {
                        "name": "Lingua Pro — acceso de por vida",
                        "description": (
                            "Conversación ilimitada con el tutor de IA (Hablar en vivo), "
                            "para siempre. Pago único."
                        ),
                    },
                },
                "quantity": 1,
            }
        ]
    )
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=line_items,
        # metadata.user_id is the authoritative link back to our account —
        # the webhook trusts this over the email fallback below.
        metadata={"user_id": user_id, "product": "lingua_pro_lifetime"},
        client_reference_id=user_id,
        customer_email=email or None,
        success_url=f"{base}/pro?checkout=success&session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{base}/pro?checkout=canceled",
        locale="auto",
    )
    logger.info("Checkout session created for user %s", user_id)
    return session.url


def verify_webhook_event(payload: bytes, sig_header: str | None) -> dict:
    """Verifies the Stripe signature and returns the parsed event. Raises on
    anything untrusted — callers must NOT grant anything when this raises."""
    stripe = _stripe()
    return stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)


def handle_checkout_completed(event: dict) -> bool:
    """Processes a checkout.session.completed event. Returns True when a user
    was actually upgraded."""
    session_obj = event.get("data", {}).get("object", {}) or {}
    if session_obj.get("payment_status") != "paid":
        logger.warning("Ignoring checkout.session.completed with payment_status=%s", session_obj.get("payment_status"))
        return False
    metadata = session_obj.get("metadata") or {}
    user_id = metadata.get("user_id") or session_obj.get("client_reference_id")
    if user_id and grant_pro(user_id, str(session_obj.get("customer") or "")):
        return True
    # Fallback: match by the buyer's email (covers sessions created without
    # metadata, e.g. a manually-created payment link).
    email = ((session_obj.get("customer_details") or {}).get("email") or "").strip().lower()
    if email:
        with db.cursor() as cur:
            cur.execute("SELECT id FROM users WHERE email=?", (email,))
            row = cur.fetchone()
        if row and grant_pro(row["id"], str(session_obj.get("customer") or "")):
            return True
    logger.error("checkout.session.completed could not be mapped to a user: %s", session_obj.get("id"))
    return False
