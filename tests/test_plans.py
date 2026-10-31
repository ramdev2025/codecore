"""Plan arithmetic — pure functions, fully offline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jupiter_core.errors import JupiterError
from jupiter_core.plans import (
    CYCLE_DAYS,
    PLANS,
    apply_renewal,
    can_create_team,
    next_period_end,
    plans_catalog,
    plan_for,
    redeem_result,
    renewal_due,
)

NOW = datetime(2026, 10, 5, 12, 0, 0, tzinfo=timezone.utc)


def later(days: float) -> datetime:
    return NOW + timedelta(days=days)


# --------------------------------------------------------------------------
# The pricing table itself
# --------------------------------------------------------------------------


def test_the_three_plans_match_the_spec():
    assert PLANS["free"].price_points == 0
    assert PLANS["free"].max_teams == 1
    assert PLANS["pro"].price_points == 50
    assert PLANS["pro"].max_teams == 6
    assert PLANS["enterprise"].price_points == 300
    assert PLANS["enterprise"].max_teams == 100


def test_catalog_lists_every_plan():
    catalog = plans_catalog()
    assert [p["key"] for p in catalog] == ["free", "pro", "enterprise"]
    pro = next(p for p in catalog if p["key"] == "pro")
    assert pro == {"key": "pro", "label": "Pro", "price_points": 50, "max_teams": 6}


# --------------------------------------------------------------------------
# plan_for — the distrustful default
# --------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, "", "gold", "unlimited", 123])
def test_unknown_plan_falls_back_to_free(bad):
    assert plan_for(bad).key == "free"


def test_plan_keys_are_case_insensitive():
    assert plan_for("PRO").key == "pro"
    assert plan_for(" Enterprise ").key == "enterprise"


# --------------------------------------------------------------------------
# renewal_due — the cycle boundary
# --------------------------------------------------------------------------


def test_paid_plan_not_due_before_period_end():
    assert renewal_due("pro", later(10), NOW) is False


def test_paid_plan_due_exactly_at_period_end():
    # A period *ends* at its end — the same boundary the sweep uses.
    assert renewal_due("pro", NOW, NOW) is True


def test_paid_plan_due_after_period_end():
    assert renewal_due("enterprise", later(-1), NOW) is True


def test_free_plan_is_never_due():
    assert renewal_due("free", None, NOW) is False
    assert renewal_due("free", later(-90), NOW) is False


def test_paid_plan_without_a_period_is_due():
    # Hand-written state; settle it rather than leaving it frozen.
    assert renewal_due("pro", None, NOW) is True


# --------------------------------------------------------------------------
# next_period_end — stacking arithmetic
# --------------------------------------------------------------------------


def test_period_extends_from_now_when_lapsed():
    assert next_period_end(later(-5), NOW) == later(CYCLE_DAYS)


def test_period_extends_from_period_end_when_live():
    assert next_period_end(later(10), NOW) == later(10 + CYCLE_DAYS)


def test_period_from_none_extends_from_now():
    assert next_period_end(None, NOW) == later(CYCLE_DAYS)


# --------------------------------------------------------------------------
# apply_renewal — one cycle per settlement
# --------------------------------------------------------------------------


def test_renewal_deducts_and_extends():
    plan, balance, end = apply_renewal(80, "pro", NOW, NOW)
    assert plan == "pro"
    assert balance == 30
    assert end == later(CYCLE_DAYS)


def test_renewal_with_exact_balance_leaves_zero():
    plan, balance, end = apply_renewal(50, "pro", NOW, NOW)
    assert (plan, balance, end) == ("pro", 0, later(CYCLE_DAYS))


def test_renewal_insufficient_balance_downgrades():
    plan, balance, end = apply_renewal(49, "pro", NOW, NOW)
    assert (plan, balance, end) == ("free", 49, None)


def test_renewal_of_live_period_is_a_no_op():
    # Not due — nothing changes; the caller writes nothing.
    assert apply_renewal(300, "enterprise", later(5), NOW) == (
        "enterprise",
        300,
        later(5),
    )


def test_lapsed_renewal_charges_one_cycle_not_the_backlog():
    # 90 days lapsed: a single new cycle from now, never a 3x catch-up.
    plan, balance, end = apply_renewal(600, "enterprise", later(-90), NOW)
    assert plan == "enterprise"
    assert balance == 300
    assert end == later(CYCLE_DAYS)


# --------------------------------------------------------------------------
# redeem_result — buying (and stacking) a plan
# --------------------------------------------------------------------------


def test_redeem_from_free_starts_from_now():
    balance, end = redeem_result(100, "free", None, "pro", NOW)
    assert balance == 50
    assert end == later(CYCLE_DAYS)


def test_redeem_stacks_on_a_live_period():
    balance, end = redeem_result(100, "pro", later(10), "pro", NOW)
    assert balance == 50
    assert end == later(10 + CYCLE_DAYS)


def test_redeem_after_lapse_starts_from_now():
    balance, end = redeem_result(400, "enterprise", later(-1), "enterprise", NOW)
    assert balance == 100
    assert end == later(CYCLE_DAYS)


def test_redeem_upgrades_mid_cycle():
    # Pro bought 10 days ago, still live; enterprise extends the remaining
    # period — the customer keeps the 10 paid days.
    balance, end = redeem_result(400, "pro", later(20), "enterprise", NOW)
    assert balance == 100
    assert end == later(20 + CYCLE_DAYS)


def test_redeem_insufficient_balance_raises_402():
    with pytest.raises(JupiterError) as caught:
        redeem_result(49, "free", None, "pro", NOW)
    assert caught.value.status_code == 402


def test_redeem_unknown_plan_raises_422():
    with pytest.raises(JupiterError) as caught:
        redeem_result(9999, "free", None, "gold", NOW)
    assert caught.value.status_code == 422


def test_redeem_free_plan_raises_422():
    with pytest.raises(JupiterError) as caught:
        redeem_result(9999, "pro", later(5), "free", NOW)
    assert caught.value.status_code == 422


# --------------------------------------------------------------------------
# can_create_team — the caps
# --------------------------------------------------------------------------


def test_free_org_can_create_one_team():
    assert can_create_team("free", 0) is True
    assert can_create_team("free", 1) is False


def test_pro_org_caps_at_six_teams():
    assert can_create_team("pro", 5) is True
    assert can_create_team("pro", 6) is False


def test_enterprise_org_caps_at_one_hundred_teams():
    assert can_create_team("enterprise", 99) is True
    assert can_create_team("enterprise", 100) is False


def test_unknown_plan_gets_the_free_cap():
    assert can_create_team("gold", 1) is False
