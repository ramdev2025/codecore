"""Developer teams: sub-groupings of members inside an org, capped by plan.

A team is purely a grouping — locks, claims and sessions stay org-wide.
The cap is enforced only at creation time, so an org that downgrades
keeps its over-cap teams (grandfathered) but cannot add more.
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from .billing_repo import settle_billing
from .config import NAME_MAX_LENGTH
from .errors import conflict, not_found, payment_required, unprocessable
from .plans import can_create_team, plan_for
from .time_util import isoformat, now as utcnow

_TEAMS_SQL = """
    SELECT t.id, t.name, t.created_at, m.id, m.display_name
      FROM teams t
      LEFT JOIN team_members tm ON tm.team_id = t.id
      LEFT JOIN members m ON m.id = tm.member_id
     WHERE t.org_id = %s
     ORDER BY t.name, m.display_name
"""


@dataclass(frozen=True)
class TeamMemberOut:
    member_id: int
    display_name: str


@dataclass(frozen=True)
class TeamOut:
    team_id: int
    name: str
    created_at: str | None
    members: list


def _to_teams(rows) -> list[TeamOut]:
    """Fold the joined rows — one row per (team, member) pair — into teams."""
    teams: dict[int, TeamOut] = {}
    order: list[int] = []
    for row in rows:
        team_id = int(row[0])
        if team_id not in teams:
            teams[team_id] = TeamOut(team_id=team_id, name=row[1], created_at=isoformat(row[2]), members=[])
            order.append(team_id)
        if row[3] is not None:
            teams[team_id].members.append(TeamMemberOut(member_id=int(row[3]), display_name=row[4]))
    return [teams[team_id] for team_id in order]


async def list_teams(aconn, org_id: int) -> list[TeamOut]:
    async with aconn.cursor() as cur:
        await cur.execute(_TEAMS_SQL, (org_id,))
        rows = await cur.fetchall()
    return _to_teams(rows)


async def _team_org(aconn, org_id: int, team_id: int) -> int | None:
    """The org a team belongs to, or None — a foreign team reads as absent."""
    async with aconn.cursor() as cur:
        await cur.execute("SELECT org_id FROM teams WHERE id = %s", (team_id,))
        row = await cur.fetchone()
    return int(row[0]) if row else None


async def _require_team(aconn, org_id: int, team_id: int) -> None:
    owner = await _team_org(aconn, team_id)
    if owner is None or owner != org_id:
        raise not_found(f"no such team: {team_id}")


async def create_team(aconn, principal, raw_name: str) -> TeamOut:
    """Create a developer team, enforcing the plan's cap.

    Settles billing first, so the cap checked against is current. The
    name validation mirrors ``join_org``: strip, non-empty, length cap,
    UniqueViolation -> 409.
    """
    name = (raw_name or "").strip()
    if not name:
        raise unprocessable("name must not be empty")
    if len(name) > NAME_MAX_LENGTH:
        raise unprocessable(f"name must be at most {NAME_MAX_LENGTH} characters")

    await settle_billing(aconn, principal.org_id)

    async with aconn.cursor() as cur:
        await cur.execute("SELECT plan FROM organizations WHERE id = %s", (principal.org_id,))
        row = await cur.fetchone()
        if row is None:
            raise not_found("org no longer exists")
        plan = plan_for(row[0])

        await cur.execute("SELECT COUNT(*) FROM teams WHERE org_id = %s", (principal.org_id,))
        existing = int((await cur.fetchone())[0])

        if not can_create_team(plan.key, existing):
            raise payment_required(
                f"plan '{plan.key}' allows {plan.max_teams} developer teams — "
                f"upgrade to create more (currently {existing})"
            )

        try:
            await cur.execute(
                "INSERT INTO teams (org_id, name, created_at) VALUES (%s, %s, %s) RETURNING id, created_at",
                (principal.org_id, name, utcnow()),
            )
            inserted = await cur.fetchone()
        except psycopg.errors.UniqueViolation as error:
            raise conflict(f"team '{name}' already exists") from error

    return TeamOut(team_id=int(inserted[0]), name=name, created_at=isoformat(inserted[1]), members=[])


async def delete_team(aconn, org_id: int, team_id: int) -> dict:
    """Delete a team. Its memberships cascade; the members themselves stay."""
    await _require_team(aconn, org_id, team_id)
    async with aconn.cursor() as cur:
        await cur.execute("DELETE FROM teams WHERE id = %s", (team_id,))
    return {"deleted": True, "team_id": team_id}


async def add_team_member(aconn, org_id: int, team_id: int, member_id: int) -> dict:
    """Add an org member to a team. Duplicate adds are idempotent."""
    await _require_team(aconn, org_id, team_id)

    async with aconn.cursor() as cur:
        await cur.execute(
            "SELECT id, display_name FROM members WHERE id = %s AND org_id = %s",
            (member_id, org_id),
        )
        row = await cur.fetchone()
        if row is None:
            # A foreign member reads as absent, not forbidden — same rule
            # as a foreign session.
            raise not_found(f"no such member: {member_id}")

        await cur.execute(
            """
            INSERT INTO team_members (team_id, member_id)
            VALUES (%s, %s)
            ON CONFLICT (team_id, member_id) DO NOTHING
            """,
            (team_id, member_id),
        )

    return {"team_id": team_id, "member_id": member_id, "display_name": row[1], "added": True}


async def remove_team_member(aconn, org_id: int, team_id: int, member_id: int) -> dict:
    await _require_team(aconn, org_id, team_id)
    async with aconn.cursor() as cur:
        await cur.execute(
            "DELETE FROM team_members WHERE team_id = %s AND member_id = %s",
            (team_id, member_id),
        )
    return {"team_id": team_id, "member_id": member_id, "removed": True}
