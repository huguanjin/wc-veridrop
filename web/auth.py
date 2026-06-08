"""Simple admin authentication helpers."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse

from . import mongo_store


_HASH_NAME = "pbkdf2_sha256"
_ITERATIONS = 310_000
_SALT_BYTES = 16
_DKLEN = 32
_SESSION_KEY = "admin_username"
_API_TOKEN_PREFIX = "vdp_"
_API_TOKEN_BYTES = 32


@dataclass(frozen=True)
class AdminBootstrapResult:
    created: bool
    username: str


def ensure_initial_admin() -> AdminBootstrapResult:
    """Create the first admin from config/env when the admin collection is empty."""
    if mongo_store.admin_count() > 0:
        return AdminBootstrapResult(created=False, username="")

    settings = mongo_store.load_settings()
    username = settings.initial_admin_username
    password = settings.initial_admin_password
    if not username or not password:
        raise RuntimeError(
            "No admin account exists. Set admin.initial_username and "
            "admin.initial_password in mongodb_config.yaml, or set "
            "VERIDROP_ADMIN_USERNAME and VERIDROP_ADMIN_PASSWORD."
        )
    if os.environ.get("VERIDROP_ENV") == "production" and password == "ChangeMe123!":
        raise RuntimeError(
            "Refusing to create the initial admin with the example password in "
            "production. Set VERIDROP_ADMIN_PASSWORD to a strong secret."
        )

    mongo_store.create_admin(username, hash_password(password))
    return AdminBootstrapResult(created=True, username=username)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        _ITERATIONS,
        dklen=_DKLEN,
    )
    return "$".join([
        _HASH_NAME,
        str(_ITERATIONS),
        _b64(salt),
        _b64(digest),
    ])


def verify_password(password: str, encoded: str) -> bool:
    try:
        name, iter_s, salt_s, digest_s = encoded.split("$", 3)
        if name != _HASH_NAME:
            return False
        iterations = int(iter_s)
        salt = _unb64(salt_s)
        expected = _unb64(digest_s)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=len(expected),
    )
    return hmac.compare_digest(actual, expected)


def authenticate(username: str, password: str) -> bool:
    admin = mongo_store.get_admin(username)
    if not admin:
        return False
    encoded = admin.get("password_hash")
    return isinstance(encoded, str) and verify_password(password, encoded)


def generate_api_token() -> str:
    return _API_TOKEN_PREFIX + secrets.token_urlsafe(_API_TOKEN_BYTES)


def hash_api_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def api_token_prefix(token: str) -> str:
    return token[:12]


def reset_system_api_token(updated_by: str) -> tuple[str, dict[str, Any]]:
    token = generate_api_token()
    doc = mongo_store.save_system_api_token(
        token_hash=hash_api_token(token),
        token_prefix=api_token_prefix(token),
        updated_by=updated_by,
    )
    return token, doc


def verify_system_api_token(token: str) -> bool:
    token = token.strip()
    if not token:
        return False
    doc = mongo_store.get_system_api_token()
    if not doc:
        return False
    expected = doc.get("token_hash")
    return isinstance(expected, str) and hmac.compare_digest(
        hash_api_token(token),
        expected,
    )


def api_token_from_request(request: Request) -> str:
    auth_header = request.headers.get("authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return request.headers.get("x-api-token", "").strip()


def has_valid_api_token(request: Request) -> bool:
    return verify_system_api_token(api_token_from_request(request))


def login_session(request: Request, username: str) -> None:
    request.session[_SESSION_KEY] = username


def logout_session(request: Request) -> None:
    request.session.pop(_SESSION_KEY, None)


def current_admin(request: Request) -> dict[str, Any] | None:
    username = request.session.get(_SESSION_KEY)
    if not isinstance(username, str):
        return None
    return mongo_store.get_admin(username)


def require_admin(request: Request) -> dict[str, Any]:
    admin = current_admin(request)
    if admin is None:
        raise HTTPException(status_code=401, detail="admin login required")
    return admin


def redirect_if_not_admin(request: Request, next_path: str) -> RedirectResponse | None:
    if current_admin(request) is not None:
        return None
    return RedirectResponse(f"/login?next={next_path}", status_code=303)


def session_secret() -> str:
    secret = os.environ.get("VERIDROP_SESSION_SECRET", "").strip()
    if secret:
        return secret
    if os.environ.get("VERIDROP_ENV") == "production":
        raise RuntimeError("VERIDROP_SESSION_SECRET must be set in production")
    return "dev-only-veridrop-session-secret-change-me"


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)
