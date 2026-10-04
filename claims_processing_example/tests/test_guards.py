"""Static guards on the engine source: purity, and no product numbers in rule logic."""

import ast
from pathlib import Path

import pytest

from engine import clauses as C

ENGINE = Path(__file__).resolve().parent.parent / "engine"
RULES = ENGINE / "rules.py"


def parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def imported_modules(tree: ast.Module) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add(node.module or "")
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_rules_never_import_the_placeholder_tables():
    assert not {name for name in imported_modules(parse(RULES)) if "tables" in name.split(".")}


def test_rules_hold_no_product_numbers():
    """Only 0, 1 and 2 may appear as numbers in rule logic (comparisons, 1 - ratio, a half).
    Every product number must come from policy.terms."""
    numbers = {
        node.value
        for node in ast.walk(parse(RULES))
        if isinstance(node, ast.Constant) and isinstance(node.value, int | float) and not isinstance(node.value, bool)
    }
    assert numbers <= {0, 1, 2}


def test_rules_cite_clauses_only_through_the_registry():
    literals = [
        node.value
        for node in ast.walk(parse(RULES))
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and C.CLAUSE_ID_PATTERN.match(node.value)
    ]
    assert literals == []


ALLOWED_IMPORTS = {
    "__future__", "calendar", "collections", "collections.abc", "dataclasses", "datetime", "decimal",
    "enum", "fractions", "itertools", "math", "re", "typing", "pydantic",
}


@pytest.mark.parametrize("module", sorted(ENGINE.glob("*.py")), ids=lambda path: path.name)
def test_engine_is_pure(module):
    """No I/O, network, clock or randomness: only these imports, and no clock reads."""
    tree = parse(module)
    outside = {
        name for name in imported_modules(tree)
        if name.split(".")[0] not in {"engine"} and name.split(".")[0] not in ALLOWED_IMPORTS
    }
    assert not outside
    clock_reads = {
        node.attr for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"now", "today", "utcnow", "time_ns", "perf_counter"}
    }
    assert not clock_reads
