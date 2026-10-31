"""The org wallet: Moon Points, plan state, and the lazy renewal.

All money is a ledger row. The balance is always ``SUM(delta)`` -
``balance_after`` is a display convenience written in the same
transaction, never an authority.

``settle_billing`` is the billing twin of ``sweep.py``: there is no
scheduler anywhere in Jupiter, so a cycle boundary is settled inside
whatever read or write touched billing state. Call it before any billing
read or write (the one deliberate exception: the capture path credits
first, then settles, so a top-up arriving just after a lapse still funds
the renewal).
"""

from __future__ import annotations

from dataclasses import dataclass

import psycopg

from .auth import Principal
from .errors import not_found, unprocessable
from .plans import plan_for, plans_catalog, redeem_result, renewal_due, apply_renewal
from .time_util import isoformat, now as utcnow

_BALANCE_SQL = """
    SELECT COALESCE(SUM(delta), 0) FROM points_ledger WHERE org_id = %s
"""

_ORG_LOCK_SQL = """
    SELECT plan, plan_period_ends_at FROM organizations WHERE id = %s FOR UPDATE
"""


# --------------------------------------------------------------------------
# Reads
# --------------------------------------------------------------------------


async def org_balance(aconn, org_id: int) -> int:
    async with aconn.cursor() as cur:
        await cur.execute(_BALANCE_SQL, (org_id,))
        row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_teams(aconn, org_id: int) -> int:
    async with aconn.cursor() as cur:
        await cur.execute("SELECT COUNT(*) FROM teams WHERE org_id = %s", (org_id,))
        row = await cur.fetchone()
    return int(row[0]) if row else 0


# --------------------------------------------------------------------------
# The lazy renewal
# --------------------------------------------------------------------------


async def _settle_locked(cur, org_id: int, plan_key: str, period_ends_at, now) -> tuple[str, object]:
    """Settle a lapsed cycle on a cursor already holding the org-row lock.

    Returns the new ``(plan_key, period_ends_at)`` — unchanged when not
    due. Writes the renewal ledger row on a successful charge; a
    downgrade writes nothing (Free is the absence of a charge, not one).
    """
    if not renewal_due(plan_key, period_ends_at, now):
        return plan_key, period_ends_at

    await cur.execute(_BALANCE_SQL, (org_id,))
    row = await cur.fetchone()
    balance = int(row[0]) if row else 0

    new_plan, new_balance, new_end = apply_renewal(balance, plan_key, period_ends_at, now)

    if new_plan != "free":
        await cur.execute(
            "UPDATE organizations SET plan = %s, plan_period_ends_at = %s WHERE id = %s",
            (new_plan, new_end, org_id),
        )
        await _append_ledger(
            cur, org_id, -plan_for(new_plan).price_points, new_balance, "renewal",
            f"automatic renewal of {plan_for(new_plan).label}",
        )
    else:
        # Insufficient balance: downgrade. Over-cap teams are grandfathered.
        await cur.execute(
            "UPDATE organizations SET plan = 'free', plan_period_ends_at = NULL WHERE id = %s",
            (org_id,),
        )
    return new_plan, new_end


async def _append_ledger(cur, org_id: int, delta: int, balance_after: int, kind: str,
                         note: str | None = None, paypal_order_id: str | None = None) -> None:
    await cur.execute(
        """
        INSERT INTO points_ledger (org_id, delta, balance_after, kind, note, paypal_order_id)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (org_id, delta, balance_after, kind, note, paypal_order_id),
    )


async def settle_billing(aconn, org_id: int, now=None) -> None:
    """Settle a lapsed billing cycle, inside the caller's transaction.

    The ``FOR UPDATE`` on the org row is the serialization point for every
    billing mutation (captures, redeems, settlements), so two concurrent
    writers cannot double-charge or double-credit. Idempotent: nothing to
    do when the plan is Free or the period has not ended.
    """
    now = now or utcnow()

    async with aconn.cursor() as cur:
        await cur.execute(_ORG_LOCK_SQL, (org_id,))
        row = await cur.fetchone()
        if row is None:
            raise not_found("org no longer exists")
        await _settle_locked(cur, org_id, row[0], row[1], now)


# --------------------------------------------------------------------------
# The overview payload
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PayPalStatus:
    enabled: bool
    client_id: str | None
    env: str | None
    reason: str | None


@dataclass(frozen=True)
class BillingOut:
    balance: int
    plan: str
    plan_label: str
    price_points: int
    max_teams: int
    period_ends_at: str | None
    teams_count: int
    plans: list
    paypal: PayPalStatus


def _paypal_status() -> PayPalStatus:
    from .paypal import describe_paypal

    return describe_paypal()


async def billing_overview(aconn, org_id: int) -> BillingOut:
    """Settle first, then read — the dashboard never shows a stale plan."""
    await settle_billing(aconn, org_id)

    async with aconn.cursor() as cur:
        await cur.execute(
            "SELECT plan, plan_period_ends_at FROM organizations WHERE id = %s",
            (org_id,),
        )
        row = await cur.fetchone()
        if row is None:
            raise not_found("org no longer exists")

    plan = plan_for(row[0])
    return BillingOut(
        balance=await org_balance(aconn, org_id),
        plan=plan.key,
        plan_label=plan.label,
        price_points=plan.price_points,
        max_teams=plan.max_teams,
        period_ends_at=isoformat(row[1]),
        teams_count=await count_teams(aconn, org_id),
        plans=plans_catalog(),
        paypal=_paypal_status(),
    )


# --------------------------------------------------------------------------
# Writes
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TopupOut:
    points_added: int
    balance: int
    paypal_order_id: str


async def record_topup(aconn, org_id: int, paypal_order_id: str, amount_usd: int) -> TopupOut:
    """Credit a captured PayPal order, exactly once.

    The claim gate is the ``UPDATE ... WHERE status = 'created'`` on the
    order row: exactly one transaction wins it, so a double-clicked or
    retried capture is a clean ``points_added = 0``, never a second
    credit and never a unique-index 500. (The partial unique index on
    ``points_ledger.paypal_order_id`` stays as the backstop.)
    """
    async with aconn.cursor() as cur:
        await cur.execute(
            """
            UPDATE billing_orders
               SET status = 'captured', captured_at = %s
             WHERE paypal_order_id = %s AND org_id = %s AND status = 'created'
            RETURNING id
            """,
            (utcnow(), paypal_order_id, org_id),
        )
        claimed = await cur.fetchone()
        if claimed is None:
            # Already captured (or never ours): idempotent replay.
            return TopupOut(points_added=0, balance=await org_balance(aconn, org_id),
                            paypal_order_id=paypal_order_id)

        await cur.execute(_BALANCE_SQL, (org_id,))
        row = await cur.fetchone()
        balance = int(row[0]) if row else 0

        await _append_ledger(cur, org_id, amount_usd, balance + amount_usd, "topup",
                             "PayPal order captured", paypal_order_id)

    return TopupOut(points_added=amount_usd, balance=balance + amount_usd,
                    paypal_order_id=paypal_order_id)


async def record_order_created(aconn, org_id: int, paypal_order_id: str, amount_usd: int) -> None:
    """Persist a PayPal order we just created, for capture-side verification."""
    async with aconn.cursor() as cur:
        await cur.execute(
            """
            INSERT INTO billing_orders (org_id, paypal_order_id, amount_usd)
            VALUES (%s, %s, %s)
            ON CONFLICT (paypal_order_id) DO NOTHING
            """,
            (org_id, paypal_order_id, amount_usd),
        )


async def order_amount(aconn, org_id: int, paypal_order_id: str) -> int | None:
    """The amount WE asked PayPal for, or None if we never created this order.

    Capture verifies against this row, never against what the client
    claims. An order belonging to another org reads as absent — same
    reasoning as a foreign session's 404.
    """
    async with aconn.cursor() as cur:
        await cur.execute(
            "SELECT amount_usd FROM billing_orders WHERE paypal_order_id = %s AND org_id = %s",
            (paypal_order_id, org_id),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else None


async def redeem_plan(aconn, principal: Principal, raw_plan_key: str) -> BillingOut:
    """Redeem points for one plan cycle, atomically.

    Lock, settle any lapsed cycle, apply the redeem (which stacks from
    ``max(current_end, now)`` when the plan is live), then read back the
    overview. 402 when the balance is short; 422 for an unknown plan.
    """
    target = plan_for(raw_plan_key)
    if raw_plan_key not in ("pro", "enterprise"):
        raise unprocessable(f"unknown plan '{raw_plan_key}' (choose from: pro, enterprise)")

    now = utcnow()
    async with aconn.transaction():
        async with aconn.cursor() as cur:
            await cur.execute(_ORG_LOCK_SQL, (principal.org_id,))
            row = await cur.fetchone()
            if row is None:
                raise not_found("org no longer exists")

            current_plan, current_end = await _settle_locked(cur, principal.org_id, row[0], row[1], now)

            await cur.execute(_BALANCE_SQL, (principal.org_id,))
            balance_row = await cur.fetchone()
            balance = int(balance_row[0]) if balance_row else 0

            # Raises 402 on insufficient balance, which aborts the
            # transaction — including the settlement above. A renewal
            # charge only sticks when the redeem that triggered it does.
            new_balance, new_end = redeem_result(balance, current_plan, current_end, target.key, now)

            await cur.execute(
                "UPDATE organizations SET plan = %s, plan_period_ends_at = %s WHERE id = %s",
                (target.key, new_end, principal.org_id),
            )
            await _append_ledger(cur, principal.org_id, -target.price_points, new_balance, "redeem",
                                 f"redeemed {target.label}")

    return await billing_overview(aconn, principal.org_id)


def grant_points_sync(conn: psycopg.Connection, org_id: int, points: int, note: str | None) -> int:
    """Sync twin, for jupiter_admin's grant-points. Returns the new balance.

    Manual credits need no PayPal — the dev/test path for balances.
    """
    if points == 0:
        raise unprocessable("points must not be zero")
    if abs(points) > 10_000_000:
        raise unprocessable("points must be at most ±10,000,000")

    with conn.cursor() as cur:
        cur.execute("SELECT 1 FROM organizations WHERE id = %s", (org_id,))
        if cur.fetchone() is None:
            raise not_found("org no longer exists")
        cur.execute(_BALANCE_SQL, (org_id,))
        row = cur.fetchone()
        balance = int(row[0]) if row else 0
        if balance + points < 0:
            raise unprocessable(f"grant would take the balance below zero (balance is {balance})")
        cur.execute(
            """
            INSERT INTO points_ledger (org_id, delta, balance_after, kind, note)
            VALUES (%s, %s, %s, 'grant', %s)
            """,
            (org_id, points, balance + points, note),
        )
    conn.commit()
    return balance + points
