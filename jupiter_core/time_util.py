"""TTL arithmetic and timestamp rendering.

Ported from jupiter-code's lib/time.ts and lib/expiry.ts.

Two rules carried over unchanged:

  1. A claim's life is measured from ``refreshed_at``, never from
     ``locked_at`` - ``locked_at`` stays put so sort order is stable.
  2. A claim never outlives its session. Even well inside the TTL, a claim
     whose session has ended is gone.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

DEFAULT_LOCK_TTL = 300
MIN_LOCK_TTL = 5
MIN_SESSION_TTL = 600

_INT_RE = re.compile(r"^[+-]?\d+$")


def now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat(value: datetime | None) -> str | None:
    """Render a timestamp the way every existing Jupiter client expects.

    Seconds precision, literal ``Z``, no offset -
    e.g. ``2026-09-21T14:33:28Z``.
    """
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def lock_ttl_from(raw: str | int | None) -> int:
    """Seconds an unrefreshed claim stays active, from a raw ``JUPITER_LOCK_TTL``.

    Unparseable values fall back to the default rather than failing.
    """
    if raw is None or raw == "":
        return DEFAULT_LOCK_TTL
    text = str(raw).strip()
    if not _INT_RE.match(text):
        return DEFAULT_LOCK_TTL
    try:
        value = int(text)
    except ValueError:
        return DEFAULT_LOCK_TTL
    return max(value, MIN_LOCK_TTL)


def session_ttl_from(lock_ttl: int) -> int:
    return max(2 * lock_ttl, MIN_SESSION_TTL)


def expires_at(refreshed_at: datetime, lock_ttl: int) -> datetime:
    return refreshed_at + timedelta(seconds=lock_ttl)


def lock_cutoff(now_: datetime, lock_ttl: int) -> datetime:
    return now_ - timedelta(seconds=lock_ttl)


def session_cutoff(now_: datetime, lock_ttl: int) -> datetime:
    return now_ - timedelta(seconds=session_ttl_from(lock_ttl))
