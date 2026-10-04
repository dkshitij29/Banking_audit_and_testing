# Task brief

You are settling health insurance claims for an Indian insurer. For each case you
are given the documents an insurer would hold, and you decide the claim.

This brief tells you the conventions the answer key uses. It does not tell you any
policy's rules: those are in the documents, and they differ from one policy to the
next. Read the documents you are given for every case; do not carry numbers from
one case to another.

Give this brief to the agent, unchanged, on every case. Results from agents that
were briefed differently are not comparable.

---

## 1. What you are given

Each case is a folder of PDFs, and one policy wording shared by every case written
against the same product:

| Document | Who wrote it | What it gives you |
|---|---|---|
| Policy wording | the insurer | what the policy covers, what it does not, and on what conditions |
| Certificate of insurance | the insurer | this policy's sum insured, period, members, and the limits that apply to it |
| Claim form | the claimant | the claimant's own account of the admission and what is claimed |
| Discharge summary | the hospital | the clinical record: dates, diagnosis, procedure, treating doctor |
| Hospital bill | the hospital | the charges, itemised |

Three of these are documents the claimant submits: the claim form, the hospital
bill and the discharge summary. **A case may be missing one of them.** The insurer's
own certificate and wording are always present.

The insurer's other intake requirements — identity proof, KYC, bank details,
investigation reports, the prescription advising admission — were checked when the
claim was registered. Their absence from the bundle is not a reason to escalate.
Only the three documents listed above matter to your decision.

Nothing in the bundle tells you the answer. No document states whether the claim is
payable, and none names a clause of this scheme.

## 2. The four verdicts

| Verdict | When |
|---|---|
| `APPROVE` | Something is paid, and the only things that reduced it were items the policy never pays for as separate charges, a deductible, or a co-payment. |
| `PARTIAL` | Something is paid, and a limit or an exclusion cut part of the claim. |
| `REJECT` | Nothing is paid: a condition of cover was not met, or nothing survived the deductions. |
| `ESCALATE` | You cannot decide, because a document is missing or two documents contradict each other, and the gap could change the outcome. |

The line between `APPROVE` and `PARTIAL` is the one to be careful with. A
deductible and a co-payment are cost sharing the policyholder agreed to when
buying the policy, and so are the sundry items no policy pays for as separate
charges — a bill almost always carries some. None of those makes a claim
`PARTIAL`. A room rent limit, an intensive care limit, a limit for a particular
condition, a cap on what the policy will pay in a year, an expense outside the
window the policy allows before or after the stay, or an item the policy excludes
by name: any of those does.

## 3. When to escalate, and when not to

Escalate only where the gap could change the outcome.

- **A required document is missing.** If the discharge summary is missing, escalate:
  the diagnosis, the dates and the cause are all in it, and nothing can be checked
  without it. If the bill or the claim form is missing, escalate — unless the claim
  already fails a condition of cover on the documents you do have, in which case
  decide it.
- **Two documents disagree.** If the claim form's dates differ from the hospital's,
  work the claim out on each set of dates. If the verdict or the amount differ,
  escalate; if they come to the same thing, decide on the hospital's records. If the
  amount claimed differs from the bill total, escalate — unless the claim already
  fails a condition of cover, in which case decide it.

Escalating a case you could have decided counts against you, and so does deciding a
case you should have escalated. Both are reported.

Check whether the claim fails a condition of cover **before** you consider
escalating. A claim that plainly fails one is `REJECT`, not `ESCALATE`, however
untidy the paperwork.

## 4. Working out the amount

Start from the bill. Apply what the policy says in this order, each step working on
what the step before it left:

1. Drop expenses dated outside the window the policy allows before admission or
   after discharge.
2. Remove bill lines the policy does not pay for: the items it lists as not
   payable, and anything it excludes by name.
3. If the room rate is above the policy's limit, reduce the room charge and
   whatever the policy says is reduced with it, in the proportion the limit bears
   to the rate charged.
4. The same for intensive care, against its own limit.
5. Cap what is left at any limit the policy sets for this particular condition or
   procedure.
6. Cap what is left at any limit on the system of medicine used.
7. Subtract the deductible.
8. Subtract the co-payment.
9. Cap at the sum insured, together with any cumulative bonus.

The order changes the answer, so follow it. Where a policy states its own order,
the policy governs and you should say so in your explanation.

**Rounding.** Work each step exactly and round that step's deduction to the nearest
rupee, halves up. Do not round the running total. Every amount you report is a
whole number of rupees.

**A rejected or escalated claim pays nothing.** Report `0`.

## 5. Which clauses to cite

Cite the clauses that explain your outcome, using the identifiers below and no
others. Order does not matter.

- If you reject the claim because a condition of cover was not met, cite **every**
  condition it failed, not just the first one you found.
- If you escalate, cite only the escalation clauses.
- Otherwise cite every step that reduced the amount, and every exception you
  relied on to keep the claim alive — if a waiting period would have applied but
  the cause was an accident, that exception is part of your reasoning and belongs
  in the list.

<!-- clause-table -->

**Whether the stay counts as hospitalisation**

| Clause | What it is |
|---|---|
| `2.1_min_hospitalisation` | Minimum duration of hospitalisation |
| `2.2_day_care` | Day-care treatment |

**Limits on what is paid**

| Clause | What it is |
|---|---|
| `3.1_room_rent_limit` | Room rent limit and proportionate deduction |
| `3.2_icu_limit` | ICU charges limit |
| `3.3_disease_sublimit` | Disease- or procedure-wise sub-limit |
| `3.4_ayush` | AYUSH treatment |
| `3.5_pre_hospitalisation` | Pre-hospitalisation expenses |
| `3.6_post_hospitalisation` | Post-hospitalisation expenses |

**Waiting periods and exclusions**

| Clause | What it is |
|---|---|
| `4.1_ped_waiting` | Pre-existing disease waiting period |
| `4.2_specific_disease_waiting` | Specified disease or procedure waiting period |
| `4.2_accident_exception` | Accident exception to the specified disease waiting period |
| `4.3_initial_waiting` | Initial waiting period |
| `4.3_accident_exception` | Accident exception to the initial waiting period |
| `4.4_investigation_evaluation` | Investigation and evaluation |
| `4.5_rest_cure_rehabilitation` | Rest cure, rehabilitation and respite care |
| `4.6_obesity_weight_control` | Obesity and weight control |
| `4.7_change_of_gender` | Change-of-gender treatment |
| `4.8_cosmetic_surgery` | Cosmetic or plastic surgery |
| `4.9_hazardous_sports` | Hazardous or adventure sports |
| `4.10_breach_of_law` | Breach of law |
| `4.11_excluded_providers` | Excluded providers |
| `4.12_substance_abuse` | Alcoholism, drug or substance abuse |
| `4.13_hydros_spas` | Health hydros, nature cure clinics and spas |
| `4.14_dietary_supplements` | Dietary supplements and non-prescription substances |
| `4.15_refractive_error` | Refractive error |
| `4.16_unproven_treatments` | Unproven treatments |
| `4.17_sterility_infertility` | Sterility and infertility |
| `4.18_maternity` | Maternity |

**What the policyholder bears**

| Clause | What it is |
|---|---|
| `5.1_deductible` | Deductible |
| `5.2_copay` | Co-payment |
| `5.3_sum_insured` | Sum insured and cumulative bonus |

**The policy itself**

| Clause | What it is |
|---|---|
| `6.1_policy_period` | Policy period |

**The claim papers**

| Clause | What it is |
|---|---|
| `7.1_missing_documents` | Required claim documents |
| `7.2_document_mismatch` | Consistency of claim documents |

**Items no policy pays for as a separate charge**

| Clause | What it is |
|---|---|
| `A1_non_payable_items` | List of non-payable items |

## 6. What to return

One JSON object:

```json
{
  "verdict": "APPROVE | PARTIAL | REJECT | ESCALATE",
  "payable": 0,
  "clauses": ["4.2_specific_disease_waiting"],
  "explanation": "Two or three sentences a claimant could understand, citing the clauses that decided it."
}
```

`payable` is a whole number of rupees, with no separators and no currency symbol.

Your explanation is read by a person, not matched against a template. It should say
what you decided and why, name the clauses that decided it, and claim nothing the
documents do not support.
