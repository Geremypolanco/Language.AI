from backend import db


class _FakeCursor:
    def __init__(self):
        self.last_query = None
        self.last_params = None

    def execute(self, query, params=()):
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        return {"ok": 1}

    def fetchall(self):
        return [{"ok": 1}]

    def close(self):
        pass


def test_cursor_proxy_translates_placeholders_for_postgres():
    fake = _FakeCursor()
    proxy = db._CursorProxy(fake, translate=True)
    proxy.execute("SELECT * FROM users WHERE id=? AND email=?", ("u1", "a@b.com"))
    assert fake.last_query == "SELECT * FROM users WHERE id=%s AND email=%s"
    assert fake.last_params == ("u1", "a@b.com")


def test_cursor_proxy_leaves_sqlite_placeholders_untouched():
    fake = _FakeCursor()
    proxy = db._CursorProxy(fake, translate=False)
    proxy.execute("SELECT * FROM users WHERE id=?", ("u1",))
    assert fake.last_query == "SELECT * FROM users WHERE id=?"


def test_cursor_proxy_delegates_fetch_and_close():
    fake = _FakeCursor()
    proxy = db._CursorProxy(fake, translate=False)
    assert proxy.fetchone() == {"ok": 1}
    assert proxy.fetchall() == [{"ok": 1}]
    proxy.close()  # should not raise


def test_reset_for_tests_clears_supabase_url(tmp_path):
    db.reset_for_tests(str(tmp_path / "other.db"))
    assert db.settings.supabase_db_url == ""
    assert db._is_postgres() is False


def test_row_to_dict_parses_interests_json():
    row = {"id": "u1", "interests": '["music", "chess"]'}
    result = db.row_to_dict(row)
    assert result["interests"] == ["music", "chess"]


def test_row_to_dict_handles_none():
    assert db.row_to_dict(None) is None
