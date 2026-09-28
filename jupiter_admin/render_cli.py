"""Prints minted keys the way the old dashboard would have shown them once -
a one-time reveal, with a loud warning that they will not be shown again."""

from __future__ import annotations


def render_org_created(name: str, slug: str, admin_key: str) -> str:
    return (
        f"Organization created: {name} ({slug})\n"
        f"Admin API key (save this — shown once): {admin_key}"
    )


def render_member_joined(slug: str, display_name: str, member_key: str) -> str:
    return (
        f"Joined '{slug}' as '{display_name}'.\n"
        f"Member API key (save this — shown once): {member_key}"
    )
