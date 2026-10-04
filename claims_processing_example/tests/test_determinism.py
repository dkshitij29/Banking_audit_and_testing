"""Same inputs, same bytes: across processes and across hash seeds.

Python randomises set and dict-of-str iteration order per process unless
PYTHONHASHSEED is fixed, so an engine that iterated a set without sorting
would pass in-process tests and still drift between runs. This test runs the
golden cases in fresh processes with different hash seeds and compares bytes.
"""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SCRIPT = """
import sys
from engine import adjudicate
from tests.golden_cases import GOLDEN
for build in GOLDEN:
    case = build()
    for model in (case.policy, case.claim, adjudicate(case.policy, case.claim)):
        sys.stdout.write(model.model_dump_json() + "\\n")
"""


def run_with_hash_seed(seed: str) -> str:
    env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT], cwd=ROOT, env=env, capture_output=True, encoding="utf-8", check=True
    )
    return result.stdout


def test_output_is_byte_identical_across_processes_and_hash_seeds():
    outputs = {seed: run_with_hash_seed(seed) for seed in ("0", "1", "271828")}
    assert outputs["0"].count("\n") > 0
    assert len(set(outputs.values())) == 1
