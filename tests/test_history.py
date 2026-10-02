"""Claim history: the state a closed claim reports, and how it serialises.

Nothing in Jupiter deletes a claim - expiry is an UPDATE stamping
`released_at` - so every claim ever taken is still in `file_locks`. These
cover the part that is *not* stored: whether a closed claim lapsed on its own
or was released deliberately, which is inferred from how long it had gone
unrefreshed when it closed.
"""

from datetime import datetime, timedelta, timezone

import pytest

from jupiter_core.locks_repo import (
    ACTIVE_LOCKS_SQL,
    HISTORY_LOCKS_SQL,
    ActiveLock,
    _to_active_lock,
    claim_state,
    history_out,
    lock_out,
)

TTL = 300
T0 = datetime(2026, 9, 29, 14, 30, 0, tzinfo=timezone.utc)


def _lock(refreshed_delta=0, released_delta=None, **kw):
    refreshed = T0 + timedelta(seconds=refreshed_delta)
    return ActiveLock(
        id=kw.get("id", 1),
        file_path=kw.get("file_path", "index.html"),
        intent=kw.get("intent", "editing"),
        session_id=1,
        member_id=kw.get("member_id", 7),
        member=kw.get("member", "alice"),
        working_dir=None,
        locked_at=T0,
        refreshed_at=refreshed,
        note=kw.get("note"),
        line_start=kw.get("line_start"),
        line_end=kw.get("line_end"),
        released_at=None if released_delta is None else T0 + timedelta(seconds=released_delta),
    )


# --------------------------------------------------------------------------
# claim_state
# --------------------------------------------------------------------------


def test_unreleased_claim_is_active():
    assert claim_state(None, T0, TTL) == "active"


def test_released_after_a_full_ttl_reads_as_expired():
    """What the sweep does: it only closes claims already past their TTL."""
    assert claim_state(T0 + timedelta(seconds=TTL), T0, TTL) == "expired"


def test_released_well_after_the_ttl_reads_as_expired():
    assert claim_state(T0 + timedelta(seconds=TTL * 4), T0, TTL) == "expired"


def test_released_inside_the_ttl_reads_as_released():
    """An explicit jupiter_unlock_file lands before the sweep could have."""
    assert claim_state(T0 + timedelta(seconds=TTL - 1), T0, TTL) == "released"


def test_released_immediately_reads_as_released():
    assert claim_state(T0, T0, TTL) == "released"


def test_the_boundary_belongs_to_expired():
    """Exactly TTL is the sweep's own cutoff, so it is not a manual release."""
    assert claim_state(T0 + timedelta(seconds=TTL), T0, TTL) == "expired"
    assert claim_state(T0 + timedelta(seconds=TTL - 0.001), T0, TTL) == "released"


def test_a_missing_refreshed_at_cannot_be_called_expired():
    """With nothing to measure against, claiming it lapsed would be a guess."""
    assert claim_state(T0, None, TTL) == "released"


def test_state_tracks_the_configured_ttl_not_the_default():
    at_60 = T0 + timedelta(seconds=60)
    assert claim_state(at_60, T0, 30) == "expired"
    assert claim_state(at_60, T0, 300) == "released"


# --------------------------------------------------------------------------
# history_out
# --------------------------------------------------------------------------


def test_history_out_carries_the_release_timestamp():
    out = history_out(_lock(released_delta=TTL), TTL)
    assert out.released_at == "2026-09-29T14:35:00Z"
    assert out.state == "expired"


def test_history_out_leaves_released_at_null_while_live():
    out = history_out(_lock(), TTL)
    assert out.released_at is None
    assert out.state == "active"


def test_history_out_still_reports_expires_at():
    """A closed claim keeps the expiry it had, so the UI can say when it was due."""
    assert history_out(_lock(released_delta=TTL), TTL).expires_at == "2026-09-29T14:35:00Z"


def test_history_out_preserves_the_line_range():
    out = history_out(_lock(released_delta=10, line_start=40, line_end=80), TTL)
    assert (out.line_start, out.line_end) == (40, 80)


def test_history_out_agrees_with_lock_out_on_every_shared_field():
    """HistoryLockOut is a superset of LockOut - the overlap must not drift."""
    lock = _lock(released_delta=10, note="fixing the nav", line_start=1, line_end=50)
    live, past = lock_out(lock, TTL), history_out(lock, TTL)
    for field in vars(live):
        assert getattr(past, field) == getattr(live, field), field


# --------------------------------------------------------------------------
# The queries themselves
# --------------------------------------------------------------------------


def test_history_sql_does_not_filter_out_closed_claims():
    """The whole point: `/api/activity` has this clause and history must not."""
    assert "released_at IS NULL" in ACTIVE_LOCKS_SQL
    assert "released_at IS NULL" not in HISTORY_LOCKS_SQL


def test_history_sql_selects_released_at_last():
    """_to_active_lock reads released_at positionally, at index 13.

    Split on the outer FROM, not the first one - the has_snippet column is an
    EXISTS subquery with a FROM of its own.
    """
    columns = HISTORY_LOCKS_SQL.split("FROM file_locks")[0]
    assert columns.rstrip().rstrip(",").endswith("l.released_at")


def test_history_sql_selects_the_active_columns_in_the_same_order():
    """Both queries feed _to_active_lock, so the shared prefix must match."""
    active = ACTIVE_LOCKS_SQL.split("FROM file_locks")[0].split(",\n")
    history = HISTORY_LOCKS_SQL.split("FROM file_locks")[0].split(",\n")
    assert len(history) == len(active) + 1
    assert [c.strip() for c in history[:-1]] == [c.strip() for c in active]


def test_history_sql_is_newest_first_and_bounded():
    assert "ORDER BY l.locked_at DESC, l.id DESC" in HISTORY_LOCKS_SQL
    assert "LIMIT %s" in HISTORY_LOCKS_SQL


@pytest.mark.parametrize("released", [None, T0])
def test_row_mapping_round_trips_released_at(released):
    row = (1, "index.html", "editing", 1, T0, T0, None, 7, None, "alice", None, None, False, released)
    assert _to_active_lock(row).released_at == released


def test_row_mapping_defaults_released_at_when_absent():
    """An ACTIVE_LOCKS_SQL row is one column shorter and must still map."""
    row = (1, "index.html", "editing", 1, T0, T0, None, 7, None, "alice", None, None, False)
    assert _to_active_lock(row).released_at is None
