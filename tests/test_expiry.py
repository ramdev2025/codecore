import pytest

from jupiter_core.time_util import (
    DEFAULT_LOCK_TTL,
    MIN_LOCK_TTL,
    MIN_SESSION_TTL,
    lock_ttl_from,
    session_ttl_from,
)


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, DEFAULT_LOCK_TTL),
        ("", DEFAULT_LOCK_TTL),
        ("300", 300),
        ("+300", 300),
        (300, 300),
        ("3", MIN_LOCK_TTL),  # floored at MIN_LOCK_TTL
        ("0", MIN_LOCK_TTL),
        ("-10", MIN_LOCK_TTL),
        ("300.5", DEFAULT_LOCK_TTL),  # not int() parseable -> default
        ("1e3", DEFAULT_LOCK_TTL),
        ("not a number", DEFAULT_LOCK_TTL),
        ("  300  ", 300),  # stripped before matching
        ("300 ", 300),
    ],
)
def test_lock_ttl_from(raw, expected):
    assert lock_ttl_from(raw) == expected


def test_session_ttl_from_doubles_lock_ttl():
    assert session_ttl_from(400) == 800


def test_session_ttl_from_floors_at_min():
    assert session_ttl_from(5) == MIN_SESSION_TTL
    assert session_ttl_from(1) == MIN_SESSION_TTL
