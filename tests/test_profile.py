from fastapi.testclient import TestClient

from backend import db
from backend.main import app
from test_api import _onboard


def test_update_user_profile_fields():
    with TestClient(app) as client:
        user = _onboard(client, email="profile1@example.com")
        res = client.patch(
            f"/api/users/{user['id']}",
            json={"display_name": "Nueva Ada", "native_lang": "fr", "target_lang": "de"},
        )
        assert res.status_code == 200
        updated = res.json()
        assert updated["display_name"] == "Nueva Ada"
        assert updated["native_lang"] == "fr"
        assert updated["target_lang"] == "de"


def test_update_user_rejects_empty_display_name():
    with TestClient(app) as client:
        user = _onboard(client, email="profile2@example.com")
        res = client.patch(f"/api/users/{user['id']}", json={"display_name": "   "})
        assert res.status_code == 422


def test_delete_user_removes_account_and_related_rows():
    with TestClient(app) as client:
        user = _onboard(client, email="profile3@example.com")
        field_id = client.get("/api/academy/fields").json()[0]["id"]
        client.post(f"/api/academy/{user['id']}/enroll", json={"field_id": field_id, "level": "ASSOCIATE"})

        res = client.delete(f"/api/users/{user['id']}")
        assert res.status_code == 200
        assert res.json()["deleted"] is True

        with db.cursor() as cur:
            cur.execute("SELECT 1 FROM users WHERE id=?", (user["id"],))
            assert cur.fetchone() is None
            cur.execute("SELECT 1 FROM academy_enrollment WHERE user_id=?", (user["id"],))
            assert cur.fetchone() is None

        # The session cookie was cleared server-side — the account is gone.
        session_res = client.get("/api/session")
        assert session_res.json()["authenticated"] is False


def test_delete_user_requires_ownership():
    with TestClient(app) as client:
        user_a = _onboard(client, email="profile4a@example.com")

    with TestClient(app) as client2:
        _onboard(client2, email="profile4b@example.com")
        res = client2.delete(f"/api/users/{user_a['id']}")
        assert res.status_code == 403
