"""MongoDB-backed persistence for web reports and admin accounts.

The detection payload can contain arbitrary upstream JSON. MongoDB rejects
keys with special shapes in some contexts, so reports are stored as a JSON
string and indexed metadata is duplicated into top-level fields.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse


REPORTS_COLLECTION = "reports"
ADMINS_COLLECTION = "admins"
API_TOKENS_COLLECTION = "api_tokens"
SYSTEM_API_TOKEN_ID = "system"

_CLIENT: Any | None = None
_DB: Any | None = None
_SETTINGS: "MongoSettings | None" = None
_LOCK = threading.Lock()

_MEMORY_REPORTS: dict[str, dict[str, Any]] = {}
_MEMORY_ADMINS: dict[str, dict[str, Any]] = {}
_MEMORY_API_TOKENS: dict[str, dict[str, Any]] = {}


@dataclass(frozen=True)
class MongoSettings:
    connection_string: str
    database_name: str
    initial_admin_username: str = ""
    initial_admin_password: str = ""


@dataclass(frozen=True)
class StoredReport:
    job_id: str
    protocol: str
    domain: str
    timestamp: datetime | None
    report: dict[str, Any]


def storage_backend() -> str:
    """Return the active persistence backend.

    Production defaults to MongoDB. Tests may set VERIDROP_STORAGE_BACKEND=memory
    to avoid an external service.
    """
    return os.environ.get("VERIDROP_STORAGE_BACKEND", "mongo").strip().lower()


def using_mongo() -> bool:
    return storage_backend() == "mongo"


def load_settings() -> MongoSettings:
    global _SETTINGS
    if _SETTINGS is not None:
        return _SETTINGS

    data = _load_config_file()
    mongodb = data.get("mongodb") if isinstance(data.get("mongodb"), dict) else {}
    admin = data.get("admin") if isinstance(data.get("admin"), dict) else {}

    connection_string = (
        os.environ.get("VERIDROP_MONGODB_URI")
        or os.environ.get("MONGODB_CONNECTION_STRING")
        or str(mongodb.get("connection_string") or "")
    ).strip()
    database_name = (
        os.environ.get("VERIDROP_MONGODB_DATABASE")
        or os.environ.get("MONGODB_DATABASE_NAME")
        or str(mongodb.get("database_name") or "")
    ).strip()

    initial_admin_username = (
        os.environ.get("VERIDROP_ADMIN_USERNAME")
        or str(admin.get("initial_username") or "")
    ).strip()
    initial_admin_password = (
        os.environ.get("VERIDROP_ADMIN_PASSWORD")
        or str(admin.get("initial_password") or "")
    )

    if using_mongo() and (not connection_string or not database_name):
        path = _config_path()
        raise RuntimeError(
            "MongoDB persistence is enabled, but MongoDB connection settings "
            f"are missing. Configure {path}, VERIDROP_MONGODB_URI, or "
            "MONGODB_CONNECTION_STRING."
        )

    _SETTINGS = MongoSettings(
        connection_string=connection_string,
        database_name=database_name,
        initial_admin_username=initial_admin_username,
        initial_admin_password=initial_admin_password,
    )
    return _SETTINGS


def init_store() -> None:
    """Initialize Mongo collections and indexes."""
    if not using_mongo():
        return
    db = get_db()
    db[REPORTS_COLLECTION].create_index([("domain", 1), ("protocol", 1), ("timestamp", -1)])
    db[REPORTS_COLLECTION].create_index([("protocol", 1), ("timestamp", -1)])
    db[REPORTS_COLLECTION].create_index([("timestamp", -1)])
    db[ADMINS_COLLECTION].create_index("username", unique=True)
    db[API_TOKENS_COLLECTION].create_index("token_prefix")


def close_store() -> None:
    global _CLIENT, _DB
    with _LOCK:
        if _CLIENT is not None:
            _CLIENT.close()
        _CLIENT = None
        _DB = None


def get_db() -> Any:
    if not using_mongo():
        raise RuntimeError("MongoDB backend is not active")

    global _CLIENT, _DB
    if _DB is not None:
        return _DB

    with _LOCK:
        if _DB is not None:
            return _DB
        settings = load_settings()
        try:
            from pymongo import MongoClient
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "PyMongo is required for MongoDB persistence. Install the web "
                "extra with `pip install -e .[web]`."
            ) from exc

        timeout_ms = int(os.environ.get("VERIDROP_MONGODB_TIMEOUT_MS", "5000"))
        _CLIENT = MongoClient(
            settings.connection_string,
            serverSelectionTimeoutMS=timeout_ms,
        )
        _CLIENT.admin.command("ping")
        _DB = _CLIENT[settings.database_name]
        return _DB


def save_report(job_id: str, protocol: str, report: dict[str, Any]) -> None:
    doc = _report_to_doc(job_id, protocol, report)
    if not using_mongo():
        _MEMORY_REPORTS[job_id] = doc
        return
    get_db()[REPORTS_COLLECTION].replace_one({"_id": job_id}, doc, upsert=True)


def get_report(job_id: str) -> dict[str, Any] | None:
    if not using_mongo():
        doc = _MEMORY_REPORTS.get(job_id)
    else:
        doc = get_db()[REPORTS_COLLECTION].find_one({"_id": job_id})
    if not doc:
        return None
    return _decode_report_doc(doc)


def iter_reports(domain: str | None = None) -> Iterable[StoredReport]:
    if not using_mongo():
        docs = list(_MEMORY_REPORTS.values())
        if domain:
            docs = [d for d in docs if d.get("domain") == domain]
        docs.sort(key=lambda d: d.get("timestamp") or datetime.min, reverse=True)
        for doc in docs:
            stored = _stored_report_from_doc(doc)
            if stored is not None:
                yield stored
        return

    query: dict[str, Any] = {}
    if domain:
        query["domain"] = domain
    cursor = get_db()[REPORTS_COLLECTION].find(query).sort("timestamp", -1)
    for doc in cursor:
        stored = _stored_report_from_doc(doc)
        if stored is not None:
            yield stored


def admin_count() -> int:
    if not using_mongo():
        return len(_MEMORY_ADMINS)
    return int(get_db()[ADMINS_COLLECTION].count_documents({}))


def get_admin(username: str) -> dict[str, Any] | None:
    username = username.strip()
    if not username:
        return None
    if not using_mongo():
        doc = _MEMORY_ADMINS.get(username)
        return dict(doc) if doc else None
    doc = get_db()[ADMINS_COLLECTION].find_one({"username": username})
    return dict(doc) if doc else None


def create_admin(username: str, password_hash: str) -> None:
    now = datetime.now(timezone.utc)
    doc = {
        "username": username.strip(),
        "password_hash": password_hash,
        "role": "admin",
        "created_at": now,
        "updated_at": now,
    }
    if not doc["username"]:
        raise ValueError("admin username is required")

    if not using_mongo():
        if doc["username"] in _MEMORY_ADMINS:
            return
        _MEMORY_ADMINS[doc["username"]] = doc
        return

    get_db()[ADMINS_COLLECTION].update_one(
        {"username": doc["username"]},
        {"$setOnInsert": doc},
        upsert=True,
    )


def get_system_api_token() -> dict[str, Any] | None:
    if not using_mongo():
        doc = _MEMORY_API_TOKENS.get(SYSTEM_API_TOKEN_ID)
        return dict(doc) if doc else None
    doc = get_db()[API_TOKENS_COLLECTION].find_one({"_id": SYSTEM_API_TOKEN_ID})
    return dict(doc) if doc else None


def save_system_api_token(
    *,
    token_hash: str,
    token_prefix: str,
    updated_by: str,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    update = {
        "$set": {
            "token_hash": token_hash,
            "token_prefix": token_prefix,
            "updated_by": updated_by,
            "updated_at": now,
        },
        "$setOnInsert": {
            "_id": SYSTEM_API_TOKEN_ID,
            "created_by": updated_by,
            "created_at": now,
        },
    }

    if not using_mongo():
        existing = _MEMORY_API_TOKENS.get(SYSTEM_API_TOKEN_ID, {})
        doc = {
            **existing,
            "_id": SYSTEM_API_TOKEN_ID,
            "token_hash": token_hash,
            "token_prefix": token_prefix,
            "updated_by": updated_by,
            "updated_at": now,
            "created_by": existing.get("created_by", updated_by),
            "created_at": existing.get("created_at", now),
        }
        _MEMORY_API_TOKENS[SYSTEM_API_TOKEN_ID] = doc
        return dict(doc)

    coll = get_db()[API_TOKENS_COLLECTION]
    coll.update_one({"_id": SYSTEM_API_TOKEN_ID}, update, upsert=True)
    doc = coll.find_one({"_id": SYSTEM_API_TOKEN_ID})
    return dict(doc) if doc else {}


def _config_path() -> Path:
    return Path(os.environ.get("VERIDROP_MONGODB_CONFIG", "mongodb_config.yaml"))


def _load_config_file() -> dict[str, Any]:
    path = _config_path()
    if not path.is_file():
        return {}
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError(
            "PyYAML is required to read mongodb_config.yaml. Install the web "
            "extra with `pip install -e .[web]`."
        ) from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must contain a YAML object")
    return data


def _report_to_doc(job_id: str, protocol: str, report: dict[str, Any]) -> dict[str, Any]:
    timestamp = _parse_timestamp(report.get("timestamp"))
    domain = _extract_domain(str(report.get("base_url") or ""))
    return {
        "_id": job_id,
        "job_id": job_id,
        "protocol": protocol,
        "domain": domain,
        "base_url": str(report.get("base_url") or ""),
        "target_model": str(report.get("target_model") or ""),
        "mode": str(report.get("mode") or ""),
        "total_score": float(report.get("total_score") or 0.0),
        "verdict": str(report.get("verdict") or ""),
        "timestamp": timestamp or datetime.now(timezone.utc),
        "report_json": json.dumps(report, ensure_ascii=False),
        "updated_at": datetime.now(timezone.utc),
    }


def _stored_report_from_doc(doc: dict[str, Any]) -> StoredReport | None:
    report = _decode_report_doc(doc)
    if report is None:
        return None
    return StoredReport(
        job_id=str(doc.get("job_id") or doc.get("_id") or ""),
        protocol=str(doc.get("protocol") or report.get("protocol") or "anthropic"),
        domain=str(doc.get("domain") or _extract_domain(str(report.get("base_url") or ""))),
        timestamp=_coerce_datetime(doc.get("timestamp")) or _parse_timestamp(report.get("timestamp")),
        report=report,
    )


def _decode_report_doc(doc: dict[str, Any]) -> dict[str, Any] | None:
    raw = doc.get("report_json")
    if isinstance(raw, str):
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else None
        except json.JSONDecodeError:
            return None
    legacy = doc.get("report")
    return legacy if isinstance(legacy, dict) else None


def _extract_domain(base_url: str) -> str:
    if not base_url:
        return ""
    if "://" not in base_url:
        base_url = "https://" + base_url
    try:
        host = urlparse(base_url).hostname or ""
    except ValueError:
        return ""
    return host.lower()


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return _coerce_datetime(value)
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _coerce_datetime(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
