"""Plain-text rendering for tool results.

Ported byte-for-byte from jupiter-code's lib/mcp/render.ts. Pure string
formatting, no I/O - every string here is what Claude actually reads.
"""

from __future__ import annotations

from .activity import ActivityOut
from .locks_repo import LockResponse, RelatedOut, describe_claim


def render_activity(activity: ActivityOut, own_session_id: int | None) -> str:
    lines: list[str] = []

    members = activity.active_members or []
    lines.append(f"Team: {activity.slug or '?'} - active teammates: {', '.join(members) or 'none'}")

    locks = activity.locks or []
    if len(locks) == 0:
        lines.append("No files are currently claimed by anyone.")
    else:
        lines.append("Files claimed right now:")
        for lock in locks:
            mine = " (you)" if lock.session_id == own_session_id else ""
            note = f" - {lock.note}" if lock.note else ""
            # describe_claim appends nothing for a whole-file claim, so this
            # line is byte-identical to the original unless a range was named.
            target = describe_claim(lock.file_path, lock.line_start, lock.line_end)
            lines.append(
                f"  - {target} | {lock.intent} | {lock.member}{mine}"
                f" | expires {lock.expires_at}{note}"
            )

    announcements = activity.announcements or []
    if len(announcements) > 0:
        lines.append("Recent announcements:")
        for item in announcements[-5:]:
            lines.append(f"  - {item.member}: {item.message} ({item.at})")

    if activity.lock_ttl_seconds:
        lines.append(f"Claims auto-expire {activity.lock_ttl_seconds}s after they were last refreshed.")

    return "\n".join(lines)


def render_checkin(session, activity: ActivityOut) -> str:
    header = (
        f"Checked in as '{session.display_name}' in org '{session.slug}' "
        f"(session {session.session_id}, dir {session.working_dir or 'unset'})."
    )
    return f"{header}\n{render_activity(activity, session.session_id)}"


def render_overlaps(overlaps: list[RelatedOut] | None) -> list[str]:
    """Model-suggested overlaps, for `jupiter_who_is_working`."""
    overlaps = overlaps or []
    if len(overlaps) == 0:
        return []

    lines = ["Possibly-related work on *different* files (advisory, AI-suggested):"]
    for item in overlaps:
        who = ", ".join(item.members or []) or "someone"
        paths = " + ".join(item.paths or [])
        lines.append(f"  - {paths} ({who}, {item.confidence or 'medium'} confidence) - {item.reason or ''}")
    return lines


def render_related_hint(related: list[RelatedOut] | None) -> str:
    """The trailing hint on a claim result. Empty when there is nothing to say."""
    if not related:
        return ""
    rows = "\n".join(
        f"  - {', '.join(r.members)} holds {' + '.join(r.paths)}"
        f" ({r.confidence} confidence) - {r.reason}"
        for r in related
    )
    return f"\nHeads-up, related work on other files (AI-suggested, advisory):\n{rows}"


def render_lock(result: LockResponse) -> str:
    hint = render_related_hint(result.related)

    if result.status != "blocked":
        return result.message + hint

    holders = "\n".join(
        f"  - {c.member} is {c.intent} it (since {c.locked_at}, expires {c.expires_at})"
        f"{f' - {c.note}' if c.note else ''}"
        for c in result.conflicts
    )

    return (
        f"{result.message}\n{holders}\n"
        "Your claim was still recorded. Prefer another file, or check with the user "
        f"before editing this one.{hint}"
    )
