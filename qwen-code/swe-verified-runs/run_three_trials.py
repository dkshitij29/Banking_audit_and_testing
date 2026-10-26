"""Reuse one batch, run two fresh trials, and report empirical three-trial metrics."""

import argparse
import csv
import fcntl
import json
from pathlib import Path
import subprocess
import urllib.request

import run_verified_batch as runner


TERMINAL = {"resolved", "unresolved", "empty_patch", "runner_error", "interrupted",
            "evaluation_error", "evaluation_timeout", "infrastructure_failure", "ambiguous_failure"}


def report(root, manifests, paths):
    tasks = manifests[0]["tasks"]
    rows = []
    pending = 0
    usage = {"input_tokens": 0, "output_tokens": 0, "available_attempts": 0}
    counts = {}
    for task in tasks:
        iid = task["instance_id"]
        row = {"instance_id": iid}
        values = []
        for trial, path in enumerate(paths, 1):
            state_file = path / iid / "state.json"
            state = json.loads(state_file.read_text()) if state_file.exists() else {"status": "pending"}
            status = state["status"]
            counts[status] = counts.get(status, 0) + 1
            done = status in TERMINAL
            pending += not done
            row[f"trial_{trial}"] = status
            values.append(int(status == "resolved") if done else None)
            try:
                result = runner.read_agent_result(path / iid / "agent-output.json")
                tokens = result.get("usage", {})
                if "input_tokens" in tokens:
                    usage["available_attempts"] += 1
                    for key in ("input_tokens", "output_tokens"):
                        usage[key] += tokens.get(key, 0)
            except (OSError, ValueError, TypeError):
                pass
        row["successes"] = sum(v or 0 for v in values)
        row["any_success"] = int(any(v == 1 for v in values))
        row["all_success"] = int(all(v == 1 for v in values)) if None not in values else ""
        rows.append(row)
    complete = pending == 0
    successes = sum(r["successes"] for r in rows)
    any_success = sum(r["any_success"] for r in rows)
    all_success = sum(r["all_success"] for r in rows) if complete else None
    n = len(rows)
    metrics = {
        "cases": n, "planned_attempts": 3 * n, "finished_attempts": 3 * n - pending,
        "complete": complete, "status_counts": counts,
        "successful_attempts_so_far": successes,
        "avg_score_percent": round(100 * successes / (3 * n), 2) if complete else None,
        "pass_at_3_percent": round(100 * any_success / n, 2) if complete else None,
        "pass_power_3_percent": round(100 * all_success / n, 2) if complete else None,
        "pass_rate_percent": round(100 * any_success / n, 2) if complete else None,
        "pass_rate_definition": "Alias of empirical pass@3 (at least one success); source definition unverified.",
        "definitions": {"avg_score": "successful attempts / (3 * cases)",
                        "pass@3": "cases with at least one success / cases",
                        "pass^3": "cases with three successes / cases"},
        "usage": usage, "trial_paths": [str(p) for p in paths],
        "limitations": "Host generation, Docker evaluation. Fresh workspaces/sessions; shared Qwen settings or memory may affect independence. No explicit sampling or reasoning settings enforced. Terminal failures count as unsuccessful; inspect infrastructure errors separately.",
    }
    runner.save(root / "metrics.json", metrics)
    with (root / "per_issue.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [f"Completed attempts: {3*n-pending}/{3*n}",
             "Version / model: see original batch versions.txt and manifest.json"]
    if complete:
        lines += [f"Avg Score: {metrics['avg_score_percent']}% ({successes}/{3*n})",
                  f"Pass Rate (= pass@3 here): {metrics['pass_at_3_percent']}% ({any_success}/{n})",
                  f"pass@3: {metrics['pass_at_3_percent']}%",
                  f"pass^3: {metrics['pass_power_3_percent']}% ({all_success}/{n})"]
    else:
        lines.append("Final three-trial metrics unavailable until all attempts finish.")
    lines.append(f"Reports: {root}")
    text = "\n".join(lines) + "\n"
    (root / "summary.txt").write_text(text)
    print(text, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    original = json.loads((baseline / "manifest.json").read_text())
    root = runner.ROOT / "repeated-trials" / baseline.name
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("This three-trial experiment is already running.")
    paths = [baseline, root / "trial-2", root / "trial-3"]
    manifests = [original]
    for path in paths[1:]:
        path.mkdir(exist_ok=True)
        target = path / "manifest.json"
        if not target.exists():
            runner.save(target, original)
        manifest = json.loads(target.read_text())
        if manifest != original:
            raise SystemExit("Trial configuration differs from the baseline.")
        manifests.append(manifest)
    if args.report_only:
        report(root, manifests, paths)
        return
    for task in original["tasks"]:
        state_file = baseline / task["instance_id"] / "state.json"
        if not state_file.exists() or json.loads(state_file.read_text())["status"] not in TERMINAL:
            raise SystemExit("Finish the baseline batch before running additional trials.")
    docker = subprocess.run(["docker", "ps"], capture_output=True, text=True)
    if docker.returncode:
        raise SystemExit("Docker access failed. Run newgrp docker, reactivate .venv, and retry.\n" + docker.stderr)
    with urllib.request.urlopen("http://127.0.0.1:9000/v1/models", timeout=20) as response:
        models = json.load(response)
    if original["config"]["model"] not in [m["id"] for m in models["data"]]:
        raise SystemExit("Configured model unavailable at tunnel endpoint")
    current_version = subprocess.check_output(["node", original["config"]["cli"], "--version"], text=True).strip()
    old_versions = (baseline / "versions.txt").read_text().splitlines()
    if current_version != old_versions[0].strip():
        raise SystemExit("Qwen CLI version changed since the baseline")
    print("Reusing baseline as trial 1. Running trials 2 and 3 sequentially.", flush=True)
    print("Automatic tool approval enabled; host workspaces are not sandboxes.", flush=True)
    try:
        for number, path in enumerate(paths[1:], 2):
            for index, task in enumerate(original["tasks"], 1):
                print(f"Trial {number}, issue {index}/{len(original['tasks'])}: {task['instance_id']}", flush=True)
                try:
                    runner.run_task(path, task, original["config"])
                except Exception as error:
                    folder = path / task["instance_id"]
                    folder.mkdir(exist_ok=True)
                    state_file = folder / "state.json"
                    state = json.loads(state_file.read_text()) if state_file.exists() else {"instance_id": task["instance_id"]}
                    state.update(status="runner_error", error=str(error))
                    runner.save(state_file, state)
                    print(f"Attempt failed: {error}", flush=True)
                report(root, manifests, paths)
    finally:
        report(root, manifests, paths)


if __name__ == "__main__":
    main()
