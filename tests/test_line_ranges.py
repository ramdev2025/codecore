"""Claimed line ranges: validation, the overlap rule, and rendering.

The load-bearing property here is that a claim with no range behaves exactly
as claims did before ranges existed - it covers the whole file, so it
conflicts with everything on that path and renders byte-identically.
"""

import pytest

from jupiter_core.config import SNIPPET_MAX_LENGTH
from jupiter_core.errors import JupiterError
from jupiter_core.locks_repo import (
    ActiveLock,
    blocked_message,
    clear_message,
    conflicts_for,
    describe_claim,
    describe_range,
    normalize_lines,
    ranges_overlap,
    resolve_snippet,
)


def _lock(id, file_path, member_id, intent, line_start=None, line_end=None, member="m", session_id=1):
    return ActiveLock(
        id=id,
        file_path=file_path,
        intent=intent,
        session_id=session_id,
        member_id=member_id,
        member=member,
        working_dir=None,
        locked_at=None,
        refreshed_at=None,
        note=None,
        line_start=line_start,
        line_end=line_end,
    )


# --------------------------------------------------------------------------
# normalize_lines
# --------------------------------------------------------------------------


def test_both_absent_is_whole_file():
    assert normalize_lines(None, None) == (None, None)


def test_start_alone_claims_one_line():
    assert normalize_lines(40, None) == (40, 40)


def test_range_is_kept():
    assert normalize_lines(40, 80) == (40, 80)


def test_numeric_strings_are_accepted():
    assert normalize_lines("40", "80") == (40, 80)


def test_end_without_start_is_rejected():
    with pytest.raises(JupiterError) as caught:
        normalize_lines(None, 80)
    assert caught.value.status_code == 422


@pytest.mark.parametrize("start,end", [(0, 10), (-1, 10), (1, 0)])
def test_out_of_range_is_rejected(start, end):
    with pytest.raises(JupiterError) as caught:
        normalize_lines(start, end)
    assert caught.value.status_code == 422


def test_end_before_start_is_rejected():
    with pytest.raises(JupiterError) as caught:
        normalize_lines(80, 40)
    assert caught.value.status_code == 422


def test_non_numeric_is_rejected():
    with pytest.raises(JupiterError) as caught:
        normalize_lines("forty", None)
    assert caught.value.status_code == 422


def test_booleans_are_not_lines():
    # bool is an int subclass in Python; True must not slip through as line 1.
    with pytest.raises(JupiterError):
        normalize_lines(True, None)


# --------------------------------------------------------------------------
# ranges_overlap
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a,b,expected",
    [
        ((10, 20), (15, 25), True),    # partial overlap
        ((10, 20), (20, 30), True),    # touching at one line
        ((10, 20), (21, 30), False),   # adjacent but disjoint
        ((10, 20), (1, 5), False),     # entirely before
        ((10, 20), (12, 15), True),    # contained
        ((10, 20), (10, 20), True),    # identical
    ],
)
def test_range_pairs(a, b, expected):
    assert ranges_overlap(a[0], a[1], b[0], b[1]) is expected


def test_whole_file_overlaps_any_range():
    assert ranges_overlap(None, None, 40, 80) is True
    assert ranges_overlap(40, 80, None, None) is True
    assert ranges_overlap(None, None, None, None) is True


# --------------------------------------------------------------------------
# conflicts_for with ranges
# --------------------------------------------------------------------------


def test_overlapping_ranges_conflict():
    active = [_lock(1, "a.py", member_id=2, intent="editing", line_start=60, line_end=120)]
    result = conflicts_for(active, "a.py", member_id=1, intent="editing", line_start=40, line_end=80)
    assert len(result) == 1


def test_disjoint_ranges_do_not_conflict():
    active = [_lock(1, "a.py", member_id=2, intent="editing", line_start=200, line_end=240)]
    assert conflicts_for(active, "a.py", member_id=1, intent="editing", line_start=40, line_end=80) == []


def test_whole_file_claim_conflicts_with_a_range():
    active = [_lock(1, "a.py", member_id=2, intent="editing")]
    result = conflicts_for(active, "a.py", member_id=1, intent="editing", line_start=40, line_end=80)
    assert len(result) == 1


def test_range_claim_conflicts_with_a_whole_file_holder():
    active = [_lock(1, "a.py", member_id=2, intent="editing", line_start=40, line_end=80)]
    result = conflicts_for(active, "a.py", member_id=1, intent="editing")
    assert len(result) == 1


def test_two_readers_never_conflict_even_when_overlapping():
    active = [_lock(1, "a.py", member_id=2, intent="reading", line_start=40, line_end=80)]
    assert conflicts_for(active, "a.py", member_id=1, intent="reading", line_start=50, line_end=60) == []


def test_same_member_never_conflicts_even_when_overlapping():
    active = [_lock(1, "a.py", member_id=1, intent="editing", line_start=40, line_end=80)]
    assert conflicts_for(active, "a.py", member_id=1, intent="editing", line_start=50, line_end=60) == []


def test_different_files_never_conflict():
    active = [_lock(1, "b.py", member_id=2, intent="editing", line_start=40, line_end=80)]
    assert conflicts_for(active, "a.py", member_id=1, intent="editing", line_start=40, line_end=80) == []


# --------------------------------------------------------------------------
# Rendering - whole-file output must not change
# --------------------------------------------------------------------------


def test_describe_range_shapes():
    assert describe_range(None, None) == ""
    assert describe_range(40, 40) == ":40"
    assert describe_range(40, None) == ":40"
    assert describe_range(40, 80) == ":40-80"


def test_describe_claim():
    assert describe_claim("a.py", None, None) == "a.py"
    assert describe_claim("a.py", 40, 80) == "a.py:40-80"


def test_clear_message_without_range_is_unchanged():
    assert clear_message("a.py", "editing", "2026-01-01T00:05:00Z") == (
        "clear - you hold a.py (editing) until 2026-01-01T00:05:00Z"
    )


def test_clear_message_with_range():
    assert clear_message("a.py", "editing", "2026-01-01T00:05:00Z", 40, 80) == (
        "clear - you hold a.py:40-80 (editing) until 2026-01-01T00:05:00Z"
    )


def test_blocked_message_without_ranges_is_unchanged():
    conflicts = [_lock(1, "a.py", member_id=2, intent="editing", member="bob")]
    assert blocked_message(conflicts, "a.py") == (
        "⚠ blocked by bob (editing) on a.py - coordinate before editing, or pick another file"
    )


def test_blocked_message_names_the_overlapping_lines():
    conflicts = [
        _lock(1, "a.py", member_id=2, intent="editing", member="bob", line_start=60, line_end=120)
    ]
    assert blocked_message(conflicts, "a.py", 40, 80) == (
        "⚠ blocked by bob (editing:60-120) on a.py:40-80"
        " - coordinate before editing, or pick another file"
    )


# --------------------------------------------------------------------------
# Snippets are opt-in
# --------------------------------------------------------------------------


def test_snippet_dropped_when_storage_disabled(monkeypatch):
    monkeypatch.delenv("JUPITER_STORE_SNIPPETS", raising=False)
    assert resolve_snippet("def f(): pass") is None


def test_snippet_kept_when_storage_enabled(monkeypatch):
    monkeypatch.setenv("JUPITER_STORE_SNIPPETS", "true")
    assert resolve_snippet("def f(): pass") == "def f(): pass"


def test_snippet_is_capped(monkeypatch):
    monkeypatch.setenv("JUPITER_STORE_SNIPPETS", "1")
    assert len(resolve_snippet("x" * (SNIPPET_MAX_LENGTH + 500))) == SNIPPET_MAX_LENGTH


def test_absent_snippet_stays_absent(monkeypatch):
    monkeypatch.setenv("JUPITER_STORE_SNIPPETS", "on")
    assert resolve_snippet(None) is None
