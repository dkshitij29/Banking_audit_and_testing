"""Resumable Qwen host-checkout generation and Docker SWE-bench evaluation."""

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parent
DATASET = "SWE-bench/SWE-bench_Verified"


def save(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def execute(command, cwd, log, timeout, env=None):
    started = time.monotonic()
    with log.open("w") as output:
        process = subprocess.Popen(command, cwd=cwd, env=env, stdout=output,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code = process.wait(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt) as error:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            if isinstance(error, KeyboardInterrupt):
                raise
            code = 124
    return code, round(time.monotonic() - started, 2)


def git(workspace, *args):
    return subprocess.check_output(["git", *args], cwd=workspace, text=True)


def read_agent_result(path):
    # CLI warnings on stderr can precede the JSON in a combined log.
    text = path.read_text()
    decoder = json.JSONDecoder()
    for offset, character in enumerate(text):
        if character not in "[{":
            continue
        try:
            value, _ = decoder.raw_decode(text[offset:])
        except ValueError:
            continue
        if isinstance(value, dict) and value.get("type") == "result":
            return value
        if isinstance(value, list):
            result = next((e for e in reversed(value)
                           if isinstance(e, dict) and e.get("type") == "result"), None)
            if result is not None:
                return result
    raise ValueError("No final result in agent log")


def summarize(batch, manifest):
    rows = []
    for task in manifest["tasks"]:
        path = batch / task["instance_id"] / "state.json"
        row = json.loads(path.read_text()) if path.exists() else {
            "instance_id": task["instance_id"], "status": "pending"}
        rows.append(row)
    fields = ["instance_id", "status", "agent_exit", "agent_seconds",
              "evaluation_seconds", "changed_tests", "input_tokens", "output_tokens"]
    with (batch / "summary.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    counts = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    predictions = []
    for task in manifest["tasks"]:
        prediction = batch / task["instance_id"] / "prediction.jsonl"
        if prediction.exists():
            predictions.append(prediction.read_text().strip())
    (batch / "predictions.jsonl").write_text("\n".join(predictions) + ("\n" if predictions else ""))
    metrics = {
        "selected": len(rows), "resolved": counts.get("resolved", 0),
        "resolved_percent": round(100 * counts.get("resolved", 0) / len(rows), 2),
        "status_counts": counts,
        "agent_seconds": round(sum(r.get("agent_seconds", 0) for r in rows), 2),
        "evaluation_seconds": round(sum(r.get("evaluation_seconds", 0) for r in rows), 2),
        "input_tokens_reported": sum(r.get("input_tokens", 0) for r in rows),
        "output_tokens_reported": sum(r.get("output_tokens", 0) for r in rows),
        "usage_available_for": sum("input_tokens" in r for r in rows),
        "agent_timeouts": sum(r.get("agent_exit") == 124 for r in rows),
        "agent_nonzero_exits": sum(r.get("agent_exit", 0) != 0 for r in rows),
        "issues_with_test_changes": sum(bool(r.get("changed_tests")) for r in rows),
        "environment": "host checkout generation; Docker official evaluation",
        "notes": "Subset result, not full Verified score. Reported usage may include harness auxiliary calls.",
    }
    save(batch / "metrics.json", metrics)
    lines = [f"{'ISSUE':<40} RESULT"]
    lines += [f"{r['instance_id']:<40} {r['status']}" for r in rows]
    lines += [f"\nResolved: {metrics['resolved']}/{len(rows)} ({metrics['resolved_percent']}%)",
              f"Reports: {batch}"]
    report = "\n".join(lines) + "\n"
    (batch / "summary.txt").write_text(report)
    print(report, flush=True)


def run_task(batch, task, config):
    iid = task["instance_id"]
    folder = batch / iid
    folder.mkdir(exist_ok=True)
    state_path = folder / "state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {
        "instance_id": iid, "status": "pending"}
    if state["status"] not in ("pending", "running", "patch_ready"):
        print(f"Skipping saved result: {iid} ({state['status']})", flush=True)
        return
    workspace = folder / "workspace"
    if not (folder / "prediction.jsonl").exists():
        # A partial attempt is retained rather than silently treated as a fresh attempt.
        if state["status"] == "running":
            state["status"] = "interrupted"
            save(state_path, state)
            return
        state["status"] = "running"
        save(state_path, state)
        code, _ = execute(["git", "clone", f"https://github.com/{task['repo']}.git", str(workspace)],
                          folder, folder / "clone.log", 900)
        if code:
            raise RuntimeError(f"Repository clone failed: {code}")
        subprocess.run(["git", "checkout", "--detach", task["base_commit"]],
                       cwd=workspace, check=True, capture_output=True)
        prompt = (
            "Fix the issue below. Inspect code and make the smallest appropriate fix. "
            "Do not commit, modify or delete existing tests, fetch upstream fixes, or read "
            "outside this workspace or benchmark data. Run relevant tests if possible. "
            "You are in a host checkout, not a prepared benchmark container. If compiled "
            "extensions or dependencies are missing, report that limitation; do not spend "
            "the attempt rebuilding the whole project or installing into global environments. "
            "Finish with a concise explanation and test results.\n\n" + task["problem_statement"])
        (folder / "prompt.txt").write_text(prompt)
        env = os.environ.copy()
        env.pop("VIRTUAL_ENV", None)
        env.pop("PYTHONPATH", None)
        # A per-issue environment avoids writes to the evaluator's Python environment.
        subprocess.run(["uv", "venv", "--python", "3.11", str(workspace / ".venv")],
                       check=True, capture_output=True)
        env["VIRTUAL_ENV"] = str(workspace / ".venv")
        env["PATH"] = str(workspace / ".venv/bin") + os.pathsep + env["PATH"]
        state["agent_exit"], state["agent_seconds"] = execute(
            ["node", config["cli"], "--model", config["model"],
             "--approval-mode", "yolo", "--output-format", "json", "-p", prompt],
            workspace, folder / "agent-output.json", config["agent_minutes"] * 60, env)
        save(state_path, state)
        try:
            result = read_agent_result(folder / "agent-output.json")
            (folder / "agent-final.txt").write_text(str(result.get("result", "")))
            usage = result.get("usage", {})
            for key in ("input_tokens", "output_tokens"):
                if isinstance(usage.get(key), (int, float)):
                    state[key] = usage[key]
        except (ValueError, TypeError, StopIteration, AttributeError):
            pass
        subprocess.run(["git", "add", "-N", "--", "."], cwd=workspace,
                       check=True, capture_output=True)
        changed = git(workspace, "diff", "--name-only", task["base_commit"], "--").splitlines()
        state["changed_tests"] = any(
            "tests" in Path(p).parts or Path(p).name.startswith("test_") for p in changed)
        patch = git(workspace, "diff", "--binary", task["base_commit"], "--")
        (folder / "model.patch").write_text(patch)
        prediction = {"instance_id": iid, "model_name_or_path": config["model_label"],
                      "model_patch": patch}
        (folder / "prediction.jsonl").write_text(json.dumps(prediction) + "\n")
        state["status"] = "patch_ready"
        save(state_path, state)

    prediction = json.loads((folder / "prediction.jsonl").read_text())
    if not prediction["model_patch"].strip():
        state["status"] = "empty_patch"
        save(state_path, state)
        return
    # The same identifier safely resumes an unchanged saved prediction.
    digest = hashlib.sha256(prediction["model_patch"].encode()).hexdigest()[:10]
    batch_key = batch.name
    if batch.name in ("trial-2", "trial-3"):
        batch_key += "-" + hashlib.sha256(str(batch.resolve()).encode()).hexdigest()[:10]
    run_id = f"{batch_key}-{iid}-{digest}"
    state["evaluation_run_id"] = run_id
    code, elapsed = execute(
        [sys.executable, "-m", "swebench.harness.run_evaluation",
         "--dataset_name", DATASET, "--instance_ids", iid,
         "--predictions_path", str(folder / "prediction.jsonl"), "--max_workers", "1",
         "--timeout", str(config["test_seconds"]), "--run_id", run_id],
        ROOT, folder / "evaluation.log", config["evaluation_minutes"] * 60)
    state["evaluation_seconds"] = elapsed
    state["evaluation_exit"] = code
    report_path = ROOT / "logs/evaluation" / run_id / "results.json"
    state["status"] = "evaluation_timeout" if code == 124 else "evaluation_error"
    if report_path.exists():
        report = json.loads(report_path.read_text())
        save(folder / "evaluation-report.json", report)
        for key, label in [("resolved_ids", "resolved"), ("infra_failure_ids", "infrastructure_failure"),
                           ("ambiguous_failure_ids", "ambiguous_failure"), ("error_ids", "evaluation_error"),
                           ("unresolved_ids", "unresolved"), ("empty_patch_ids", "empty_patch")]:
            if iid in report.get(key, []):
                state["status"] = label
                break
    save(state_path, state)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--ids-file", type=Path, help="One instance ID per line; overrides random selection")
    parser.add_argument("--resume", type=Path, help="Existing batch directory")
    parser.add_argument("--report-only", type=Path, help="Print an existing batch's metrics")
    parser.add_argument("--agent-minutes", type=int, default=20)
    parser.add_argument("--evaluation-minutes", type=int, default=30)
    parser.add_argument("--test-seconds", type=int, default=900)
    parser.add_argument("--cli", default="/home/mahesh/DAT/qwen-code-release/scripts/cli-entry.js")
    parser.add_argument("--model", default="Qwen3.6-27B")
    args = parser.parse_args()
    if args.report_only:
        batch = args.report_only.resolve()
        summarize(batch, json.loads((batch / "manifest.json").read_text()))
        return
    if min(args.count, args.agent_minutes, args.evaluation_minutes, args.test_seconds) <= 0:
        parser.error("Counts and time limits must be positive")
    if args.resume:
        batch = args.resume.resolve()
        manifest = json.loads((batch / "manifest.json").read_text())
    else:
        from datasets import load_dataset
        dataset = load_dataset(DATASET, split="test")
        tasks = sorted(dataset, key=lambda task: task["instance_id"])
        if args.ids_file:
            ids = args.ids_file.read_text().split()
            by_id = {t["instance_id"]: t for t in tasks}
            if not ids or len(ids) != len(set(ids)) or any(i not in by_id for i in ids):
                parser.error("IDs must be nonempty, unique, and present in Verified")
            tasks = [by_id[i] for i in ids]
        else:
            tasks = random.Random(args.seed).sample(tasks, args.count)
        batch = ROOT / "batches" / datetime.now(timezone.utc).strftime("verified-%Y%m%d-%H%M%S-%f")
        batch.mkdir(parents=True)
        config = {"cli": str(Path(args.cli).resolve()), "model": args.model,
                  "model_label": f"qwen-code-{args.model}", "agent_minutes": args.agent_minutes,
                  "evaluation_minutes": args.evaluation_minutes, "test_seconds": args.test_seconds}
        manifest = {"dataset": DATASET, "dataset_fingerprint": getattr(dataset, "_fingerprint", None),
                    "seed": args.seed, "config": config,
                    "tasks": [{k: t[k] for k in ("instance_id", "repo", "base_commit", "problem_statement")} for t in tasks]}
        save(batch / "manifest.json", manifest)
        (batch / "versions.txt").write_text(
            subprocess.check_output(["node", config["cli"], "--version"], text=True)
            + subprocess.check_output(["git", "-C", str(Path(config["cli"]).parent.parent), "rev-parse", "HEAD"], text=True))
    config = manifest["config"]
    subprocess.run(["docker", "ps"], check=True, capture_output=True)
    with urllib.request.urlopen("http://127.0.0.1:9000/v1/models", timeout=20) as response:
        models = json.load(response)
    if config["model"] not in [m["id"] for m in models["data"]]:
        raise RuntimeError("Configured model is missing from server")
    print(f"Batch: {batch}\nAutomatic tool approval; host workspaces are not sandboxes.", flush=True)
    try:
        for index, task in enumerate(manifest["tasks"], 1):
            print(f"[{index}/{len(manifest['tasks'])}] {task['instance_id']}", flush=True)
            try:
                run_task(batch, task, config)
            except Exception as error:
                folder = batch / task["instance_id"]
                folder.mkdir(exist_ok=True)
                state_path = folder / "state.json"
                state = json.loads(state_path.read_text()) if state_path.exists() else {"instance_id": task["instance_id"]}
                state.update(status="runner_error", error=str(error))
                save(state_path, state)
                print(f"Runner error: {error}", flush=True)
            summarize(batch, manifest)
    finally:
        summarize(batch, manifest)


if __name__ == "__main__":
    main()
