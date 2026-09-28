"""Environment access. Ported from jupiter-code's lib/config.ts."""

from __future__ import annotations

import os

from .errors import JupiterError
from .time_util import lock_ttl_from, session_ttl_from

VERSION = "0.3.0"

ANNOUNCEMENT_WINDOW = 3600
ANNOUNCEMENT_LIMIT = 20
ANNOUNCEMENT_MAX_LIMIT = 100
ANNOUNCEMENT_MAX_LENGTH = 280

NAME_MAX_LENGTH = 120

SNIPPET_MAX_LENGTH = 4000


def store_snippets() -> bool:
    """Whether to persist the claimed lines' source alongside a claim.

    Off unless explicitly enabled. Joining a team is open by design and keys
    cannot be revoked (see the README's "What this does not do"), so storing
    source raises the stakes of a leaked slug or key from "they see your
    filenames" to "they read your code". That has to be a deliberate choice.
    """
    return (os.environ.get("JUPITER_STORE_SNIPPETS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def lock_ttl() -> int:
    return lock_ttl_from(os.environ.get("JUPITER_LOCK_TTL"))


def session_ttl() -> int:
    return session_ttl_from(lock_ttl())


def key_pepper() -> str | None:
    return os.environ.get("JUPITER_KEY_PEPPER") or None


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise JupiterError(
            503,
            "DATABASE_URL is not set. Copy .env.example to .env, add your Neon "
            "connection string, run `python -m jupiter_admin db-push`, then restart.",
        )
    return url
