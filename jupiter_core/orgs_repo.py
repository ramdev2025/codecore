"""Organizations and members. Ported from jupiter-code's lib/orgs.ts.

Sync (psycopg.Connection) - only jupiter_admin calls this, and it has no
event loop.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from .auth import Principal, hash_key, mint_admin_key, mint_member_key
from .config import NAME_MAX_LENGTH, key_pepper, lock_ttl
from .errors import conflict, forbidden, not_found, unprocessable
from .slugify import resolve_slug, slugify
from .sweep import sweep_sync
from .time_util import isoformat, now as utcnow


@dataclass(frozen=True)
class OrgRow:
    id: int
    name: str
    slug: str
    admin_key_hash: str


def _is_unique_violation(error: Exception) -> bool:
    return isinstance(error, psycopg.errors.UniqueViolation)


def get_org_by_slug(conn: psycopg.Connection, slug: str) -> OrgRow:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, slug, admin_key_hash FROM organizations WHERE slug = %s", (slug,))
        row = cur.fetchone()
    if row is None:
        raise not_found(f"no such org: {slug}")
    return OrgRow(id=int(row[0]), name=row[1], slug=row[2], admin_key_hash=row[3])


def get_org_by_id(conn: psycopg.Connection, org_id: int) -> OrgRow:
    with conn.cursor() as cur:
        cur.execute("SELECT id, name, slug, admin_key_hash FROM organizations WHERE id = %s", (org_id,))
        row = cur.fetchone()
    if row is None:
        raise not_found("org no longer exists")
    return OrgRow(id=int(row[0]), name=row[1], slug=row[2], admin_key_hash=row[3])


def require_org_access(principal: Principal, org: OrgRow) -> None:
    if principal.org_id != org.id:
        raise forbidden("key does not belong to this org")


@dataclass(frozen=True)
class OrgCreated:
    org: str
    slug: str
    admin_api_key: str
    lock_ttl_seconds: int


def create_org(conn: psycopg.Connection, raw_name: str, raw_slug: str | None) -> OrgCreated:
    """Create a team. The admin key is minted in two phases - insert with an
    empty hash, read back the generated id, mint a key that embeds it, then
    store the digest."""
    name = (raw_name or "").strip()
    if not name:
        raise unprocessable("name must not be empty")
    if len(name) > NAME_MAX_LENGTH:
        raise unprocessable(f"name must be at most {NAME_MAX_LENGTH} characters")
    if raw_slug and not slugify(raw_slug):
        raise unprocessable("could not derive a slug; pass an explicit 'slug'")

    slug = resolve_slug(raw_slug, name)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO organizations (name, slug, admin_key_hash, created_at)
                VALUES (%s, %s, '', %s)
                RETURNING id
                """,
                (name, slug, utcnow()),
            )
            org_id = int(cur.fetchone()[0])
        conn.commit()
    except psycopg.errors.UniqueViolation as error:
        conn.rollback()
        raise conflict(f"org '{slug}' already exists") from error

    admin_key = mint_admin_key(org_id)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE organizations SET admin_key_hash = %s WHERE id = %s",
            (hash_key(admin_key, key_pepper()), org_id),
        )
    conn.commit()

    return OrgCreated(org=name, slug=slug, admin_api_key=admin_key, lock_ttl_seconds=lock_ttl())


@dataclass(frozen=True)
class MemberCreated:
    member_id: int
    display_name: str
    slug: str
    api_key: str


def join_org(conn: psycopg.Connection, slug: str, raw_name: str) -> MemberCreated:
    """Join a team by slug and receive a member key.

    Open by design: anyone who knows the slug can join.
    """
    display_name = (raw_name or "").strip()
    if not display_name:
        raise unprocessable("display_name must not be empty")
    if len(display_name) > NAME_MAX_LENGTH:
        raise unprocessable(f"display_name must be at most {NAME_MAX_LENGTH} characters")

    org = get_org_by_slug(conn, slug)

    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO members (org_id, display_name, api_key_hash, joined_at)
                VALUES (%s, %s, '', %s)
                RETURNING id
                """,
                (org.id, display_name, utcnow()),
            )
            member_id = int(cur.fetchone()[0])
        conn.commit()
    except psycopg.errors.UniqueViolation as error:
        conn.rollback()
        raise conflict(f"'{display_name}' is already a member of {slug}; reuse that member's API key") from error

    api_key = mint_member_key(member_id)
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE members SET api_key_hash = %s WHERE id = %s",
            (hash_key(api_key, key_pepper()), member_id),
        )
    conn.commit()

    return MemberCreated(member_id=member_id, display_name=display_name, slug=org.slug, api_key=api_key)


@dataclass(frozen=True)
class MemberOut:
    member_id: int
    display_name: str
    joined_at: str | None
    active_sessions: int
    last_seen: str | None


def list_members(conn: psycopg.Connection, org_id: int) -> list[MemberOut]:
    now = utcnow()
    sweep_sync(conn, org_id, now, lock_ttl())
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT m.id,
                   m.display_name,
                   m.joined_at,
                   COUNT(s.id) FILTER (WHERE s.ended_at IS NULL) AS active_sessions,
                   MAX(s.last_seen) AS last_seen
              FROM members m
              LEFT JOIN sessions s ON s.member_id = m.id
             WHERE m.org_id = %s
             GROUP BY m.id, m.display_name, m.joined_at
             ORDER BY m.display_name
            """,
            (org_id,),
        )
        rows = cur.fetchall()
    conn.commit()

    return [
        MemberOut(
            member_id=int(row[0]),
            display_name=row[1],
            joined_at=isoformat(row[2]),
            active_sessions=int(row[3]),
            last_seen=isoformat(row[4]),
        )
        for row in rows
    ]
