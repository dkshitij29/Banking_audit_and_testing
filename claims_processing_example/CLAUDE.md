# CLAUDE.md — Indian Health Insurance Claims Benchmark Dataset

## What this project is

A generator that produces a benchmark dataset for evaluating AI agents on
health insurance claim adjudication, in the Indian (IRDAI) context.

Each generated case contains:

- a **structured case file** (JSON) with a deterministic gold answer, and
- a **document bundle** (PDFs) that an agent must read to reach that answer.

A separate team builds the agent. **This repo does not build an agent and does
not build an evaluation harness.** It produces data plus a scoring contract
that the agent team consumes.

## The one idea that everything depends on

Ground truth is computed by a deterministic Python function, never written by
an LLM.

The data flows in this direction, and only this direction:

```
  sample_case()          ->  a case as JSON (clean, structured)
  adjudicate(case)       ->  gold verdict + payable amount + clause IDs
  render(case)           ->  messy PDFs, written by an LLM
  validate(case, pdfs)   ->  keep or discard
```

The engine **never parses a PDF**. It already had clean data before the
documents existed. Parsing documents is the agent's job, not ours.

Two representations of the same case exist side by side:

| Artifact | Who sees it |
|---|---|
| `case.json` (inputs + gold) | scorer only, never the agent |
| `documents/*.pdf` | the agent only |

## Non-negotiable invariants

These are the rules that make the dataset trustworthy. Do not relax them
without asking.

1. **Only `engine/` decides gold answers.** No LLM output is ever a label.
2. **`render` may reformat, never invent.** Every fact in a document must
   trace to a field in `case.json`. If the renderer adds a date, an amount, or
   a diagnosis that is not in the case, the gold label is now wrong and the
   case is poison. This is what the validator exists to catch.
3. **The engine is pure.** No network, no clock, no randomness, no LLM calls.
   Same input, same output, forever.
4. **Every case is reproducible from a seed.** Given a seed, the sampler must
   produce byte-identical `case.json`.
5. **No real personal data.** All names, IDs, hospitals, and doctors are
   synthetic. Never scrape a real claim. The insurer on a generated document is
   synthetic too: the rules come from a real wording, but no document is issued
   in a real company's name, with a real UIN, or on a real insurer's letterhead.
   A standard product's own name (Arogya Sanjeevani) is IRDAI's, not a
   company's, and may be used.
6. **Never commit third-party PDFs.** See "Policy wording corpus" below.

## Repo layout

```
engine/
  rules.py           adjudicate() and its helper predicates
  schema.py          dataclasses / pydantic models for Policy, Claim, Decision
  clauses.py         clause ID registry, mapped to wording sections
  tables.py          placeholder disease lists, day-care list, non-payable items
sampler/
  sample.py          builds a case from a seed; writes a dataset
  profiles.py        product profile type, and the placeholder profile
  products/          one module per real wording: its terms and profile
  ambiguity.py       guards that discard cases resting on an open reading
  difficulty.py      tier logic — where facts get scattered
  scenarios.py       what each seed is aimed at; the 100-slot schedule
  catalogue.py       synthetic conditions, prices, names, hospitals
  case.py            the case.json schema
  rng.py             seeded draws, stable across Python versions
render/
  prompts/           one prompt template per document type
  llm.py             thin client wrapper, cached, deterministic settings
  layout.py          house style, formatting, HTML/CSS -> PDF
  documents.py       one renderer per per-case document type
  wording.py         the policy wording, generated per product
validate/
  checks.py          fact-presence and leakage checks
release/
  split.py           the public split to ship, and the gold split to keep
corpus/
  manifest.csv       source URLs for real IRDAI wordings (no PDFs committed)
  fetch.py           downloads wordings locally into corpus/pdfs/ (gitignored)
  mapping.yaml       maps engine clause IDs -> section refs in each wording
datasets/
  <name>/            generated output, gitignored
docs/
  METRICS.md         the scoring contract handed to the agent team
  AGENT_BRIEF.md     the task brief every agent receives
  reference_prompt.md  baseline system prompt + tool interface
tests/
```

## Domain: Indian health indemnity

Scope is **health only**. Do not add motor, life, or travel.

### Rule families the engine must implement

Implement these as separate, individually testable predicates. Each returns
whether it fired and which clause ID it corresponds to.

**Eligibility gates** (these reject outright, payable = 0)

- Policy in force: admission date within policy period.
- Initial waiting period: illness claims within the first N days of first
  policy inception are excluded; accidents are not.
- Specific disease waiting period: a named list (cataract, hernia, piles,
  kidney stones, joint replacement, and similar) has a longer wait.
- Pre-existing disease waiting period: longer still, and it keys off the
  declared PED list on the policy, not the diagnosis list.
- Permanent exclusions: procedures never covered under any circumstance.
- Hospitalisation qualification: at least 24 hours of admission, UNLESS the
  procedure is on the day-care list.

**Amount calculations** (these reduce payable, applied in a fixed order)

- Non-payable items: strip disallowed line items from the bill first
  (consumables, administrative charges, toiletries, and similar).
- Room rent sub-limit: if the actual per-day room rent exceeds the cap, apply
  a proportionate deduction to the associated charges. Which charges are
  "associated" is a configurable set and must be documented.
- ICU sub-limit: same shape, separate cap.
- Disease-wise sub-limit: a per-procedure cap (cataract per eye, for example).
- Deductible.
- Co-pay percentage.
- Sum insured cap, including any cumulative bonus.

**Ancillary**

- Pre-hospitalisation window and post-hospitalisation window.
- AYUSH treatment handling.

### Order of operations is part of the spec

The sequence above changes the answer. Co-pay applied before a sub-limit gives
a different number than after. Write the order down explicitly in
`engine/rules.py` as a module docstring, implement exactly that order, and
never reorder silently. A test must lock the order in place.

### Configuration, not hardcoding

Every number above (waiting period lengths, caps, co-pay percent, the disease
lists) is a **product parameter**, not a constant in code. They come from the
policy object. Different products carry different numbers.

**Important:** do not treat the specific durations and lists as known. Read
them from the actual IRDAI wording being modelled and record the source
section in `corpus/mapping.yaml`. Where a real wording is ambiguous, pick an
interpretation, write it down in a comment, and move on — but the engine must
match the document the agent is given.

Each real product lives in `sampler/products/<product>.py`: its terms, with
each value citing the wording's section, and its sampler profile. Placeholder
lists live in `engine/tables.py` under `PLACEHOLDER_*` names, and terms built
from them carry `source="UNVERIFIED_PLACEHOLDER"`. Nothing carrying that
source may be released. Golden tests define their own test product, so the
placeholders never change their answers; each real product also gets golden
cases of its own, worked by hand from its wording.

Where a wording can defensibly be read two ways and the choice changes an
answer, the engine takes one reading and a guard in `sampler/ambiguity.py`
discards every drawn case the other reading would decide differently. No case
may depend on a contested reading. Record the reading and the guard in
`corpus/mapping.yaml`.

### Clause IDs

Every rule has a stable ID: `<section>_<slug>`, for example
`4.2_specific_disease_waiting`. These IDs are graded, so they must be stable
across regenerations. `engine/clauses.py` is the single registry.

`corpus/mapping.yaml` maps each clause ID to where that rule actually appears
in each real policy wording (document, page, section number). This is what
makes clause-level grading meaningful: the gold clause list points at real
text the agent could have found.

## The case schema

`case.json`, one per case:

```
case_id            stable, derived from seed
seed               integer
product_id         which policy wording this case is written against
difficulty         "easy" | "medium" | "hard"
scenario_tags      e.g. ["room_rent_breach", "copay", "within_waiting"]

policy             sum insured, caps, co-pay, deductible, dates,
                   declared PEDs, cumulative bonus, members
claim              diagnosis (clinical term + code), procedure,
                   admission/discharge datetimes, room category and
                   per-day rate, itemised bill lines, hospital, doctor

gold
  verdict          "APPROVE" | "REJECT" | "PARTIAL" | "ESCALATE"
  payable          integer rupees
  clauses          list of clause IDs that fired, order-insensitive
  reasoning_trace  ordered steps: fact -> clause -> effect
                   (for inspection and for judge grounding; not graded
                    directly)

documents          list of generated file paths
provenance         engine version, ruleset hash, render model, timestamp
```

`reasoning_trace` is produced by the engine as a by-product — each predicate
records what it saw and what it did. It is not LLM-written.

### Verdicts and the answer key

Decided 2026-09-23. The full statement, with the order of operations, is the
module docstring of `engine/rules.py`.

- **REJECT** — a gate fired, or nothing is left to pay after the amount steps.
- **PARTIAL** — something is paid, and a limit or exclusion cut part of the
  claim: room rent or ICU limit, disease sub-limit, AYUSH cap, sum insured
  used up, bills outside the pre/post window, excluded line items. This is
  what Indian regulation calls partial repudiation.
- **APPROVE** — something is paid, and the only reductions were non-payable
  items, deductible or co-pay. Those are cost sharing the policyholder agreed
  to, not a disallowance. (Every bill carries non-payables, so if they made a
  claim PARTIAL there would be no APPROVE cases at all.)
- **ESCALATE** — checked after the gates, and only when a missing document or
  a contradiction could change the outcome. If a gate already rejects the
  claim on facts the documents establish, the verdict is REJECT.

`gold.clauses` lists what explains the outcome:

- a gate rejected: every gate that fired, not just the first, and nothing else;
- otherwise: the exceptions that stopped a gate from rejecting (accident
  exception, day-care) plus every amount step that reduced the payable.

Exceptions are in the answer key so that an agent which never checked a rule
cannot score the same as one that checked it and applied the exception.

## Difficulty tiers

Difficulty is **where the facts live**, not how complex the arithmetic is.

- **easy** — every fact needed appears in the claim form. Retrieval is trivial;
  this tier isolates arithmetic and rule application.
- **medium** — facts are split across two or three documents. Admission date on
  the discharge summary, room rate in the bill.
- **hard** — a needed fact appears only in the long policy wording, far from
  where the related coverage clause sits, and the diagnosis is written
  clinically so it does not string-match the rule's name. Multiple rules
  interact (a sub-limit AND a co-pay AND a partial exclusion).

Tag every case. The agent team reports metrics per tier; a single average
across tiers hides the thing worth knowing.

How the sampler applies the tiers (`sampler/difficulty.py` writes a placement
plan per case; the renderer follows it and the validator checks it):

- **easy** — every claim fact the answer needs is also on the claim form, and
  every product rule it needs is also restated on the policy certificate.
- **medium** — claim facts stay in their natural homes (dates and diagnosis in
  the discharge summary, amounts in the bill); rules are restated on the
  certificate.
- **hard** — nothing is copied; at least one rule that decides the case is
  only in the wording, and the diagnosis is written clinically.
- In every tier, three lists live only in the wording, because no real
  certificate restates them: non-payable items, excluded bill items, and the
  required claim documents.

The mix is fixed per 100 seeds: 35 APPROVE, 40 PARTIAL, 13 REJECT, 12
ESCALATE; 34 easy, 33 medium, 33 hard. Seed n takes slot n mod 100, so adding
seeds never changes an existing case.

### Deliberate hard cases to include

- **Exclusion vs coverage near-miss.** A procedure that is covered, described
  in language almost identical to an exclusion elsewhere in the wording.
- **Diagnosis obfuscation.** The discharge summary says "senile cataract,
  right eye, phacoemulsification with IOL"; the rule keys on "cataract".
- **Day-care trap.** Under 24 hours of admission, but the procedure IS on the
  day-care list, so it is payable. Naive agents reject these.
- **Accident exception.** Inside the initial waiting period, but the cause is
  an accident, so the wait does not apply.
- **Escalation cases.** Documents genuinely contradict each other (bill total
  disagrees with claim form), or a required document is missing, and the gap
  could change the outcome. Gold verdict is `ESCALATE`. Roughly 8–12% of the
  dataset. These test whether an agent knows when not to decide, which matters
  more than accuracy on clean cases. Include the mirror image too: a gap that
  cannot change the outcome (an amount mismatch on a claim a gate rejects
  anyway). Those must still be decided; escalating them is a false escalation.

## Document rendering

Five document types. Text PDFs with selectable text — no scanning, no OCR
noise, for now. Realistic layout and tables.

1. **Policy certificate** — policy number, members, sum insured, period,
   room rent cap, co-pay, declared PEDs. Short, semi-structured, table-heavy.
   It also restates exactly the product rules the placement plan assigns to it,
   which is how the easy and medium tiers differ from the hard one.
2. **Policy wording** — the long rules document. Shared per `product_id`, not
   generated per case. Generated from the same `ProductTerms` the engine
   adjudicates with, so the document and the answer key cannot drift apart, and
   numbered to match the clause registry: gold clause `4.2_specific_disease_waiting`
   points at section 4.2 of the document the agent was given. The rules are the
   real product's; the words are this repo's, and nothing is copied from the
   insurer's PDF.
3. **Discharge summary** — clinical prose on hospital letterhead. Admission
   and discharge datetimes, presenting complaint, diagnosis in clinical
   language, procedure, treating doctor.
4. **Hospital bill** — itemised. Room charges shown as rate x days, surgery,
   pharmacy, consumables, investigations. Must include non-payable items so
   the agent has to strip them.
5. **Claim form** — the filled form. May contain minor inconsistencies with
   the bill, because real ones do — but only where the case is tagged for it.
   Minor means it cannot change the outcome; one that can is an escalation case.

### Renderer rules

- **Code places every fact; the model writes only prose.** Dates, amounts,
  names, ages, codes, the diagnosis and the length of stay are read from
  `case.json` and formatted by `render/layout.py`. The model is given the
  admission's facts as context, and writes narrative using tokens where a fact
  belongs — "admitted on {admitted} with {diagnosis}" — which the renderer then
  substitutes. A document therefore cannot carry a date or an amount the case
  does not have. This is stricter than asking the model to reformat the case
  JSON, and it is what makes invariant 2 hold by construction rather than by
  inspection.
- **The prose is checked before it is used**, and the case is discarded if it
  stays bad: no digits, no numbers spelled out, no token the case does not
  have, no rule vocabulary, no verdict words. One corrective retry, naming the
  fault, then discard.
- What the model is left to invent is qualitative narrative — "the pain had
  been troubling her for a few days", "the wound was healthy at discharge".
  Nothing the gold answer depends on. Anything specific enough to matter
  (including how an accident happened, `Claim.cause_note`) is a field of the
  case.
- The model is never told an amount, the policy, or the gold answer.
- Deterministic settings, cached by the hash of the whole request, so
  regeneration is free and stable. A PDF is stamped with the day its issuer
  would have printed it, never with the clock, or the bytes would differ on
  every run.
- Every call is metered against a spending cap and refused before it is sent if
  it would pass the cap.
- The renderer must not use the rule's own vocabulary. If a clause is called
  "specific disease waiting period", that phrase must not appear in the
  discharge summary.
- Vary surface form across cases: different hospital names, letterhead
  layouts, date formats (DD/MM/YYYY vs DD-Mon-YYYY), currency formatting
  (1,20,000 vs 120000). An agent that only works on one format is overfit. A
  hospital writes the same way in every case it appears in; an insurer's forms
  are consistent per product.
- Documents whose prose came from the offline stub instead of a model are
  marked and are never releasable, exactly as placeholder product terms are.

## The validation gate

Every case is checked before it enters the dataset. Discard on any failure and
log why. Report the discard rate; a rate above ~15% means the render prompts
need work.

- **Fact presence** — every gold-relevant fact (dates, amounts, diagnosis,
  room rate, caps) appears somewhere in the rendered bundle, in some form.
  If a fact the agent needs is missing, the case is unanswerable.
- **No fabrication** — numbers and dates appearing in documents reconcile with
  the case. Extract all currency amounts and dates from the PDFs and check
  they are either in the case or derivable from it.
- **Arithmetic consistency** — bill line items sum to the stated total.
- **No leakage** — the words of the gold verdict must not appear. No document
  says "claim rejected", "not payable", "waiting period not completed", or
  names a clause ID. The documents describe what happened; they never state
  the conclusion.
- **Difficulty honesty** — for `hard` cases, assert the required fact is NOT
  in the claim form.

Leakage is the most likely silent failure. Test it explicitly.

## Policy wording corpus

Real IRDAI policy wordings, fetched from insurer websites.

**Never commit the PDFs.** Follow the manifest pattern: `corpus/manifest.csv`
records source URL, insurer, product name, UIN, retrieval date, page count,
and a licence note for each document. `corpus/fetch.py` reconstructs the
corpus from the manifest. `corpus/pdfs/` is gitignored.

Start with 3–5 products from different insurers. Different wordings differ in
structure and phrasing, which is the variation the dataset needs.

For each product, hand-extract the rules into a product profile and fill in
`corpus/mapping.yaml`. This is manual work and it is the slowest part of the
project. Do it carefully — every gold label downstream depends on the engine
matching what the document actually says.

## Output

```
datasets/<name>/
  cases/<case_id>/case.json
  cases/<case_id>/documents/*.pdf
  wordings/<product_id>.pdf
  index.jsonl          one row per case: id, product, difficulty, tags,
                       gold verdict, payable, clause count, doc paths
  manifest.json        generator version, ruleset hash, counts, seed range,
                       discard rate, tier and verdict distribution
```

Ship a **public split** (documents + case IDs, gold withheld) and a
**gold split**, so the agent team can be scored without being able to train
against the answers. `release/split.py` builds both under
`datasets/<name>/public/` and `datasets/<name>/gold/`. The public half carries
no verdict, amount, clause list, difficulty tier or scenario name, and its
manifest reports no distribution of any of them: an agent that knows the base
rates can play them. It ships the three documents of `docs/` with it, so the
brief travels with the data. `tests/test_split.py` reads the public half back
off disk and fails if an answer is anywhere in it.

Target size for a first release: 500–1000 cases across 3–5 products, roughly
balanced across tiers, with the verdict mix reflecting realistic skew rather
than 50/50.

## docs/METRICS.md — the contract for the agent team

Generate this as a standalone document. It is a deliverable of this repo. It
defines what the agent team must report, so that results from different agents
and different models are comparable.

### Required run protocol

- Every case run **k = 4** times independently.
- Report per-tier and per-product breakdowns, never only the overall average.
- The agent receives the document bundle and its own tools. It must do its own
  tool calling. **Replaying a reference trace is not a valid run** — it
  measures next-token prediction, not agent behaviour.
- The agent never receives `case.json`.
- Every agent receives the task brief, `docs/AGENT_BRIEF.md`.
- Submit raw traces alongside summary numbers.

### Task brief and reference prompt

Two companion documents, versioned with the dataset:

- `docs/AGENT_BRIEF.md` — **required**. The gold answer depends on conventions
  the case documents do not state: verdict definitions, when to escalate, the
  order deductions apply in where a wording is silent, rounding, the clause ID
  list, the output format. An agent not told these is graded on guessing our
  conventions. The brief carries no product numbers (those come from the
  documents) and no hints ("check the day-care list" would give the hard tier
  away). Generate its clause list from `engine/clauses.py`.
  Anything that can differ between products (whether a deductible is per
  claim, whether accidents are exempt from a wait, what a sub-limit covers)
  belongs in that product's documents, never in the brief. The brief holds
  only conventions that are the same for every product. It must say that the
  bundle holds three claim documents (claim form, itemised bill, discharge
  summary) and that intake verified the other documents a wording lists (ID,
  KYC, bank details, reports), or an agent that reads the wording's document
  list will escalate every case.
- `docs/reference_prompt.md` — **recommended**. A baseline system prompt built
  around the brief, plus the tool interface (names and arguments; the agent
  team implements it). Model comparisons hold the prompt and tools fixed and
  change only the model; otherwise they measure prompt engineering. Also the
  starting point for demos. Teams may run their own prompts; those results
  are reported separately.

### Correctness

| Metric | Definition |
|---|---|
| Verdict accuracy | Exact match on APPROVE/REJECT/PARTIAL/ESCALATE |
| Verdict confusion matrix | Full 4x4. **Never report a single accuracy number.** A wrong approval leaks money; a wrong rejection harms a claimant and creates regulatory exposure. These are not interchangeable and averaging destroys the information. |
| Amount exact match | Payable equals gold exactly |
| Amount within tolerance | Within ±1% — separates rounding from rule errors |
| Clause precision / recall / F1 | Against gold clause IDs. Catches right-answer-wrong-reason. |
| Fully correct | Verdict AND amount AND clause set all correct |

### Reliability

| Metric | Definition |
|---|---|
| pass^k | Fraction of cases correct in all k runs |
| pass^1 | Mean single-run accuracy |
| Variance | Spread across the k runs |

An agent scoring 70% every run is a different product from one swinging
40–95% and averaging 70%. Report both.

### Behaviour

| Metric | Definition |
|---|---|
| Completion rate | Terminated with a decision at all (did not loop or bail) |
| Correctness rate | Of those, how many were right |
| Tool calls on success | Mean calls **on cases it got right**. Unconditioned call counts reward giving up early. |
| Redundant call rate | Identical call with identical arguments repeated |
| Schema error rate | Malformed arguments, wrong types, hallucinated tool names. Raw model capability; expect this to dominate the gap for smaller self-hosted models. |
| Semantic error rate | Valid call, wrong tool or wrong parameters for the situation |
| Recovery rate | After a tool error, did it correct and continue, or spiral |

Keep the three tool-failure numbers separate. They have different causes and
different fixes.

### Mandatory checks

Scoring the end state alone lets an agent be right by luck. For each case,
define the checks that must have happened — policy-in-force verified, waiting
period checked, room rent compared against the cap — and report adherence. An
agent that reaches the right verdict while skipping a mandatory check should
be scored as a failure on this axis.

### Escalation

| Metric | Definition |
|---|---|
| Escalation recall | Of cases where gold is ESCALATE, how many escalated |
| False escalation rate | Of decidable cases, how many escalated anyway |

Both matter. An agent that escalates everything is useless in a different way
from one that never escalates.

### Cost and latency

| Metric | Definition |
|---|---|
| Input / output tokens per case | Portable across deployments |
| LLM round trips per case | Portable |
| Wall clock per case | **Not portable** — a property of the deployment, not the agent. Report it, but never compare a hosted API against a local GPU on this number alone. |
| Cost per adjudicated case | Rupees, at a stated accuracy level |

For a self-hosting comparison this is the headline. The interesting finding is
not "the 8B model is worse" — it is "the 8B reaches X% of frontier accuracy at
Y% of the cost, and here is exactly where it breaks."

### Response quality

Split it, strictly:

- Verdict, payable amount, and clause IDs are **deterministic**. Never let an
  LLM judge near them.
- A judge scores **only the written explanation**, and only for: does it cite
  the clauses that actually fired, is it free of claims not supported by the
  documents, is it intelligible to a claimant.
- Give the judge the gold clause list and `reasoning_trace` so it grades
  against a reference rather than on impression.

### Submission format

Define a JSON schema for results so runs are comparable. One record per case
per run: case_id, run_index, predicted verdict, predicted payable, predicted
clause IDs, full tool-call trace with timestamps and outcomes, token counts,
model identifier, agent version, and prompt ID (the reference prompt's
version, or a hash of the team's own prompt).

## Build order

1. `engine/` plus its tests. No LLM anywhere. Unit test each predicate and
   lock the order of operations.
2. `sampler/` producing valid cases with gold labels. At this point you have a
   structured-only dataset that is already useful.
3. `corpus/` — fetch 1 real wording, hand-map its rules, get the engine to
   match it.
4. `render/` for one document type, end to end, one case.
5. `validate/` — including the leakage check.
6. Remaining document types.
7. Scale to 3–5 products, generate the full dataset.
8. `docs/METRICS.md`, `docs/AGENT_BRIEF.md` and `docs/reference_prompt.md`.

Do not start rendering before the engine is tested. Everything downstream
inherits its correctness.

## Testing requirements

- Golden tests: a fixed set of hand-computed cases with hand-verified answers.
  These are the only labels a human writes, and they exist to prove the engine
  itself is right.
- Property tests: payable never exceeds sum insured; payable is never
  negative; a rejected claim always has payable = 0; adding a non-payable line
  item never increases payable.
- Determinism test: same seed, identical output, twice.
- Order-of-operations test: locks the calculation sequence.
- Leakage test: run the validator against a known-bad document and confirm it
  is caught.

## Things not to do

- Do not let an LLM produce or adjust a gold label.
- Do not let the engine read a PDF.
- Do not hardcode product parameters into rule logic.
- Do not commit real policy wording PDFs or any real claim data.
- Do not add motor, life, or travel.
- Do not build an agent or an evaluation harness here.
- Do not reorder the calculation sequence without updating the test and the
  docstring.
