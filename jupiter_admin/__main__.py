"""Jupiter admin CLI: bootstrap and inspect a Jupiter deployment.

Usage: python -m jupiter_admin <command> [options]

Commands: db-push, create-org, join, list-members, semantic-status, whoami.

No web dashboard for v1 - this CLI covers the same bootstrap flow
jupiter-code's setup wizard did.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv()

from jupiter_core.auth import parse_key, verify_key, InvalidKey
from jupiter_core.config import key_pepper
from jupiter_core.db import apply_schema, sync_connection
from jupiter_core.errors import JupiterError
from jupiter_core.orgs_repo import create_org, get_org_by_slug, join_org, list_members

from .render_cli import render_member_joined, render_org_created


def _fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    sys.exit(1)


def cmd_db_push(_args: argparse.Namespace) -> None:
    conn = sync_connection()
    try:
        apply_schema(conn)
    finally:
        conn.close()
    print("Schema applied.")


def cmd_create_org(args: argparse.Namespace) -> None:
    conn = sync_connection()
    try:
        try:
            result = create_org(conn, args.name, args.slug)
        except JupiterError as error:
            _fail(error.message)
            return
    finally:
        conn.close()
    print(render_org_created(result.org, result.slug, result.admin_api_key))


def cmd_join(args: argparse.Namespace) -> None:
    conn = sync_connection()
    try:
        try:
            result = join_org(conn, args.slug, args.display_name)
        except JupiterError as error:
            _fail(error.message)
            return
    finally:
        conn.close()
    print(render_member_joined(result.slug, result.display_name, result.api_key))


def cmd_list_members(args: argparse.Namespace) -> None:
    conn = sync_connection()
    try:
        try:
            org = get_org_by_slug(conn, args.slug)
            members = list_members(conn, org.id)
        except JupiterError as error:
            _fail(error.message)
            return
    finally:
        conn.close()

    if not members:
        print(f"No members in '{args.slug}' yet.")
        return

    header = f"{'display_name':<24} {'joined_at':<22} {'live':<6} last_seen"
    print(header)
    print("-" * len(header))
    for m in members:
        live = "yes" if m.active_sessions > 0 else "no"
        print(f"{m.display_name:<24} {m.joined_at or '':<22} {live:<6} {m.last_seen or ''}")


def cmd_semantic_status(args: argparse.Namespace) -> None:
    async def run() -> None:
        from jupiter_core.locks_repo import active_locks_for
        from jupiter_core.semantic import claims_for_analysis, get_semantic

        conn = sync_connection()
        try:
            org = get_org_by_slug(conn, args.slug)
        except JupiterError as error:
            _fail(error.message)
            return
        finally:
            conn.close()

        from jupiter_core.config import database_url

        aconn = await psycopg.AsyncConnection.connect(database_url())
        try:
            locks = await active_locks_for(aconn, org.id)
            result = await get_semantic(aconn, org.id, claims_for_analysis(locks))
        finally:
            await aconn.close()

        print(f"status:      {result.status}")
        print(f"model:       {result.model}")
        print(f"llm enabled: {result.llm.enabled}")
        if result.llm.reason:
            print(f"llm reason:  {result.llm.reason}")
        if result.error:
            print(f"error:       {result.error}")
        if result.overlaps:
            print("overlaps:")
            for o in result.overlaps:
                print(f"  - {' + '.join(o.paths)} ({', '.join(o.members)}, {o.confidence}) - {o.reason}")
        else:
            print("overlaps:    none")

    asyncio.run(run())


def cmd_whoami(args: argparse.Namespace) -> None:
    try:
        parsed = parse_key(args.key)
    except InvalidKey as error:
        _fail(f"invalid API key: {error}")
        return

    conn = sync_connection()
    try:
        pepper = key_pepper()
        if parsed.kind == "member":
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT m.id, m.org_id, m.display_name, m.api_key_hash, o.slug
                      FROM members m LEFT JOIN organizations o ON o.id = m.org_id
                     WHERE m.id = %s
                    """,
                    (parsed.record_id,),
                )
                row = cur.fetchone()
            ok = verify_key(args.key, row[3] if row else None, pepper)
            if not row or not ok:
                _fail("invalid API key")
                return
            print(f"kind:         member\nmember_id:    {row[0]}\norg_id:       {row[1]}\ndisplay_name: {row[2]}\nslug:         {row[4]}")
        else:
            with conn.cursor() as cur:
                cur.execute("SELECT id, slug, admin_key_hash FROM organizations WHERE id = %s", (parsed.record_id,))
                row = cur.fetchone()
            ok = verify_key(args.key, row[2] if row else None, pepper)
            if not row or not ok:
                _fail("invalid API key")
                return
            print(f"kind:  admin\norg_id: {row[0]}\nslug:  {row[1]}")
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m jupiter_admin")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("db-push", help="Apply the idempotent schema.").set_defaults(func=cmd_db_push)

    p = sub.add_parser("create-org", help="Create a team and mint its admin key.")
    p.add_argument("--name", required=True)
    p.add_argument("--slug", default=None)
    p.set_defaults(func=cmd_create_org)

    p = sub.add_parser("join", help="Join a team and mint a member key.")
    p.add_argument("--slug", required=True)
    p.add_argument("--display-name", required=True)
    p.set_defaults(func=cmd_join)

    p = sub.add_parser("list-members", help="List a team's members.")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_list_members)

    p = sub.add_parser("semantic-status", help="Run the semantic-overlap analysis for real.")
    p.add_argument("--slug", required=True)
    p.set_defaults(func=cmd_semantic_status)

    p = sub.add_parser("whoami", help="Resolve and print the Principal for an API key.")
    p.add_argument("--key", required=True)
    p.set_defaults(func=cmd_whoami)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
