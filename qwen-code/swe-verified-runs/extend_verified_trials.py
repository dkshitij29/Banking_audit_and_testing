"""Add non-overlapping issues with three attempts and combine both experiments."""

import argparse
import csv
import fcntl
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

import run_verified_batch as runner
import run_three_trials as trials


def select_additional(tasks, excluded, count, seed):
    pool = sorted((task for task in tasks if task["instance_id"] not in excluded),
                  key=lambda task: task["instance_id"])
    if count < 1 or count > len(pool):
        raise ValueError("Additional count must be positive and fit the remaining dataset")
    return random.Random(seed).sample(pool, count)


def combine(root, baseline, additional, included=()):
    batches = [baseline, *included, additional]
    manifests = [json.loads((path / "manifest.json").read_text())
                 for path in batches]
    ids = [set(t["instance_id"] for t in m["tasks"]) for m in manifests]
    if sum(map(len, ids)) != len(set().union(*ids)):
        raise ValueError("Issue overlap detected; refusing to combine")
    rows = []
    for batch, manifest in zip(batches, manifests):
        repeated = runner.ROOT / "repeated-trials" / batch.name
        for task in manifest["tasks"]:
            row = {"instance_id": task["instance_id"],
                   "group": "additional" if batch == additional else "original"}
            results = []
            for n, path in enumerate((batch, repeated / "trial-2", repeated / "trial-3"), 1):
                state = path / task["instance_id"] / "state.json"
                status = json.loads(state.read_text())["status"] if state.exists() else "pending"
                row[f"trial_{n}"] = status
                results.append(int(status == "resolved") if status in trials.TERMINAL else None)
            row["successful_attempts"] = sum(v or 0 for v in results)
            row["finished_attempts"] = sum(v is not None for v in results)
            row["any_success"] = int(1 in results)
            row["all_success"] = int(all(v == 1 for v in results)) if None not in results else ""
            rows.append(row)
    finished = sum(r["finished_attempts"] for r in rows)
    planned = len(rows) * 3
    complete = finished == planned
    successes = sum(r["successful_attempts"] for r in rows)
    any_success = sum(r["any_success"] for r in rows)
    all_success = sum(r["all_success"] for r in rows) if complete else None
    metrics = {
        "cases": len(rows), "original_cases": sum(map(len, ids[:-1])), "additional_cases": len(ids[-1]),
        "overlap": 0, "planned_attempts": planned, "finished_attempts": finished,
        "complete": complete, "successful_attempts_so_far": successes,
        "avg_score_percent": round(100 * successes / planned, 2) if complete else None,
        "pass_at_3_percent": round(100 * any_success / len(rows), 2) if complete else None,
        "pass_power_3_percent": round(100 * all_success / len(rows), 2) if complete else None,
        "pass_rate_percent": round(100 * any_success / len(rows), 2) if complete else None,
        "pass_rate_definition": "Alias of empirical pass@3, not an independently verified source definition",
        "failure_policy": "All terminal failures count as unsuccessful. Pending attempts do not receive final metrics.",
        "baseline": str(baseline), "additional": str(additional),
        "included_batches": [str(p) for p in included],
        "limitations": "Subset only; host generation, Docker evaluation; shared agent memory may affect trial independence.",
    }
    counts = {}
    for row in rows:
        for n in (1, 2, 3):
            status = row[f"trial_{n}"]
            counts[status] = counts.get(status, 0) + 1
    metrics["status_counts"] = counts
    runner.save(root / "combined_metrics.json", metrics)
    with (root / "combined_per_issue.csv").open("w", newline="") as output:
        writer = csv.DictWriter(output, list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    lines = [f"Cases: {sum(map(len, ids[:-1]))} original + {len(ids[-1])} additional = {len(rows)} (no overlap)",
             f"Completed attempts: {finished}/{planned}"]
    if complete:
        lines.extend([f"Avg Score: {metrics['avg_score_percent']}% ({successes}/{planned})",
                      f"Pass Rate (= pass@3): {metrics['pass_at_3_percent']}% ({any_success}/{len(rows)})",
                      f"pass@3: {metrics['pass_at_3_percent']}%",
                      f"pass^3: {metrics['pass_power_3_percent']}% ({all_success}/{len(rows)})"])
    else:
        lines.append("Final metrics pending: more attempts must finish.")
    lines.append(f"Reports: {root}")
    text = "\n".join(lines) + "\n"
    (root / "combined_summary.txt").write_text(text)
    print(text, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--include-batch", type=Path, action="append", default=[],
                        help="Previously completed additional batch to exclude and include in totals; repeatable")
    parser.add_argument("--additional", type=int, default=10)
    parser.add_argument("--seed", type=int, default=43)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    args = parser.parse_args()
    baseline = args.baseline.resolve()
    original = json.loads((baseline / "manifest.json").read_text())
    included = [p.resolve() for p in args.include_batch]
    existing = [baseline, *included]
    seen = set()
    for path in existing:
        manifest = json.loads((path / "manifest.json").read_text())
        if manifest["config"] != original["config"] or manifest["dataset"] != original["dataset"]:
            raise SystemExit("Existing batch configuration or dataset differs from baseline")
        ids = [t["instance_id"] for t in manifest["tasks"]]
        if len(ids) != len(set(ids)) or seen.intersection(ids):
            raise SystemExit("Overlapping existing batches")
        seen.update(ids)
        for iid in ids:
            for trial in (path, runner.ROOT / "repeated-trials" / path.name / "trial-2",
                          runner.ROOT / "repeated-trials" / path.name / "trial-3"):
                state = trial / iid / "state.json"
                if not state.exists() or json.loads(state.read_text())["status"] not in trials.TERMINAL:
                    raise SystemExit(f"Existing trial is incomplete: {state}")
    suffix = ""
    if included:
        suffix = "-with-" + hashlib.sha256("\n".join(str(p) for p in included).encode()).hexdigest()[:8]
    root = runner.ROOT / "extensions" / f"{baseline.name}-plus-{args.additional}-seed-{args.seed}{suffix}"
    root.mkdir(parents=True, exist_ok=True)
    lock = (root / "run.lock").open("w")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("This extension is already running in another terminal.")
    batch = root / f"extra-{baseline.name}-{args.additional}-{args.seed}"
    if not (batch / "manifest.json").exists():
        if args.report_only:
            raise SystemExit("Extension not prepared yet. Run without --report-only first.")
        from datasets import load_dataset
        dataset = load_dataset(original["dataset"], split="test")
        excluded = seen
        selected = select_additional(dataset, excluded, args.additional, args.seed)
        batch.mkdir()
        manifest = {"dataset": original["dataset"],
                    "dataset_fingerprint": getattr(dataset, "_fingerprint", None),
                    "seed": args.seed, "config": original["config"],
                    "tasks": [{k: task[k] for k in ("instance_id", "repo", "base_commit", "problem_statement")}
                              for task in selected]}
        runner.save(batch / "manifest.json", manifest)
        (root / "new-issue-ids.txt").write_text("\n".join(t["instance_id"] for t in selected) + "\n")
        # Preserve provenance and verify the installed version before any new generation.
        (batch / "versions.txt").write_text((baseline / "versions.txt").read_text())
    extra = json.loads((batch / "manifest.json").read_text())
    if seen.intersection(t["instance_id"] for t in extra["tasks"]):
        raise SystemExit("Saved selection overlaps an existing batch")
    if extra["config"] != original["config"]:
        raise SystemExit("Configuration mismatch with original batch")
    if args.report_only or args.prepare_only:
        combine(root, baseline, batch, included)
        return
    expected = (baseline / "versions.txt").read_text().splitlines()
    cli = original["config"]["cli"]
    current = subprocess.check_output(["node", cli, "--version"], text=True).strip()
    commit = subprocess.check_output(["git", "-C", str(Path(cli).parent.parent), "rev-parse", "HEAD"], text=True).strip()
    if current != expected[0].strip() or commit != expected[1].strip():
        raise SystemExit("Agent version or source commit differs from the original experiment")
    combine(root, baseline, batch, included)
    try:
        subprocess.run([sys.executable, str(runner.ROOT / "run_verified_batch.py"),
                        "--resume", str(batch)], check=True)
        subprocess.run([sys.executable, str(runner.ROOT / "run_three_trials.py"),
                        "--baseline", str(batch)], check=True)
    finally:
        combine(root, baseline, batch, included)


if __name__ == "__main__":
    main()
