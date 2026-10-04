"""Locks the order of the amount steps.

Three locks:
1. The module docstring of engine/rules.py lists the approved order.
2. AMOUNT_ORDER, which drives execution, matches the docstring.
3. Golden cases break if two steps are swapped, proving the order is observable.
"""

import re

import pytest

from engine import adjudicate, rules
from tests.golden_cases import (
    g04_room_above_cap_then_copay,
    g05_copay_then_sum_insured,
    g26_sublimit_then_deductible_then_copay,
)

APPROVED_ORDER = (
    "pre_post_window",
    "line_exclusions",
    "room_rent",
    "icu",
    "disease_sublimit",
    "ayush_cap",
    "deductible",
    "copay",
    "sum_insured",
)


def docstring_order() -> list[tuple[str, bool]]:
    """(step name, implemented?) for each step in the docstring's "Amount order:" block."""
    lines = rules.__doc__.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "Amount order:")
    steps = []
    for line in lines[start + 1 :]:
        if not line.strip():
            break
        match = re.match(r"^\s+\d+\.\s+([a-z_]+)\s", line)
        if match:
            steps.append((match.group(1), "[not yet implemented]" not in line))
    return steps


def test_docstring_lists_the_approved_order():
    assert tuple(name for name, _ in docstring_order()) == APPROVED_ORDER


def test_amount_order_runs_the_implemented_steps_in_docstring_order():
    assert rules.AMOUNT_ORDER == tuple(name for name, implemented in docstring_order() if implemented)


def test_every_step_in_the_order_has_an_implementation():
    assert set(rules.AMOUNT_ORDER) == set(rules._AMOUNT_STEPS)


@pytest.mark.parametrize(
    "build, swap, payable_if_swapped",
    [
        (g04_room_above_cap_then_copay, ("room_rent", "copay"), 60_000),
        (g05_copay_then_sum_insured, ("copay", "sum_insured"), 450_000),
        (g26_sublimit_then_deductible_then_copay, ("disease_sublimit", "deductible"), 40_500),
        (g26_sublimit_then_deductible_then_copay, ("deductible", "copay"), 30_500),
    ],
)
def test_golden_cases_notice_a_swap(monkeypatch, build, swap, payable_if_swapped):
    case = build()
    order = list(rules.AMOUNT_ORDER)
    i, j = order.index(swap[0]), order.index(swap[1])
    order[i], order[j] = order[j], order[i]
    monkeypatch.setattr(rules, "AMOUNT_ORDER", tuple(order))

    swapped = adjudicate(case.policy, case.claim).payable
    assert swapped == payable_if_swapped
    assert swapped != case.expected.payable
