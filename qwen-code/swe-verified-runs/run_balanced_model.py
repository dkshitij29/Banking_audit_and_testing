"""Copy a fixed sample into a separate model experiment; preflight and run 3 trials."""

import argparse
import fcntl
import json
from pathlib import Path
import re
import subprocess
import sys
import urllib.request

import run_verified_batch as runner


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=runner.ROOT / "batches/verified-balanced30")
    parser.add_argument("--model", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]+", args.name):
        parser.error("Use letters, numbers, underscores or hyphens for --name")
    source = args.source.resolve()
    original = json.loads((source / "manifest.json").read_text())
    manifest = dict(original)
    manifest["config"] = dict(original["config"])
    manifest["config"].update(model=args.model, model_label=f"qwen-code-{args.model}")
    manifest["sample_source"] = str(source)
    batch = runner.ROOT / "batches" / args.name
    if source == batch:
        raise SystemExit("Choose a new experiment name; do not overwrite the source sample")
    batch.mkdir(parents=True, exist_ok=True)
    lock = (batch / "experiment.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("Experiment already running")
    path = batch / "manifest.json"
    if path.exists() and json.loads(path.read_text()) != manifest:
        raise SystemExit("Existing experiment has different settings; choose another name")
    cli = manifest["config"]["cli"]
    if not path.exists():
        versions = subprocess.check_output(["node", cli, "--version"], text=True)
        versions += subprocess.check_output(["git", "-C", str(Path(cli).parent.parent), "rev-parse", "HEAD"], text=True)
        runner.save(path, manifest)
        (batch / "versions.txt").write_text(versions)
        for name in ("sample.csv", "issue-ids.txt"):
            if (source / name).exists():
                (batch / name).write_bytes((source / name).read_bytes())
    repeated = runner.ROOT / "repeated-trials" / batch.name
    three = [sys.executable, str(runner.ROOT / "run_three_trials.py"), "--baseline", str(batch)]
    print(f"Sample: {source}\nTrial 1: {batch}\nThree-trial reports: {repeated}", flush=True)
    if args.report_only:
        subprocess.run(three + ["--report-only"], check=True)
        return
    with urllib.request.urlopen("http://127.0.0.1:9000/v1/models", timeout=20) as response:
        models = json.load(response)
    model = next((m for m in models["data"] if m["id"] == args.model), None)
    if model is None:
        raise SystemExit(f"Server does not provide {args.model}")
    runner.save(batch / "server-model.json", model)
    smoke = batch / "preflight-workspace"
    smoke.mkdir(exist_ok=True)
    log = batch / "preflight.log"
    code, _ = runner.execute(
        ["node", cli, "--model", args.model, "--output-format", "json", "-p",
         "Reply only with: connection working. Do not use tools or change files."], smoke, log, 120)
    try:
        result = runner.read_agent_result(log)
    except ValueError:
        raise SystemExit(f"No valid preflight response; inspect {log}")
    if code or result.get("is_error") or "connection working" not in str(result.get("result", "")).lower():
        raise SystemExit(f"Preflight failed; no issues started. Inspect {log}")
    print(f"Headless preflight passed. Server context limit: {model.get('max_model_len')}", flush=True)
    if args.preflight_only:
        return
    subprocess.run([sys.executable, str(runner.ROOT / "run_verified_batch.py"), "--resume", str(batch)], check=True)
    subprocess.run(three, check=True)


if __name__ == "__main__":
    main()
