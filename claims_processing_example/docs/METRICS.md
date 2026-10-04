# What to report

This is the scoring contract for the claims benchmark. It defines what a run must
report, so that results from different agents, different models and different teams
can be put side by side.

Two things are measured and must not be confused. **Whether the decision is right**
is settled arithmetic: the verdict, the amount and the clause list come from a
deterministic function of the case, and no model of any kind judges them. **Whether
the written explanation is any good** is a separate, smaller question, judged
separately and never allowed near the numbers.

---

## 1. How a run must be made

- Run every case **k = 4 times**, independently.
- The agent gets the document bundle, this brief and its own tools. It must do its
  own tool calling. **Replaying a reference trace is not a run** — it measures
  next-token prediction, not agent behaviour.
- The agent never sees `case.json`, and never sees another case's answer.
- Every agent gets `docs/AGENT_BRIEF.md`, unchanged.
- Report the prompt ID. `docs/reference_prompt.md` is `claims-ref-1`; your own
  prompt gets its own ID and is reported separately.
- Submit the raw traces with the summary numbers.

**Break every number below down by tier and by product, as well as overall.** A
single average across tiers hides the thing worth knowing, which is where the agent
stops coping. The same goes for products: an agent that has learnt one insurer's
numbers will look fine on that product and fall over on the next.

## 2. Is the decision right

| Metric | Definition |
|---|---|
| Verdict accuracy | Exact match on APPROVE / PARTIAL / REJECT / ESCALATE |
| Verdict confusion matrix | The full 4x4. **Never report a single accuracy number.** |
| Amount exact match | Payable equals the gold amount exactly |
| Amount within tolerance | Within ±1%, which separates a rounding slip from a rule error |
| Clause precision / recall / F1 | Against the gold clause set, order-insensitive |
| Fully correct | Verdict **and** amount **and** clause set all right |

### Why the confusion matrix is mandatory

A wrong approval pays money that was never owed. A wrong rejection denies a sick
person a claim they were entitled to, and in India invites the Ombudsman and the
regulator. These are not interchangeable, and one number that averages them
destroys the only information a deployment decision needs. Report the matrix.

The two error directions worth naming separately:

- **REJECT where gold is APPROVE or PARTIAL** — the claimant is wrongly refused.
- **APPROVE where gold is REJECT** — the insurer pays a claim it should not have.

### Why the clause set matters

An agent can reach the right verdict for the wrong reason: rejecting a claim
because it misread the room rent, on a case that should be rejected for a waiting
period. The verdict alone cannot tell the two apart. Clause F1 can, and an agent
that scores well on verdicts and badly on clauses is not doing the job.

## 3. Is it reliable

| Metric | Definition |
|---|---|
| pass^k | Fraction of cases correct in **all** k runs |
| pass^1 | Mean single-run accuracy |
| Variance | The spread across the k runs |

An agent that scores 70% every run is a different product from one swinging 40-95%
and averaging 70. Report both, and report them for "fully correct", not for the
verdict alone.

## 4. How it behaved

| Metric | Definition |
|---|---|
| Completion rate | Terminated with a decision at all, rather than looping or giving up |
| Correctness rate | Of those that terminated, how many were right |
| Tool calls on success | Mean calls **on the cases it got right**. An unconditioned count rewards giving up early. |
| Redundant call rate | The identical call, with identical arguments, repeated |
| Schema error rate | Malformed arguments, wrong types, invented tool names |
| Semantic error rate | A valid call, but the wrong tool or the wrong arguments for the situation |
| Recovery rate | After a tool error, did it correct itself and carry on, or spiral |

Keep the three failure numbers apart. They have different causes and different
fixes: schema errors are raw model capability and should dominate the gap for
smaller self-hosted models; semantic errors are reasoning; recovery is the agent
loop.

## 5. Did it do the work

Scoring only the end state lets an agent be right by luck. Every case carries a
list of the checks that had to happen — that the policy was in force, that the
waiting periods were checked, that the room rate was compared with the limit — and
the gold answer records which of them the case turned on.

Report **check adherence**: of the checks a case required, how many the trace shows
the agent actually made. An agent that reaches the right verdict while skipping a
mandatory check is a failure on this axis, and should be reported as one even
though its verdict was right.

## 6. Escalation

| Metric | Definition |
|---|---|
| Escalation recall | Of the cases where gold is ESCALATE, how many it escalated |
| False escalation rate | Of the cases it could have decided, how many it escalated anyway |

Both, always. An agent that escalates everything is useless in a different way from
one that never escalates, and either looks acceptable on one of these numbers
alone. Escalations are about 12% of the dataset.

## 7. What it cost

| Metric | Portable? | Definition |
|---|---|---|
| Input / output tokens per case | yes | Counted from the provider's usage, not estimated |
| LLM round trips per case | yes | |
| Wall clock per case | **no** | A property of the deployment, not the agent |
| Cost per adjudicated case | yes, if stated in rupees at a stated accuracy | |

Wall clock is not comparable between a hosted API and a local GPU. Report it, but
never rank on it alone.

For a self-hosting comparison this section is the headline. The finding worth
having is not "the 8B model is worse". It is "the 8B model reaches X% of frontier
accuracy at Y% of the cost, and here is exactly where it breaks" — which is what
the per-tier and per-clause breakdowns are for.

## 8. The written explanation

Strictly separated from everything above.

- The verdict, the amount and the clause list are **deterministic**. Never let a
  model judge them, at any stage, for any reason.
- A judge scores **only the explanation**, on three things: does it cite the
  clauses that actually decided the case; is it free of claims the documents do
  not support; would a claimant understand it.
- Give the judge the gold clause list and the gold reasoning trace, so it grades
  against a reference rather than on impression.
- Report explanation scores beside the deterministic numbers, never folded into
  them.

## 9. Submission format

One JSON object per case per run, as JSON Lines:

```json
{
  "case_id": "case-000042",
  "run_index": 0,
  "product_id": "AROGYA_SANJEEVANI_GCI",
  "agent_version": "your-agent-0.3.1",
  "model": "provider/model-name",
  "prompt_id": "claims-ref-1",
  "verdict": "PARTIAL",
  "payable": 73419,
  "clauses": ["3.1_room_rent_limit", "A1_non_payable_items"],
  "explanation": "…",
  "completed": true,
  "trace": [
    {
      "step": 0,
      "at": "2026-09-24T10:15:02Z",
      "tool": "read_document",
      "arguments": {"name": "hospital_bill", "page": 1},
      "outcome": "ok",
      "error": null
    }
  ],
  "usage": {"input_tokens": 18422, "output_tokens": 1204, "round_trips": 9},
  "wall_clock_seconds": 41.2
}
```

- `completed` is `false` where the agent never called `submit`; `verdict`,
  `payable` and `clauses` are then `null`, and the case counts against the
  completion rate.
- `outcome` is `ok`, `schema_error`, `semantic_error` or `tool_error`, which is
  what the behaviour numbers are computed from.
- Timestamps are ISO 8601 in UTC.

Send the JSONL and the summary table. The summary is checked against the JSONL; if
they disagree, the JSONL is what counts.
