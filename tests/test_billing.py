"""Tests for Lingua Pro billing (backend/billing.py, routers/billing.py).

Offline by design: Stripe network calls are monkeypatched and webhook
signatures are computed locally with stdlib hmac — the real
stripe.Webhook.construct_event verification path is still exercised.
"""

import hashlib
import hmac
import json
import time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from backend import billing
from backend.config import settings
from backend.main import app
from conftest import dev_login


@pytest.fixture()
def stripe_env(monkeypatch):
    """Points billing at test credentials for one test, then restores."""
    object.__setattr__(settings, "stripe_secret_key", "sk_test_123")
    object.__setattr__(settings, "stripe_webhook_secret", "whsec_test_123")
    yield
    object.__setattr__(settings, "stripe_secret_key", "")
    object.__setattr__(settings, "stripe_webhook_secret", "")


def _onboard(client, email="pro-buyer@example.com"):
    dev_login(client, email)
    res = client.post(
        "/api/users",
        json={
            "display_name": "Buyer",
            "native_lang": "English",
            "target_lang": "Spanish",
            "level": "A1",
            "interests": [],
        },
    )
    assert res.status_code == 200
    return res.json()


# ── plan + quota ────────────────────────────────────────────────────────────


def test_new_user_defaults_to_free():
    with TestClient(app) as client:
        user = _onboard(client)
        assert user["plan"] == "free"
        assert billing.get_plan(user["id"]) == "free"
        assert not billing.is_pro(user["id"])


def test_unknown_user_reads_as_free():
    assert billing.get_plan("no-such-user") == "free"
    assert not billing.is_pro("no-such-user")


def test_free_turn_budget_enforced():
    with TestClient(app) as client:
        user = _onboard(client)
        uid = user["id"]
        allowed, remaining = billing.can_start_turn(uid)
        assert allowed and remaining == billing.FREE_DAILY_TURNS
        for _ in range(billing.FREE_DAILY_TURNS):
            billing.record_convo_turn(uid)
        allowed, remaining = billing.can_start_turn(uid)
        assert not allowed and remaining == 0
        # Extra turns past the cap never go negative.
        billing.record_convo_turn(uid)
        allowed, remaining = billing.can_start_turn(uid)
        assert not allowed and remaining == 0


def test_pro_is_unlimited_and_idempotent():
    with TestClient(app) as client:
        user = _onboard(client)
        uid = user["id"]
        assert billing.grant_pro(uid, "cus_123")
        assert billing.grant_pro(uid, "cus_123")  # redelivered webhook
        assert billing.is_pro(uid)
        for _ in range(billing.FREE_DAILY_TURNS * 5):
            billing.record_convo_turn(uid)
        allowed, _ = billing.can_start_turn(uid)
        assert allowed


def test_grant_pro_unknown_user_returns_false():
    assert billing.grant_pro("no-such-user") is False


def test_status_endpoint_reports_plan_and_quota():
    with TestClient(app) as client:
        user = _onboard(client)
        res = client.get("/api/billing/status")
        assert res.status_code == 200
        body = res.json()
        assert body["plan"] == "free"
        assert body["is_pro"] is False
        assert body["free_daily_turns"] == billing.FREE_DAILY_TURNS
        assert body["turns_remaining_today"] == billing.FREE_DAILY_TURNS
        assert body["stripe_configured"] is False  # no keys in test env


# ── checkout ────────────────────────────────────────────────────────────────


def test_checkout_503_without_stripe_keys():
    with TestClient(app) as client:
        _onboard(client)
        res = client.post("/api/billing/checkout")
        assert res.status_code == 503


def test_checkout_creates_session_and_redirects(stripe_env):
    with TestClient(app) as client:
        user = _onboard(client)
        fake_session = mock.Mock(url="https://checkout.stripe.com/pay/cs_test_123")
        with mock.patch("stripe.checkout.Session.create", return_value=fake_session) as create:
            res = client.post("/api/billing/checkout")
        assert res.status_code == 200
        assert res.json()["url"] == "https://checkout.stripe.com/pay/cs_test_123"
        kwargs = create.call_args.kwargs
        assert kwargs["mode"] == "payment"
        assert kwargs["metadata"]["user_id"] == user["id"]
        assert kwargs["client_reference_id"] == user["id"]


def test_checkout_400_when_already_pro(stripe_env):
    with TestClient(app) as client:
        user = _onboard(client)
        billing.grant_pro(user["id"])
        res = client.post("/api/billing/checkout")
        assert res.status_code == 400


# ── webhook ─────────────────────────────────────────────────────────────────


def _signed_payload(secret: str, event: dict) -> tuple[bytes, dict]:
    payload = json.dumps(event).encode()
    ts = str(int(time.time()))
    sig = hmac.new(secret.encode(), f"{ts}.{payload.decode()}".encode(), hashlib.sha256).hexdigest()
    return payload, {"stripe-signature": f"t={ts},v1={sig}"}


def _completed_event(user_id: str, paid: bool = True) -> dict:
    return {
        "id": "evt_test_123",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "id": "cs_test_123",
                "payment_status": "paid" if paid else "unpaid",
                "metadata": {"user_id": user_id, "product": "lingua_pro_lifetime"},
                "client_reference_id": user_id,
                "customer": "cus_test_123",
                "customer_details": {"email": "pro-buyer@example.com"},
            }
        },
    }


def test_webhook_grants_pro_on_valid_signature(stripe_env):
    with TestClient(app) as client:
        user = _onboard(client)
        payload, headers = _signed_payload("whsec_test_123", _completed_event(user["id"]))
        res = client.post("/api/billing/webhook", content=payload, headers=headers)
        assert res.status_code == 200
        assert res.json()["upgraded"] is True
        assert billing.is_pro(user["id"])


def test_webhook_rejects_bad_signature(stripe_env):
    with TestClient(app) as client:
        user = _onboard(client)
        payload, _ = _signed_payload("whsec_wrong_secret", _completed_event(user["id"]))
        res = client.post(
            "/api/billing/webhook",
            content=payload,
            headers={"stripe-signature": "t=123,v1=deadbeef"},
        )
        assert res.status_code == 400
        assert not billing.is_pro(user["id"])


def test_webhook_503_when_unconfigured():
    with TestClient(app) as client:
        res = client.post("/api/billing/webhook", content=b"{}")
        assert res.status_code == 503


def test_webhook_ignores_unpaid_session(stripe_env):
    with TestClient(app) as client:
        user = _onboard(client)
        payload, headers = _signed_payload("whsec_test_123", _completed_event(user["id"], paid=False))
        res = client.post("/api/billing/webhook", content=payload, headers=headers)
        assert res.status_code == 200
        assert res.json()["upgraded"] is False
        assert not billing.is_pro(user["id"])


def test_webhook_falls_back_to_email_match(stripe_env):
    with TestClient(app) as client:
        user = _onboard(client, email="fallback@example.com")
        event = _completed_event(user_id="")  # no metadata user_id
        event["data"]["object"]["client_reference_id"] = None
        event["data"]["object"]["customer_details"] = {"email": "fallback@example.com"}
        payload, headers = _signed_payload("whsec_test_123", event)
        res = client.post("/api/billing/webhook", content=payload, headers=headers)
        assert res.status_code == 200
        assert res.json()["upgraded"] is True
        assert billing.is_pro(user["id"])
