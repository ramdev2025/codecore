"""Shared fixtures.

`db_conn` is for tests that need a real Postgres (the sweep SQL uses
`interval`, `ON CONFLICT ... WHERE`, and correlated `EXISTS` against `now()`
that SQLite doesn't support the same way). Those tests are skipped, not
failed, when `JUPITER_TEST_DATABASE_URL` is unset.
"""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def db_conn():
    url = os.environ.get("JUPITER_TEST_DATABASE_URL")
    if not url:
        pytest.skip("JUPITER_TEST_DATABASE_URL not set")

    import psycopg

    from jupiter_core.db import SCHEMA_SQL

    conn = psycopg.connect(url)
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    try:
        yield conn
    finally:
        conn.close()
