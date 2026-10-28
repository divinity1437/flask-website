import os

os.environ.setdefault("ENABLE_DONATION_LISTENER", "false")

from app import create_app


def test_home_uses_canonical_domain():
    app = create_app({"TESTING": True, "ENABLE_DONATION_LISTENER": False})
    response = app.test_client().get("/")
    assert response.status_code == 200
    assert b"osuokayu.pw" in response.data


def test_oauth_login_includes_state():
    app = create_app({"TESTING": True, "ENABLE_DONATION_LISTENER": False})
    app.config["SESSION_COOKIE_SECURE"] = False
    client = app.test_client()
    with client.session_transaction() as session:
        session["_csrf_token"] = "csrf-token"
    response = client.get("/auth/login")
    assert response.status_code == 302
    assert "state=" in response.headers["Location"]


def test_post_without_csrf_is_rejected():
    app = create_app({"TESTING": True, "ENABLE_DONATION_LISTENER": False})
    response = app.test_client().post("/inspector", data={"username": "example"})
    assert response.status_code == 400


def test_invalid_submode_does_not_crash():
    app = create_app({"TESTING": True, "ENABLE_DONATION_LISTENER": False})
    client = app.test_client()
    with client.session_transaction() as session:
        from security import csrf_token
        session["_csrf_token"] = "csrf-token"
    response = client.post("/inspector", data={"csrf_token": "csrf-token", "username": "", "submode": "invalid"})
    assert response.status_code == 200
