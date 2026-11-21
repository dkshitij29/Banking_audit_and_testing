"""Run the original 30 cases, three fresh trials, using Qwen3.8-27B."""

import argparse
import fcntl
import json
from pathlib import Path
import subprocess
import sys
import re

import run_verified_batch as runner


def prepare(name="qwen38-same30"):
    baseline = runner.ROOT / "batches/verified-20261025-200909-712162"
    extra = runner.ROOT / (
        "extensions/verified-20261025-200909-712162-plus-10-seed-43/"
        "extra-verified-20261025-200909-712162-10-43")
    manifests = [json.loads((p / "manifest.json").read_text()) for p in (baseline, extra)]
    tasks = [task for manifest in manifests for task in manifest["tasks"]]
    ids = [task["instance_id"] for task in tasks]
    if len(tasks) != 30 or len(set(ids)) != 30:
        raise RuntimeError("Expected exactly 30 unique original issues")
    config = dict(manifests[0]["config"])
    if config != manifests[1]["config"]:
        raise RuntimeError("Original batches have different settings")
    config.update(model="Qwen3.8-27B", model_label="qwen-code-0.25.3-Qwen3.8-27B-FP8")
    manifest = {
        "dataset": manifests[0]["dataset"], "seed": None,
        "selection": "Exact original 20 plus additional 10, with original base commits and prompts",
        "source_batches": [str(baseline), str(extra)], "config": config, "tasks": tasks,
    }
    if not re.fullmatch(r"[A-Za-z0-9_-]+", name):
        raise ValueError("Run name must contain only letters, numbers, underscores or hyphens")
    batch = runner.ROOT / "batches" / name
    batch.mkdir(parents=True, exist_ok=True)
    path = batch / "manifest.json"
    if path.exists():
        if json.loads(path.read_text()) != manifest:
            raise RuntimeError("Existing experiment manifest differs; refusing to overwrite")
    else:
        cli = config["cli"]
        version = subprocess.check_output(["node", cli, "--version"], text=True).strip()
        commit = subprocess.check_output(
            ["git", "-C", str(Path(cli).parent.parent), "rev-parse", "HEAD"], text=True).strip()
        original_versions = (baseline / "versions.txt").read_text().splitlines()
        if [version, commit] != original_versions[:2]:
            raise RuntimeError("Agent version or commit differs from original experiment")
        runner.save(path, manifest)
        (batch / "versions.txt").write_text(version + "\n" + commit + "\n")
        (batch / "issue-ids.txt").write_text("\n".join(ids) + "\n")
    return batch


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--name", default="qwen38-same30", help="Separate experiment folder; reuse to resume")
    parser.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    batch = prepare(args.name)
    lock = (batch / "experiment.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("This experiment is already running.")
    repeated = runner.ROOT / "repeated-trials" / batch.name
    print(f"Trial 1: {batch}\nCombined three-trial reports: {repeated}", flush=True)
    if args.prepare_only:
        return
    command = [sys.executable, str(runner.ROOT / "run_three_trials.py"), "--baseline", str(batch)]
    if args.report_only:
        subprocess.run(command + ["--report-only"], check=True)
        return
    config = json.loads((batch / "manifest.json").read_text())["config"]
    smoke = batch / "preflight-workspace"
    smoke.mkdir(exist_ok=True)
    log = batch / "preflight.log"
    print("Checking the exact headless CLI and selected model before starting issues...", flush=True)
    code, _ = runner.execute(
        ["node", config["cli"], "--model", config["model"], "--output-format", "json",
         "-p", "Reply only with: connection working. Do not use tools or modify files."],
        smoke, log, 90)
    try:
        result = runner.read_agent_result(log)
    except ValueError:
        raise SystemExit(f"Preflight produced no valid result. Inspect {log}")
    if code or result.get("is_error") or "connection working" not in str(result.get("result", "")).lower():
        raise SystemExit(f"Preflight failed; no issue attempts started. Inspect {log}")
    print("Headless connection preflight passed.", flush=True)
    if args.preflight_only:
        return
    print("Running 90 new attempts; no previous model patches are reused.", flush=True)
    subprocess.run([sys.executable, str(runner.ROOT / "run_verified_batch.py"),
                    "--resume", str(batch)], check=True)
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
