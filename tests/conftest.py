"""pytest setup that runs before test module imports."""

from __future__ import annotations

import os
import tempfile

os.environ.setdefault(
    "VERIDROP_IMAGE_CACHE_DIR",
    tempfile.mkdtemp(prefix="veridrop-test-jobs-"),
)
os.environ.setdefault(
    "VERIDROP_WISHLIST_PATH",
    tempfile.mkstemp(prefix="veridrop-test-wishlist-")[1],
)
os.environ.setdefault("VERIDROP_STORAGE_BACKEND", "memory")
os.environ.setdefault("VERIDROP_SESSION_SECRET", "test-session-secret")
