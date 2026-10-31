"""Postgres access: pool for the async call sites, a sync helper for the CLI,
and the idempotent schema.

Ported from jupiter-code's lib/db.ts and db/schema.sql.
"""

from __future__ import annotations

import psycopg
from psycopg_pool import AsyncConnectionPool

from .config import database_url

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS organizations (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name            varchar(120) NOT NULL,
    slug            varchar(120) NOT NULL UNIQUE,
    admin_key_hash  varchar(255) NOT NULL,
    created_at      timestamptz  NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS members (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id        bigint       NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    display_name  varchar(120) NOT NULL,
    api_key_hash  varchar(255) NOT NULL,
    joined_at     timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT uq_member_name_per_org UNIQUE (org_id, display_name)
);

CREATE INDEX IF NOT EXISTS ix_members_org_id ON members (org_id);

CREATE TABLE IF NOT EXISTS sessions (
    id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    member_id    bigint      NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    org_id       bigint      NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    working_dir  text,
    started_at   timestamptz NOT NULL DEFAULT now(),
    last_seen    timestamptz NOT NULL DEFAULT now(),
    ended_at     timestamptz
);

CREATE INDEX IF NOT EXISTS ix_sessions_member_id ON sessions (member_id);
CREATE INDEX IF NOT EXISTS ix_sessions_org_id ON sessions (org_id);

CREATE TABLE IF NOT EXISTS file_locks (
    id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    session_id    bigint      NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
    org_id        bigint      NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    file_path     text        NOT NULL,
    intent        varchar(16) NOT NULL DEFAULT 'editing',
    locked_at     timestamptz NOT NULL DEFAULT now(),
    refreshed_at  timestamptz NOT NULL DEFAULT now(),
    released_at   timestamptz,
    note          text,
    CONSTRAINT ck_file_locks_intent CHECK (intent IN ('editing', 'reading'))
);

CREATE INDEX IF NOT EXISTS ix_file_locks_session_id ON file_locks (session_id);
CREATE INDEX IF NOT EXISTS ix_file_locks_org_id ON file_locks (org_id);
CREATE INDEX IF NOT EXISTS ix_file_locks_org_path ON file_locks (org_id, file_path);

CREATE TABLE IF NOT EXISTS announcements (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      bigint      NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    member_id   bigint      NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    message     text        NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_announcements_org_id ON announcements (org_id);

CREATE TABLE IF NOT EXISTS semantic_cache (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id       bigint      NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    fingerprint  varchar(32) NOT NULL,
    status       varchar(16) NOT NULL,
    findings     jsonb       NOT NULL DEFAULT '[]'::jsonb,
    model        varchar(120),
    error        text,
    started_at   timestamptz NOT NULL DEFAULT now(),
    analyzed_at  timestamptz,
    CONSTRAINT uq_semantic_cache UNIQUE (org_id, fingerprint),
    CONSTRAINT ck_semantic_status CHECK (status IN ('pending', 'ready', 'error'))
);

CREATE INDEX IF NOT EXISTS ix_semantic_cache_org ON semantic_cache (org_id);

-- Claimed line ranges. NULL/NULL means a whole-file claim, which is what every
-- claim was before this existed - so old rows keep their original meaning and
-- old clients (which send no range) keep working unchanged.
ALTER TABLE file_locks ADD COLUMN IF NOT EXISTS line_start integer;
ALTER TABLE file_locks ADD COLUMN IF NOT EXISTS line_end   integer;

-- ADD CONSTRAINT has no IF NOT EXISTS, so swallow the duplicate on re-push.
DO $$ BEGIN
    ALTER TABLE file_locks ADD CONSTRAINT ck_file_locks_lines CHECK (
        (line_start IS NULL AND line_end IS NULL)
        OR (line_start >= 1 AND line_end >= line_start)
    );
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Opt-in only: written when JUPITER_STORE_SNIPPETS is on. Held in its own
-- table so the code never rides along in the bulk activity payload, and so a
-- deployment that never enables it carries no code at all. Never sent to the
-- LLM - the semantic analyser only ever sees paths, intents, holders, notes.
CREATE TABLE IF NOT EXISTS claim_snippets (
    id           bigint      GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    lock_id      bigint      NOT NULL REFERENCES file_locks (id) ON DELETE CASCADE,
    org_id       bigint      NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    code         text        NOT NULL,
    captured_at  timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_claim_snippets_lock ON claim_snippets (lock_id);
CREATE INDEX IF NOT EXISTS ix_claim_snippets_org ON claim_snippets (org_id);

-- ============================================================================
-- Billing: Moon Points, PayPal orders, and developer teams.
-- The wallet and plan live on the org - both are org-wide.
-- ============================================================================

ALTER TABLE organizations ADD COLUMN IF NOT EXISTS plan varchar(16) NOT NULL DEFAULT 'free';
ALTER TABLE organizations ADD COLUMN IF NOT EXISTS plan_period_ends_at timestamptz;

-- ADD CONSTRAINT has no IF NOT EXISTS (the ck_file_locks_lines precedent).
DO $$ BEGIN
    ALTER TABLE organizations ADD CONSTRAINT ck_org_plan
        CHECK (plan IN ('free', 'pro', 'enterprise'));
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- Append-only: the balance is always derived (SUM(delta)), never stored
-- separately, so it cannot disagree with the rows. balance_after is a
-- display convenience written in the same transaction as its delta.
CREATE TABLE IF NOT EXISTS points_ledger (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          bigint      NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    delta           integer     NOT NULL,
    balance_after   integer     NOT NULL,
    kind            varchar(16) NOT NULL,
    note            text,
    paypal_order_id varchar(64),
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT ck_ledger_delta CHECK (delta <> 0),
    CONSTRAINT ck_ledger_kind  CHECK (kind IN ('topup', 'grant', 'redeem', 'renewal'))
);

CREATE INDEX IF NOT EXISTS ix_ledger_org ON points_ledger (org_id);

-- One ledger row per PayPal order: capture idempotency. A replayed
-- capture hits the unique index and credits nothing the second time.
CREATE UNIQUE INDEX IF NOT EXISTS ux_ledger_paypal
    ON points_ledger (paypal_order_id) WHERE paypal_order_id IS NOT NULL;

-- Every PayPal order we create, so capture can verify the amount against
-- what WE asked PayPal for - never what the client claims it paid.
CREATE TABLE IF NOT EXISTS billing_orders (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          bigint       NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    paypal_order_id varchar(64)  NOT NULL UNIQUE,
    amount_usd      integer      NOT NULL,
    status          varchar(16)  NOT NULL DEFAULT 'created',
    created_at      timestamptz  NOT NULL DEFAULT now(),
    captured_at     timestamptz,
    CONSTRAINT ck_order_status CHECK (status IN ('created', 'captured', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_billing_orders_org ON billing_orders (org_id);

-- Developer teams: a sub-grouping of members inside an org, capped by the
-- org's plan. Over-cap teams after a downgrade are grandfathered - the
-- rows stay, but no new ones can be created.
CREATE TABLE IF NOT EXISTS teams (
    id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id     bigint       NOT NULL REFERENCES organizations (id) ON DELETE CASCADE,
    name       varchar(120) NOT NULL,
    created_at timestamptz  NOT NULL DEFAULT now(),
    CONSTRAINT uq_team_name_per_org UNIQUE (org_id, name)
);

CREATE INDEX IF NOT EXISTS ix_teams_org ON teams (org_id);

CREATE TABLE IF NOT EXISTS team_members (
    team_id   bigint      NOT NULL REFERENCES teams (id) ON DELETE CASCADE,
    member_id bigint      NOT NULL REFERENCES members (id) ON DELETE CASCADE,
    added_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, member_id)
);
"""

_pool: AsyncConnectionPool | None = None


async def _configure(aconn: psycopg.AsyncConnection) -> None:
    # Autocommit: single-statement repo calls need no explicit commit, and
    # multi-statement ones wrap themselves in `async with aconn.transaction():`.
    await aconn.set_autocommit(True)


async def get_pool() -> AsyncConnectionPool:
    """The process-wide async connection pool, created lazily on first use."""
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(conninfo=database_url(), open=False, configure=_configure)
        await _pool.open()
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def sync_connection() -> psycopg.Connection:
    """A plain synchronous connection, for jupiter_admin (no event loop)."""
    return psycopg.connect(database_url())


def apply_schema(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
