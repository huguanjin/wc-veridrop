from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from web import auth, mongo_store
from web.server import app, login_submit


def test_password_hash_verification():
    encoded = auth.hash_password("secret")

    assert encoded != "secret"
    assert auth.verify_password("secret", encoded)
    assert not auth.verify_password("wrong", encoded)


def test_api_token_hash_verification():
    mongo_store._MEMORY_API_TOKENS.clear()  # type: ignore[attr-defined]

    token, doc = auth.reset_system_api_token("admin")

    assert token.startswith("vdp_")
    assert doc["token_hash"] != token
    assert doc["token_prefix"] == token[:12]
    assert auth.verify_system_api_token(token)
    assert not auth.verify_system_api_token(token + "x")


def test_initial_admin_created_from_settings(monkeypatch):
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        mongo_store,
        "_SETTINGS",
        mongo_store.MongoSettings(
            connection_string="",
            database_name="test",
            initial_admin_username="admin",
            initial_admin_password="secret",
        ),
    )

    result = auth.ensure_initial_admin()

    assert result.created is True
    assert auth.authenticate("admin", "secret")
    assert not auth.authenticate("admin", "wrong")


def test_login_sets_admin_session():
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    mongo_store.create_admin("admin", auth.hash_password("secret"))

    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret")

    @app.post("/login")
    async def route(request: Request):
        form = await request.form()
        return await login_submit(
            request,
            username=str(form.get("username") or ""),
            password=str(form.get("password") or ""),
            next=str(form.get("next") or "/admin"),
        )

    client = TestClient(app)
    response = client.post(
        "/login",
        data={"username": "admin", "password": "secret", "next": "/admin"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert "session=" in response.headers["set-cookie"]


def test_home_redirects_to_login_when_not_authenticated(monkeypatch):
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        mongo_store,
        "_SETTINGS",
        mongo_store.MongoSettings(
            connection_string="",
            database_name="test",
            initial_admin_username="admin",
            initial_admin_password="secret",
        ),
    )

    with TestClient(app) as client:
        response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login?next=%2F"


def test_api_returns_401_when_not_authenticated(monkeypatch):
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        mongo_store,
        "_SETTINGS",
        mongo_store.MongoSettings(
            connection_string="",
            database_name="test",
            initial_admin_username="admin",
            initial_admin_password="secret",
        ),
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/probe",
            data={"base_url": "https://relay.example.com/v1", "api_key": "sk-test-key"},
        )

    assert response.status_code == 401
    assert response.json() == {"detail": "admin login required"}


def test_logged_in_pages_show_admin_nav(monkeypatch):
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        mongo_store,
        "_SETTINGS",
        mongo_store.MongoSettings(
            connection_string="",
            database_name="test",
            initial_admin_username="admin",
            initial_admin_password="secret",
        ),
    )

    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "secret", "next": "/"},
            follow_redirects=False,
        )
        response = client.get("/")

    assert login.status_code == 303
    assert response.status_code == 200
    assert 'href="/admin"' in response.text
    assert 'action="/logout"' in response.text


def test_api_allows_valid_bearer_token(monkeypatch):
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    mongo_store._MEMORY_API_TOKENS.clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        mongo_store,
        "_SETTINGS",
        mongo_store.MongoSettings(
            connection_string="",
            database_name="test",
            initial_admin_username="admin",
            initial_admin_password="secret",
        ),
    )
    token, _doc = auth.reset_system_api_token("admin")

    with TestClient(app) as client:
        response = client.post(
            "/api/probe",
            headers={"Authorization": f"Bearer {token}"},
            data={"base_url": "not-a-url", "api_key": "sk-test-key"},
        )

    assert response.status_code == 200
    assert response.json()["error"] == "base_url must start with http(s)://"


def test_admin_can_reset_api_token(monkeypatch):
    mongo_store._MEMORY_ADMINS.clear()  # type: ignore[attr-defined]
    mongo_store._MEMORY_API_TOKENS.clear()  # type: ignore[attr-defined]
    monkeypatch.setattr(
        mongo_store,
        "_SETTINGS",
        mongo_store.MongoSettings(
            connection_string="",
            database_name="test",
            initial_admin_username="admin",
            initial_admin_password="secret",
        ),
    )

    with TestClient(app) as client:
        login = client.post(
            "/login",
            data={"username": "admin", "password": "secret", "next": "/admin"},
            follow_redirects=False,
        )
        response = client.post("/admin/api-token/reset", follow_redirects=False)

    doc = mongo_store.get_system_api_token()
    assert login.status_code == 303
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"
    assert doc is not None
    assert doc["updated_by"] == "admin"
