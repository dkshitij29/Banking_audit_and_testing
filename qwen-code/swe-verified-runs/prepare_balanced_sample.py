"""Prepare, but do not execute, a fresh 10/10/10 difficulty-stratified sample."""

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import random
import subprocess

from datasets import Dataset, load_dataset

import run_verified_batch as runner


GROUPS = {
    "easy": ["<15 min fix"],
    "medium": ["15 min - 1 hour"],
    "hard": ["1-4 hours", ">4 hours"],
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", required=True, help="Exact served model ID")
    parser.add_argument("--name", default="verified-balanced30")
    parser.add_argument("--seed", type=int, default=20261109)
    args = parser.parse_args()
    if Path(args.name).name != args.name or args.name in (".", ".."):
        parser.error("Name must be a single folder name")
    batch = runner.ROOT / "batches" / args.name
    if (batch / "manifest.json").exists():
        saved = json.loads((batch / "manifest.json").read_text())
        if saved.get("seed") != args.seed or saved["config"]["model"] != args.model or saved.get("difficulty_mapping") != GROUPS:
            raise SystemExit("Existing sample uses different settings; choose another --name")
        print(f"Existing selection preserved: {batch}")
        print(Counter(t["difficulty_group"] for t in saved["tasks"]))
        return

    # Read the existing Arrow cache directly: no reference patches are exported.
    cache = Path.home() / ".cache/huggingface/datasets/SWE-bench___swe-bench_verified"
    arrows = sorted(cache.rglob("*test.arrow")) if cache.exists() else []
    if arrows:
        source = arrows[-1]
        dataset = Dataset.from_file(str(source))
        provenance = {"cached_arrow": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
    else:
        dataset = load_dataset(runner.DATASET, split="test")
        provenance = {"fingerprint": dataset._fingerprint}

    excluded = set()
    exclusion_sources = []
    for directory in ("batches", "extensions", "repeated-trials"):
        for path in sorted((runner.ROOT / directory).rglob("manifest.json")):
            manifest = json.loads(path.read_text())
            ids = [t["instance_id"] for t in manifest.get("tasks", [])]
            excluded.update(ids)
            exclusion_sources.append(str(path))
    for path in (runner.ROOT / "agent-runs").glob("*/*/artifacts/metadata.json"):
        metadata = json.loads(path.read_text())
        excluded.add(metadata["instance_id"])
        exclusion_sources.append(str(path))

    rng = random.Random(args.seed)
    chosen = []
    availability = {}
    for group, labels in GROUPS.items():
        pool = sorted((t for t in dataset if t["difficulty"] in labels and t["instance_id"] not in excluded),
                      key=lambda t: t["instance_id"])
        availability[group] = len(pool)
        if len(pool) < 10:
            raise SystemExit(f"Only {len(pool)} unused {group} issues available; need 10")
        for task in rng.sample(pool, 10):
            chosen.append({**{k: task[k] for k in ("instance_id", "repo", "base_commit", "problem_statement", "difficulty")},
                           "difficulty_group": group})
    rng.shuffle(chosen)
    assert len({t["instance_id"] for t in chosen}) == 30
    assert not excluded.intersection(t["instance_id"] for t in chosen)
    baseline = runner.ROOT / "batches/verified-20261025-200909-712162"
    config = dict(json.loads((baseline / "manifest.json").read_text())["config"])
    config.update(model=args.model, model_label=f"qwen-code-{args.model}")
    version = subprocess.check_output(["node", config["cli"], "--version"], text=True)
    commit = subprocess.check_output(["git", "-C", str(Path(config["cli"]).parent.parent), "rev-parse", "HEAD"], text=True)
    batch.mkdir(parents=True)
    runner.save(batch / "manifest.json", {
        "dataset": runner.DATASET, "seed": args.seed, "config": config,
        "difficulty_mapping": GROUPS, "difficulty_note": "Custom easy/medium/hard grouping of dataset time-estimate labels, not model-specific difficulty.",
        "source": provenance, "excluded_ids": sorted(excluded), "exclusion_sources": exclusion_sources,
        "eligible_pool_sizes": availability, "tasks": chosen,
    })
    (batch / "versions.txt").write_text(version + commit)
    (batch / "issue-ids.txt").write_text("\n".join(t["instance_id"] for t in chosen) + "\n")
    with (batch / "sample.csv").open("w", newline="") as output:
        fields = ["instance_id", "difficulty_group", "difficulty", "repo", "base_commit"]
        writer = csv.DictWriter(output, fields, extrasaction="ignore")
        writer.writeheader(); writer.writerows(chosen)
    print(f"Prepared: {batch}")
    print("Selected: 10 easy + 10 medium + 10 hard; overlap with existing selections: 0")
    print(f"Excluded {len(excluded)} previously selected or pilot issue IDs")
    print(f"Remaining eligible pool sizes: {availability}")
    print("No agent attempts have been started.")


if __name__ == "__main__":
    main()
