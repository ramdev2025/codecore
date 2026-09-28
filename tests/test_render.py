from jupiter_core.activity import ActivityOut
from jupiter_core.announcements_repo import AnnouncementOut
from jupiter_core.locks_repo import LockOut, LockResponse, RelatedOut
from jupiter_core.render import render_activity, render_checkin, render_lock, render_overlaps, render_related_hint
from jupiter_core.sessions_repo import SessionOut


def _lock_out(file_path="a.py", intent="editing", member="alice", member_id=1, session_id=1,
              expires_at="2026-01-01T00:05:00Z", note=None, lock_id=1,
              line_start=None, line_end=None, has_snippet=False):
    return LockOut(
        lock_id=lock_id, file_path=file_path, intent=intent, member=member, member_id=member_id,
        session_id=session_id, working_dir=None, locked_at="2026-01-01T00:00:00Z",
        expires_at=expires_at, note=note, line_start=line_start, line_end=line_end,
        has_snippet=has_snippet,
    )


def test_render_activity_no_members_no_locks():
    activity = ActivityOut(slug="acme", now="2026-01-01T00:00:00Z", lock_ttl_seconds=300,
                            locks=[], active_members=[], announcements=[])
    result = render_activity(activity, own_session_id=None)
    assert result == (
        "Team: acme - active teammates: none\n"
        "No files are currently claimed by anyone.\n"
        "Claims auto-expire 300s after they were last refreshed."
    )


def test_render_activity_with_members_and_locks():
    activity = ActivityOut(
        slug="acme", now=None, lock_ttl_seconds=300,
        locks=[_lock_out(note="refactor")],
        active_members=["alice", "bob"],
        announcements=[],
    )
    result = render_activity(activity, own_session_id=1)
    assert result == (
        "Team: acme - active teammates: alice, bob\n"
        "Files claimed right now:\n"
        "  - a.py | editing | alice (you) | expires 2026-01-01T00:05:00Z - refactor\n"
        "Claims auto-expire 300s after they were last refreshed."
    )


def test_render_activity_lock_not_mine_no_note():
    activity = ActivityOut(slug="acme", now=None, lock_ttl_seconds=300,
                            locks=[_lock_out(session_id=2)], active_members=["alice"], announcements=[])
    result = render_activity(activity, own_session_id=1)
    assert "  - a.py | editing | alice | expires 2026-01-01T00:05:00Z\n" in result
    assert "(you)" not in result


def test_render_activity_announcements_last_five_only():
    announcements = [AnnouncementOut(member=f"m{i}", message=f"msg{i}", at=f"t{i}") for i in range(7)]
    activity = ActivityOut(slug="acme", now=None, lock_ttl_seconds=0, locks=[],
                            active_members=[], announcements=announcements)
    result = render_activity(activity, own_session_id=None)
    lines = result.split("\n")
    assert lines[0] == "Team: acme - active teammates: none"
    assert lines[1] == "No files are currently claimed by anyone."
    assert lines[2] == "Recent announcements:"
    ann_lines = lines[3:]
    assert len(ann_lines) == 5
    assert ann_lines[0] == "  - m2: msg2 (t2)"
    assert ann_lines[-1] == "  - m6: msg6 (t6)"
    # lock_ttl_seconds == 0 -> no trailing "auto-expire" line
    assert not any("auto-expire" in l for l in lines)


def test_render_checkin():
    session = SessionOut(session_id=5, member_id=1, display_name="alice", slug="acme",
                          working_dir="/repo", started_at="t", last_seen="t")
    activity = ActivityOut(slug="acme", now=None, lock_ttl_seconds=300, locks=[],
                            active_members=["alice"], announcements=[])
    result = render_checkin(session, activity)
    assert result == (
        "Checked in as 'alice' in org 'acme' (session 5, dir /repo).\n"
        "Team: acme - active teammates: alice\n"
        "No files are currently claimed by anyone.\n"
        "Claims auto-expire 300s after they were last refreshed."
    )


def test_render_checkin_unset_working_dir():
    session = SessionOut(session_id=5, member_id=1, display_name="alice", slug="acme",
                          working_dir=None, started_at="t", last_seen="t")
    activity = ActivityOut(slug="acme", now=None, lock_ttl_seconds=0, locks=[],
                            active_members=[], announcements=[])
    result = render_checkin(session, activity)
    assert result.startswith("Checked in as 'alice' in org 'acme' (session 5, dir unset).")


def test_render_overlaps_empty():
    assert render_overlaps([]) == []
    assert render_overlaps(None) == []


def test_render_overlaps_formats_line():
    overlaps = [RelatedOut(paths=["a.py", "b.py"], members=["alice", "bob"], reason="impl/test", confidence="high")]
    lines = render_overlaps(overlaps)
    assert lines == [
        "Possibly-related work on *different* files (advisory, AI-suggested):",
        "  - a.py + b.py (alice, bob, high confidence) - impl/test",
    ]


def test_render_related_hint_empty():
    assert render_related_hint([]) == ""
    assert render_related_hint(None) == ""


def test_render_related_hint_formats():
    related = [RelatedOut(paths=["c.py"], members=["carol"], reason="caller/callee", confidence="medium")]
    result = render_related_hint(related)
    assert result == (
        "\nHeads-up, related work on other files (AI-suggested, advisory):\n"
        "  - carol holds c.py (medium confidence) - caller/callee"
    )


def test_render_lock_clear_no_hint():
    result = LockResponse(status="clear", file_path="a.py", intent="editing",
                           expires_at="t", conflicts=[], message="clear - you hold a.py (editing) until t",
                           related=[])
    assert render_lock(result) == "clear - you hold a.py (editing) until t"


def test_render_lock_clear_with_hint():
    related = [RelatedOut(paths=["b.py"], members=["bob"], reason="related", confidence="low")]
    result = LockResponse(status="clear", file_path="a.py", intent="editing",
                           expires_at="t", conflicts=[], message="clear - you hold a.py (editing) until t",
                           related=related)
    rendered = render_lock(result)
    assert rendered == (
        "clear - you hold a.py (editing) until t\n"
        "Heads-up, related work on other files (AI-suggested, advisory):\n"
        "  - bob holds b.py (low confidence) - related"
    )


def test_render_lock_blocked():
    conflict = _lock_out(member="bob", note="fixing bug")
    result = LockResponse(
        status="blocked", file_path="a.py", intent="editing", expires_at="t",
        conflicts=[conflict],
        message="⚠ blocked by bob (editing) on a.py - coordinate before editing, or pick another file",
        related=[],
    )
    rendered = render_lock(result)
    assert rendered == (
        "⚠ blocked by bob (editing) on a.py - coordinate before editing, or pick another file\n"
        "  - bob is editing it (since 2026-01-01T00:00:00Z, expires 2026-01-01T00:05:00Z) - fixing bug\n"
        "Your claim was still recorded. Prefer another file, or check with the user "
        "before editing this one."
    )


def test_render_lock_blocked_with_hint_and_no_note():
    conflict = _lock_out(member="bob", note=None)
    related = [RelatedOut(paths=["c.py"], members=["carol"], reason="related", confidence="high")]
    result = LockResponse(
        status="blocked", file_path="a.py", intent="editing", expires_at="t",
        conflicts=[conflict],
        message="⚠ blocked by bob (editing) on a.py - coordinate before editing, or pick another file",
        related=related,
    )
    rendered = render_lock(result)
    assert rendered == (
        "⚠ blocked by bob (editing) on a.py - coordinate before editing, or pick another file\n"
        "  - bob is editing it (since 2026-01-01T00:00:00Z, expires 2026-01-01T00:05:00Z)\n"
        "Your claim was still recorded. Prefer another file, or check with the user "
        "before editing this one.\n"
        "Heads-up, related work on other files (AI-suggested, advisory):\n"
        "  - carol holds c.py (high confidence) - related"
    )
