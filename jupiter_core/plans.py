"""Plans, Moon Points, and the 30-day billing cycle.

Pure arithmetic only — no I/O, no database, no clock reads (callers pass
``now`` in). Everything here is unit-tested offline.

The model in one paragraph: an org holds a Moon Points balance. Redeeming
points buys a plan for one 30-day cycle. There is no scheduler: whenever
billing state is read or written, ``settle_billing`` (billing_repo) first
checks whether the current cycle has ended and, if so, charges the next
one from the balance — deducting when it covers the price, downgrading to
free when it does not. The lazy-sweep pattern from ``sweep.py``, applied
to money instead of claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .errors import payment_required, unprocessable

CYCLE_DAYS = 30

FREE_KEY = "free"
PRO_KEY = "pro"
ENTERPRISE_KEY = "enterprise"


@dataclass(frozen=True)
class Plan:
    key: str
    label: str
    price_points: int  # per 30-day cycle
    max_teams: int     # developer teams allowed


PLANS: dict[str, Plan] = {
    FREE_KEY: Plan(FREE_KEY, "Free", 0, 1),
    PRO_KEY: Plan(PRO_KEY, "Pro", 50, 6),
    ENTERPRISE_KEY: Plan(ENTERPRISE_KEY, "Enterprise", 300, 100),
}


def plan_for(key: str | None) -> Plan:
    """The plan for ``key``, or Free for anything unknown.

    Distrustful default: a key that is not in the catalog can only ever
    mean Free, never an error — a bad value in the database must never
    wedge every billing read.
    """
    if not isinstance(key, str):
        return PLANS[FREE_KEY]
    return PLANS.get(key.strip().lower()) or PLANS[FREE_KEY]


def renewal_due(plan_key: str | None, period_ends_at: datetime | None, now: datetime) -> bool:
    """Whether the org's cycle has ended and the next one must be settled.

    Free never renews (price 0, no period). A period is over at
    ``period_ends_at <= now`` — the same boundary the sweep uses for
    claims: a period *ends* at its end.
    """
    plan = plan_for(plan_key)
    if plan.key == FREE_KEY or plan.price_points <= 0:
        return False
    if period_ends_at is None:
        # A paid plan with no period is already-lapsed state (e.g. written
        # by hand); settle it rather than leaving it frozen.
        return True
    return period_ends_at <= now


def next_period_end(period_ends_at: datetime | None, now: datetime) -> datetime:
    """The end of the next cycle: ``max(period_ends_at, now) + 30d``.

    Extending from the later of the two means stacking an active period
    keeps the customer's remaining time, while a lapsed one restarts from
    settlement.
    """
    base = now if period_ends_at is None else max(period_ends_at, now)
    return base + timedelta(days=CYCLE_DAYS)


def apply_renewal(
    balance: int,
    plan_key: str | None,
    period_ends_at: datetime | None,
    now: datetime,
) -> tuple[str, int, datetime | None]:
    """Settle one cycle boundary.

    Returns ``(plan_key, balance, period_ends_at)`` after the settlement:
    the price is deducted and the period extended when the balance covers
    it, otherwise the org drops to Free with no period. Callers persist the
    result and append the matching ledger row (kind ``renewal``, or
    nothing on a downgrade — Free is the absence of a charge, not one).

    Exactly one cycle per call, never a catch-up charge for elapsed time:
    settlement itself is lazy, so a lapsed org simply restarts from now.
    """
    plan = plan_for(plan_key)
    if not renewal_due(plan.key, period_ends_at, now):
        return plan.key, balance, period_ends_at

    if balance >= plan.price_points:
        new_end = next_period_end(period_ends_at, now)
        return plan.key, balance - plan.price_points, new_end

    # Insufficient balance: downgrade. Over-cap teams are grandfathered by
    # the caller (rows stay; create_team refuses new ones).
    return FREE_KEY, balance, None


def redeem_result(
    balance: int,
    current_key: str | None,
    current_end: datetime | None,
    target_key: str,
    now: datetime,
) -> tuple[int, datetime]:
    """Buy ``target_key`` from the balance. Returns ``(new_balance, period_end)``.

    Redeeming stacks: the new period extends from ``max(current_end, now)``
    when the org already holds a live paid plan, so buying two cycles back
    to back yields sixty days. A lapsed or Free org starts from now.

    Redeeming the plan you already hold is allowed — it is how you extend
    a cycle early. Redeeming Free is not: Free is not something you buy.
    """
    target = plan_for(target_key)
    if target.key not in PLANS or target_key not in PLANS:
        raise unprocessable(
            f"unknown plan '{target_key}' (choose from: pro, enterprise)"
        )
    if target.key == FREE_KEY:
        raise unprocessable("the Free plan costs nothing — there is nothing to redeem")
    if balance < target.price_points:
        raise payment_required(
            f"not enough Moon Points: {target.label} costs {target.price_points}, balance is {balance}"
        )

    current = plan_for(current_key)
    live_period = current_end if (current.key != FREE_KEY and current_end is not None and current_end > now) else None
    new_end = next_period_end(live_period, now)
    return balance - target.price_points, new_end


def can_create_team(plan_key: str | None, existing_teams: int) -> bool:
    return existing_teams < plan_for(plan_key).max_teams


def plans_catalog() -> list[dict]:
    """The public pricing table, for GET /api/billing."""
    return [
        {
            "key": p.key,
            "label": p.label,
            "price_points": p.price_points,
            "max_teams": p.max_teams,
        }
        for p in PLANS.values()
    ]
