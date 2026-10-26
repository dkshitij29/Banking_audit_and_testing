"""Prepare a fresh source checkout for a one-issue Qwen pilot."""

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from datasets import load_dataset


root = Path(__file__).resolve().parent
instance_id = (root / "instance-id.txt").read_text().strip()
dataset_name = "SWE-bench/SWE-bench_Verified"
dataset = load_dataset(dataset_name, split="test")
task = next(row for row in dataset if row["instance_id"] == instance_id)
run_name = datetime.now(timezone.utc).strftime("qwen-%Y%m%d-%H%M%S-%f")
run_dir = root / "agent-runs" / instance_id / run_name
workspace = run_dir / "workspace"
artifacts = run_dir / "artifacts"
artifacts.mkdir(parents=True)

subprocess.run(
    ["git", "clone", f"https://github.com/{task['repo']}.git", str(workspace)],
    check=True,
)
subprocess.run(
    ["git", "checkout", "--detach", task["base_commit"]],
    cwd=workspace,
    check=True,
)

prompt = (
    "Fix the issue below in this repository. Inspect the relevant code, make "
    "the smallest appropriate fix, and run relevant tests if dependencies "
    "are available. Report any test-environment limitations accurately. "
    "Do not commit changes, modify tests to hide failures, look up the upstream "
    "solution, or read files outside this workspace. Do not inspect benchmark "
    "datasets or evaluation artifacts.\n\n"
    + task["problem_statement"]
)
(artifacts / "task-prompt.txt").write_text(prompt + "\n")
(artifacts / "metadata.json").write_text(
    json.dumps(
        {
            "dataset": dataset_name,
            "instance_id": instance_id,
            "repo": task["repo"],
            "base_commit": task["base_commit"],
            "workspace": str(workspace),
            "model": "Qwen3.6-27B",
            "environment": "host checkout pilot; not the benchmark container",
        },
        indent=2,
    )
    + "\n"
)
(root / "current-agent-run.txt").write_text(str(run_dir) + "\n")
print(f"Prepared: {instance_id}")
print(f"Workspace: {workspace}")
print(f"Prompt: {artifacts / 'task-prompt.txt'}")
