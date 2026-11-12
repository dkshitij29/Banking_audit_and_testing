# Balanced SWE-bench Verified experiments

Both experiments use the same 30 issues: 10 easy, 10 medium, and 10 hard,
with three attempts per issue (90 attempts per model). Selection details are
in `samples/verified-balanced30/sample.csv` and each experiment's manifest.
Difficulty groups map the dataset's time-estimate labels to easy (<15 min),
medium (15 min–1 hour), and hard (1–4 hours or >4 hours).

| Configuration | Average attempt success | Empirical pass@3 | Empirical pass^3 |
|---|---:|---:|---:|
| Qwen Code v0.25.3 + Qwen3.6-27B, 200,000 context | 48/90 (53.33%) | 21/30 (70.00%) | 13/30 (43.33%) |
| Qwen Code v0.25.3 + gemma-4-12B, 262,144 context | 13/90 (14.44%) | 7/30 (23.33%) | 2/30 (6.67%) |

## Artifact layout

- `batches/qwen27b-balanced30/`: Qwen trial 1.
- `repeated-trials/qwen27b-balanced30/`: Qwen combined reports, trial 2 and trial 3.
- `batches/gemma4-balanced30-larger-context/`: Gemma trial 1.
- `repeated-trials/gemma4-balanced30-larger-context/`: Gemma combined reports, trial 2 and trial 3.

For each issue, `state.json` records status, agent time, and evaluation time.
`agent-output.json` is the agent log; `model.patch` and `prediction.jsonl`
contain the proposed changes. `evaluation.log` and `evaluation-report.json`
record official grading when a nonempty patch was available. Manifests and
prompts describe the inputs; versions files record the agent source revision.
Qwen's archived connection-failed attempt is retained under `failed-attempts/`
for provenance and is not an additional scored trial.

## Interpretation and limits

- Average success = resolved attempts / 90; pass@3 = issues solved at least once / 30;
  pass^3 = issues solved all three times / 30. The report's Pass Rate is an alias of pass@3.
- Source checkouts and shell actions ran on the host; official patch evaluation ran in Docker.
- Non-resolved outcomes remain in the denominator, including ambiguous failures.
  Qwen has 8 ambiguous evaluations and Gemma has 9; missing modules and no-tests-collected
  require investigation before being interpreted as coding failures.
- Models had different context limits and serving configurations. This is a comparison
  of deployed agent/model setups, not an isolated model-capability measurement.
- Fresh sessions and workspaces were used, but automatic memory may influence independence.
- Timing totals omit preparation and downtime. Token counts are missing for some attempts.
- Dependencies, virtual environments, run locks, and cloned issue workspaces are excluded
  from this Git snapshot. Original local experiment directories are unchanged.

This is a 30-issue subset experiment, not a full 500-issue Verified score.
