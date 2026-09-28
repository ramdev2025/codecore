"""Org slugs. Ported from jupiter-code's lib/slugify.ts."""

from __future__ import annotations

import re
import secrets
import string

MAX_SLUG_LENGTH = 120

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_EDGE_DASH = re.compile(r"^-+|-+$")
_TRAILING_DASH = re.compile(r"-+$")


def slugify(value: str | None) -> str:
    slug = (value or "").strip().lower()
    slug = _NON_ALNUM.sub("-", slug)
    slug = _EDGE_DASH.sub("", slug)
    slug = slug[:MAX_SLUG_LENGTH]
    return _TRAILING_DASH.sub("", slug)


def generated_slug() -> str:
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(8))
    return f"team-{suffix}"


def resolve_slug(explicit: str | None, name: str) -> str:
    return slugify(explicit or name) or generated_slug()
