"""API-key minting, hashing and verification.

Ported from jupiter-code's lib/auth.ts and lib/principal.ts.

Key format:

    jpm_<member_id>_<secret>     member key
    jpa_<org_id>_<secret>        org admin key

The secret is 32 random bytes, URL-safe base64 (no padding). It may itself
contain ``_``, so parsing splits on the first two underscores only.

Digest = SHA-256(key), or HMAC-SHA-256(key, JUPITER_KEY_PEPPER) if that env
var is set; stored as 64 lowercase hex chars.

``verify_key`` always computes the digest and always runs the comparison via
``hmac.compare_digest``, even when the stored hash is missing or malformed,
so a nonexistent record costs the same wall-clock time as a mismatch.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass

MEMBER_PREFIX = "jpm"
ADMIN_PREFIX = "jpa"

SECRET_BYTES = 32
MAX_KEY_LENGTH = 512

MIN_RECORD_ID = 1
MAX_RECORD_ID = 2**53 - 1  # mirrors Number.MAX_SAFE_INTEGER on the TS side

_DIGIT_RE = re.compile(r"^\d+$")
_HEX_RE = re.compile(r"^[0-9a-f]+$")


class InvalidKey(Exception):
    pass


def _token_urlsafe(nbytes: int) -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(nbytes)).rstrip(b"=").decode("ascii")


def mint_member_key(member_id: int | str) -> str:
    return f"{MEMBER_PREFIX}_{member_id}_{_token_urlsafe(SECRET_BYTES)}"


def mint_admin_key(org_id: int | str) -> str:
    return f"{ADMIN_PREFIX}_{org_id}_{_token_urlsafe(SECRET_BYTES)}"


@dataclass(frozen=True)
class ParsedKey:
    kind: str  # "member" | "admin"
    record_id: int


def parse_key(key: str | None) -> ParsedKey:
    trimmed = (key or "").strip()
    if not trimmed or len(trimmed) > MAX_KEY_LENGTH:
        raise InvalidKey("malformed key")

    first_sep = trimmed.find("_")
    if first_sep < 0:
        raise InvalidKey("malformed key")
    second_sep = trimmed.find("_", first_sep + 1)
    if second_sep < 0:
        raise InvalidKey("malformed key")

    prefix = trimmed[:first_sep]
    raw_id = trimmed[first_sep + 1 : second_sep]
    secret = trimmed[second_sep + 1 :]

    if not secret:
        raise InvalidKey("malformed key")

    if prefix == MEMBER_PREFIX:
        kind = "member"
    elif prefix == ADMIN_PREFIX:
        kind = "admin"
    else:
        raise InvalidKey("unknown key prefix")

    if not _DIGIT_RE.match(raw_id):
        raise InvalidKey("malformed key id")

    record_id = int(raw_id)
    if not (MIN_RECORD_ID <= record_id <= MAX_RECORD_ID):
        raise InvalidKey("key id out of range")

    return ParsedKey(kind=kind, record_id=record_id)


def _digest(key: str, pepper: str | None = None) -> bytes:
    data = key.encode("utf-8")
    if pepper:
        return hmac.new(pepper.encode("utf-8"), data, hashlib.sha256).digest()
    return hashlib.sha256(data).digest()


def hash_key(key: str, pepper: str | None = None) -> str:
    return _digest(key, pepper).hex()


def _from_hex(hex_str: str) -> bytes | None:
    if len(hex_str) != 64 or not _HEX_RE.match(hex_str):
        return None
    return bytes.fromhex(hex_str)


def verify_key(key: str, key_hash: str | None, pepper: str | None = None) -> bool:
    """Does `key` match `key_hash`?

    Always hashes and always compares, including when the stored hash is
    empty or malformed, so the answer costs the same whatever the reason for
    failure. An empty hash (the two-phase-mint placeholder) never verifies.
    """
    presented = _digest(key or "", pepper)
    stored = _from_hex((key_hash or "").strip())
    matched = hmac.compare_digest(presented, stored or b"\x00" * 32)
    return stored is not None and matched


MISSING_KEY = "missing API key (send 'Authorization: Bearer <key>' or 'X-API-Key: <key>')"


def extract_key(headers) -> str:
    """Pull the key out of a request's headers.

    `headers` is any mapping-like object with a case-insensitive `.get`
    (e.g. a `Headers`/`starlette.datastructures.Headers` instance, or a plain
    dict with lowercase keys).

    `X-API-Key` wins over `Authorization`; a bare `Authorization: <key>` with
    no scheme is accepted too.
    """
    from .errors import unauthorized

    api_key = headers.get("x-api-key")
    if api_key and api_key.strip():
        return api_key.strip()

    authorization = headers.get("authorization")
    if authorization:
        space = authorization.find(" ")
        if space < 0:
            scheme, token = authorization, ""
        else:
            scheme, token = authorization[:space], authorization[space + 1 :]
        if scheme.lower() == "bearer" and token.strip():
            return token.strip()
        if not token:
            return authorization.strip()

    raise unauthorized(MISSING_KEY)


@dataclass(frozen=True)
class Principal:
    kind: str  # "member" | "admin"
    org_id: int
    slug: str
    member_id: int | None
    display_name: str | None


def principal_from_key(key: str, conn) -> Principal:
    """Resolve a key to a Principal using a sync psycopg Connection/cursor."""
    from .config import key_pepper
    from .errors import unauthorized

    try:
        parsed = parse_key(key)
    except InvalidKey as error:
        raise unauthorized(f"invalid API key: {error}") from error

    pepper = key_pepper()

    if parsed.kind == "member":
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT m.id, m.org_id, m.display_name, m.api_key_hash, o.slug
                  FROM members m
                  LEFT JOIN organizations o ON o.id = m.org_id
                 WHERE m.id = %s
                """,
                (parsed.record_id,),
            )
            row = cur.fetchone()
        stored_hash = row[3] if row else None
        ok = verify_key(key, stored_hash, pepper)
        if not row or not ok:
            raise unauthorized("invalid API key")
        return Principal(
            kind="member",
            org_id=int(row[1]),
            slug=row[4],
            member_id=int(row[0]),
            display_name=row[2],
        )

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, slug, admin_key_hash FROM organizations WHERE id = %s",
            (parsed.record_id,),
        )
        row = cur.fetchone()
    stored_hash = row[2] if row else None
    ok = verify_key(key, stored_hash, pepper)
    if not row or not ok:
        raise unauthorized("invalid API key")
    return Principal(kind="admin", org_id=int(row[0]), slug=row[1], member_id=None, display_name=None)


async def principal_from_key_async(key: str, aconn) -> Principal:
    """Async twin of `principal_from_key`, for the asyncio call sites
    (AgentFlow tools, the MCP server)."""
    from .config import key_pepper
    from .errors import unauthorized

    try:
        parsed = parse_key(key)
    except InvalidKey as error:
        raise unauthorized(f"invalid API key: {error}") from error

    pepper = key_pepper()

    if parsed.kind == "member":
        async with aconn.cursor() as cur:
            await cur.execute(
                """
                SELECT m.id, m.org_id, m.display_name, m.api_key_hash, o.slug
                  FROM members m
                  LEFT JOIN organizations o ON o.id = m.org_id
                 WHERE m.id = %s
                """,
                (parsed.record_id,),
            )
            row = await cur.fetchone()
        stored_hash = row[3] if row else None
        ok = verify_key(key, stored_hash, pepper)
        if not row or not ok:
            raise unauthorized("invalid API key")
        return Principal(
            kind="member",
            org_id=int(row[1]),
            slug=row[4],
            member_id=int(row[0]),
            display_name=row[2],
        )

    async with aconn.cursor() as cur:
        await cur.execute(
            "SELECT id, slug, admin_key_hash FROM organizations WHERE id = %s",
            (parsed.record_id,),
        )
        row = await cur.fetchone()
    stored_hash = row[2] if row else None
    ok = verify_key(key, stored_hash, pepper)
    if not row or not ok:
        raise unauthorized("invalid API key")
    return Principal(kind="admin", org_id=int(row[0]), slug=row[1], member_id=None, display_name=None)


def require_member(principal: Principal) -> Principal:
    """A member key. Admin keys are rejected with 403."""
    from .errors import forbidden

    if principal.kind != "member" or principal.member_id is None:
        raise forbidden("this endpoint requires a member API key")
    return principal


def require_org_access(principal: Principal, org_id: int) -> None:
    from .errors import forbidden

    if principal.org_id != org_id:
        raise forbidden("key does not belong to this org")
