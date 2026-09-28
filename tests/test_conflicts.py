from jupiter_core.locks_repo import ActiveLock, conflicts_for


def _lock(id, file_path, member_id, intent, member="m", session_id=1):
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
    )


def test_no_conflict_when_no_other_claims():
    active = [_lock(1, "a.py", member_id=1, intent="editing")]
    assert conflicts_for(active, "a.py", member_id=1, intent="editing") == []


def test_conflict_different_member_both_editing():
    active = [_lock(1, "a.py", member_id=2, intent="editing")]
    result = conflicts_for(active, "a.py", member_id=1, intent="editing")
    assert len(result) == 1
    assert result[0].member_id == 2


def test_no_conflict_two_readers():
    active = [_lock(1, "a.py", member_id=2, intent="reading")]
    assert conflicts_for(active, "a.py", member_id=1, intent="reading") == []


def test_conflict_reader_vs_editor():
    active = [_lock(1, "a.py", member_id=2, intent="editing")]
    assert len(conflicts_for(active, "a.py", member_id=1, intent="reading")) == 1

    active2 = [_lock(1, "a.py", member_id=2, intent="reading")]
    assert len(conflicts_for(active2, "a.py", member_id=1, intent="editing")) == 1


def test_no_self_conflict_same_member_different_session():
    """Your own second Claude Code instance never blocks your first."""
    active = [_lock(1, "a.py", member_id=1, intent="editing", session_id=99)]
    assert conflicts_for(active, "a.py", member_id=1, intent="editing") == []


def test_no_conflict_different_path():
    active = [_lock(1, "b.py", member_id=2, intent="editing")]
    assert conflicts_for(active, "a.py", member_id=1, intent="editing") == []


def test_multiple_conflicts_returned():
    active = [
        _lock(1, "a.py", member_id=2, intent="editing"),
        _lock(2, "a.py", member_id=3, intent="editing"),
        _lock(3, "a.py", member_id=1, intent="editing"),  # self, excluded
        _lock(4, "b.py", member_id=4, intent="editing"),  # different path
    ]
    result = conflicts_for(active, "a.py", member_id=1, intent="editing")
    assert {c.member_id for c in result} == {2, 3}
