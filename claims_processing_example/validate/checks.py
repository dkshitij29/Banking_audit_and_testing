"""The gate every case passes before it enters the dataset.

The renderer is careful, but care is not proof: this module reads the finished
PDFs back as text and checks them against case.json. A case that fails any check
is discarded and the reason logged (CLAUDE.md, "The validation gate").

  fact presence      every fact the answer needs is in the documents the
                     placement plan assigns it to. A fact the agent cannot find
                     makes the case unanswerable.
  no fabrication     every date and every amount in a document is one the case
                     has. A renderer that invents a number has silently moved
                     the right answer.
  arithmetic         the bill's lines add up to the total it states.
  no leakage         no document names a clause, states a verdict, or uses the
                     vocabulary of a rule. This is the likeliest silent failure,
                     so it is checked hardest.
  difficulty honesty a hard case's deciding rule is in the wording only, and its
                     facts are not copied onto the claim form.

Checks run against whichever documents exist, so the gate is useful from the
first document type onwards and tightens as the rest arrive.

Nothing here reads the engine's verdict to decide anything: it compares
documents with the case that produced them.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from engine import clauses as C
from engine.rules import cap_amount
from engine.schema import BP_SCALE, BillCategory, Phase, TreatmentSystem, Verdict
from render import layout
from render.documents import BANNED
from render.layout import Issuer, Style
from sampler.case import Case
from sampler.difficulty import Difficulty, Doc, Fact

BILL_FACTS = (Fact.BILL_LINES, Fact.ROOM_RATE, Fact.ICU_RATE, Fact.PRE_POST_BILLS)
"""What the hospital bill is for. Repeating these on the claim form is what the
easy tier does and the others must not."""

HOSPITAL_DOCS = (Doc.DISCHARGE_SUMMARY, Doc.HOSPITAL_BILL)
"""Written by the hospital, which knows nothing of the policy. Insurance
vocabulary of any kind here is leakage: a bill that groups its own
"non-payable items" has done the agent's work for it."""

INSURER_DOCS = (Doc.POLICY_CERTIFICATE, Doc.POLICY_WORDING, Doc.CLAIM_FORM)
"""The insurer's own, which state the rules on purpose. They may name a waiting
period or a co-pay; they may never state how this claim came out."""

CONCLUSION_WORDS = ("payable", "admissible", "inadmissible", "approved", "rejected", "repudiated",
                    "repudiation", "sanctioned", "settlement", "reimbursable", "disallowed",
                    "deduction", "deducted")
"""Banned in a hospital document, which has no view on any of this. A policy
wording uses these words constantly and legitimately.

Not "settled": a discharge summary says the pain settled, the swelling settled,
the fever settled. A claim being settled is caught by VERDICT_PHRASES instead.
Every word here is also in the list the renderer gives the model
(render.documents.BANNED), so nothing is rejected that was never asked for."""

VERDICT_PHRASES = (
    "claim rejected", "claim approved", "claim is payable", "claim is not payable", "claim not payable",
    "stands rejected", "stands approved", "hereby rejected", "amount allowed", "amount disallowed",
    "claim settled", "waiting period not completed", "within the waiting period",
)
"""A finding about this claim in particular. No document may say one of these,
whoever wrote it: a wording states rules, never outcomes."""

DATE_PATTERNS = (
    re.compile(r"\b(\d{2})/(\d{2})/(\d{4})\b"),
    re.compile(r"\b(\d{2})-([A-Z][a-z]{2})-(\d{4})\b"),
    re.compile(r"\b(\d{2})\.(\d{2})\.(\d{4})\b"),
    re.compile(r"\b(\d{1,2}) ([A-Z][a-z]+) (\d{4})\b"),
)
MONEY_MARKED = re.compile(r"(?:₹|\bRs\.?\s*|\bINR\s*)(\d[\d,]*)(?:\.(\d{2}))?|\b(\d{1,3}(?:,\d{2,3})+)(?:\.(\d{2}))?")
"""An amount is only read as money when it carries a currency mark or digit grouping.
A bare run of digits is a registration or policy number, not a rupee figure."""


@dataclass(frozen=True)
class Finding:
    check: str
    doc: Doc | None
    detail: str

    def __str__(self) -> str:
        where = f" [{self.doc.value.lower()}]" if self.doc else ""
        return f"{self.check}{where}: {self.detail}"


# ---------------------------------------------------------------- reading a document back


def text_of(path: Path) -> str:
    from pypdf import PdfReader

    return " ".join(page.extract_text() or "" for page in PdfReader(path).pages)


def normalise(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def squash(text: str) -> str:
    """Whitespace removed, for a phrase an extractor may have broken up."""
    return re.sub(r"\s+", "", text).lower()


def holds(text: str, phrase: str) -> bool:
    """Whether a document says this.

    A phrase with a digit in it has to stand on its own: ₹700 is not "in" a
    document that only ever says ₹1,700. Words are looser, and also compared with
    the whitespace removed, since an extractor can break a phrase up.
    """
    flat = normalise(text)
    if any(character.isdigit() for character in phrase):
        pattern = r"\s*".join(re.escape(part) for part in phrase.split())
        # Not part of a longer number, but a comma or full stop after it is just
        # punctuation: "the period ends 11/07/2026, both days inclusive".
        return re.search(rf"(?<!\d)(?<![\d][,.]){pattern}(?!\d)(?![,.]\d)", flat, re.IGNORECASE) is not None
    return phrase.lower() in flat.lower() or squash(phrase) in squash(flat)


# ---------------------------------------------------------------- every way a fact can be written


def _styles() -> list[Style]:
    """One style per way of writing a date, a clock and an amount."""
    base = layout.style_for("probe", issuer=Issuer.HOSPITAL)
    out = []
    for date in ("slashes", "dashes", "dots", "long"):
        for clock in (True, False):
            for money in ("symbol", "rs", "inr", "suffix"):
                for grouping in ("indian", "western"):
                    for paise in (True, False):
                        out.append(replace(base, date=date, clock_24h=clock, money=money,
                                           grouping=grouping, paise=paise))
    return out


STYLES = _styles()


def written_dates(date: dt.date) -> set[str]:
    return {layout.format_date(date, style) for style in STYLES}


def written_datetimes(moment: dt.datetime) -> set[str]:
    return {layout.format_datetime(moment, style) for style in STYLES} | written_dates(moment.date())


def written_money(amount: int) -> set[str]:
    return {layout.format_money(amount, style) for style in STYLES} | {
        layout.group_digits(amount, "indian"), layout.group_digits(amount, "western")
    }


RULE_PHRASES = frozenset(
    {"proportion", "proportionate", "day care", "day-care", "AYUSH"}
    | {clause.description for clause in C.REGISTRY.values()}
)
"""Words that can only come from stating a rule."""


def restatement_marks(spellings: set[str]) -> set[str]:
    """The spellings that show a rule has been restated.

    A rule is recognised by its parameter — ninety days, 2% of the sum insured,
    twenty-four hours — and not by the name of the condition it applies to. A
    certificate lists the pre-existing diseases a member declared, and
    "Hypertension" there is that member's history, not the ninety-day waiting
    period that happens to bear the same name.
    """
    return {spelling for spelling in spellings
            if any(character.isdigit() for character in spelling) or spelling in RULE_PHRASES}


def bill_marks(case: Case, fact: Fact) -> list[set[str]]:
    """What it would take for a document to have copied the bill: its money.

    Not its dates. A bill dated the day of discharge shares that date with every
    document in the bundle, which says nothing about where the money is.
    """
    claim = case.claim
    if fact is Fact.PRE_POST_BILLS:
        return [unambiguous(written_money(line.amount))
                for line in claim.bill if line.phase is not Phase.INPATIENT]
    return [unambiguous(spellings) for spellings in requirements(case, fact)]


def unambiguous(spellings: set[str]) -> set[str]:
    """The spellings a document could not carry by accident.

    Used when asking whether something is present that should not be. A bare "400"
    is also a postal code, a room number and a page count, so only the spellings
    that carry a currency mark or digit grouping count against a document. The
    other direction stays generous: for a fact that must be stated, any spelling
    of it will do.
    """
    return {spelling for spelling in spellings if not spelling.isdigit()}


def written_percent(bp: int) -> set[str]:
    whole, rest = divmod(bp, 100)
    return {f"{whole}%", f"{whole} %", f"{whole}.{rest:02d}%"}


# ---------------------------------------------------------------- what each fact looks like


def requirements(case: Case, fact: Fact, doc: Doc | None = None) -> list[set[str]]:
    """What a document stating this fact must contain: one set per thing that must
    appear, any one spelling of it being enough. Empty when there is nothing to
    look for (an illness has no cause note).

    A few facts are stated differently by different documents, so the document is
    taken into account: a wording gives the rule for a limit ("2% of the sum
    insured, at most ₹5,000"), while a certificate gives the figure that limit
    comes to for the policy in hand.
    """
    claim, policy = case.claim, case.policy
    member = next(m for m in policy.members if m.member_id == claim.member_id)
    terms = policy.terms
    match fact:
        case Fact.ADMISSION:
            # On the claim form the claimant's own version counts, which is the
            # point of a case where the two disagree.
            form = {claim.claim_form.admitted_at} if claim.claim_form else set()
            return [set().union(*(written_datetimes(m) for m in {claim.admitted_at} | form))]
        case Fact.DISCHARGE:
            form = {claim.claim_form.discharged_at} if claim.claim_form else set()
            return [set().union(*(written_datetimes(m) for m in {claim.discharged_at} | form))]
        case Fact.DIAGNOSIS:
            return [{claim.primary_dx.term}]
        case Fact.PROCEDURES:
            return [{procedure.term} for procedure in claim.procedures]
        case Fact.CAUSE:
            return [{claim.cause_note}] if claim.cause_note else []
        case Fact.TREATMENT_SYSTEM:
            if claim.treatment_system is TreatmentSystem.ALLOPATHY:
                return []
            return [{claim.treatment_system.value.replace("_", " and ").title()}]
        case Fact.AYUSH_HOSPITAL:
            if claim.treatment_system is TreatmentSystem.ALLOPATHY:
                return []
            return [{"AYUSH hospital"} if claim.hospital.ayush_hospital
                    else {"not registered as an AYUSH hospital", "not an AYUSH hospital"}]
        case Fact.BILL_LINES:
            return [written_money(line.amount) for line in claim.bill]
        case Fact.ROOM_RATE:
            return [written_money(line.unit_price) for line in claim.bill
                    if line.category is BillCategory.ROOM]
        case Fact.ICU_RATE:
            return [written_money(line.unit_price) for line in claim.bill
                    if line.category is BillCategory.ICU]
        case Fact.PRE_POST_BILLS:
            return [written_dates(line.date) for line in claim.bill if line.phase is not Phase.INPATIENT]
        case Fact.CLAIMED_AMOUNT:
            return [written_money(claim.claim_form.claimed_amount)] if claim.claim_form else []
        case Fact.CLAIM_FORM_DATES:
            if claim.claim_form is None:
                return []
            return [written_datetimes(claim.claim_form.admitted_at),
                    written_datetimes(claim.claim_form.discharged_at)]
        case Fact.POLICY_PERIOD:
            return [written_dates(policy.period_start), written_dates(policy.period_end)]
        case Fact.SUM_INSURED:
            return [written_money(policy.sum_insured)]
        case Fact.CUMULATIVE_BONUS:
            return [written_money(policy.cumulative_bonus)] if policy.cumulative_bonus else []
        case Fact.COPAY:
            return [written_percent(policy.copay_bp)] if policy.copay_bp else []
        case Fact.DEDUCTIBLE:
            return [written_money(policy.deductible)] if policy.deductible else []
        case Fact.FIRST_INCEPTION:
            return [written_dates(member.first_inception)]
        case Fact.DECLARED_PEDS:
            return [{ped.name} for ped in member.declared_peds]
        case Fact.ROOM_CAP:
            return [_cap_spellings(terms.room_cap, policy.sum_insured, doc)] if terms.room_cap else []
        case Fact.ICU_CAP:
            return [_cap_spellings(terms.icu_cap, policy.sum_insured, doc)] if terms.icu_cap else []
        case _:
            return rule_requirements(case, fact, doc)


def _cap_spellings(cap, sum_insured: int, doc: Doc | None) -> set[str]:
    """A limit as the reader would meet it: the rule in the wording, the amount
    everywhere else."""
    spellings = written_money(int(cap_amount(cap, sum_insured)))
    if doc is Doc.POLICY_WORDING and cap.bp_of_si:
        spellings |= {f"{cap.bp_of_si // 100}%"}
        if cap.rupees:
            spellings |= written_money(cap.rupees)
    return spellings


def _matches(match, claim) -> bool:
    """The engine's rule of match, repeated here so the gate does not import it:
    the primary diagnosis's code by prefix, or any procedure code."""
    by_code = any(claim.primary_dx.icd10.startswith(prefix) for prefix in match.icd10_prefixes)
    return by_code or any(p.code in match.procedure_codes for p in claim.procedures)


def rule_requirements(case: Case, fact: Fact, doc: Doc | None = None) -> list[set[str]]:
    """How a document would state the product rule that decides this case.

    Only the part of a rule this claim turns on: the waiting period its condition
    sits in, the exclusion it matches, the sub-limit that caps it. A certificate
    that restates a whole rule book would still be caught by the one line that
    matters.
    """
    claim, terms = case.claim, case.policy.terms
    match fact:
        case Fact.INITIAL_WAIT:
            wait = terms.initial_wait.duration
            return [{wait.describe(), wait.adjective()}]
        case Fact.PED_WAIT:
            return [{terms.ped_wait.describe(), terms.ped_wait.adjective()}]
        case Fact.SPECIFIED_DISEASES:
            groups = [g for g in terms.specific_wait.groups if _matches(g.match, claim)]
            return [{group.name, group.duration.describe(), group.duration.adjective()} for group in groups]
        case Fact.EXCLUSIONS:
            matched = [e for e in terms.exclusions if _matches(e.match, claim)]
            return [{C.REGISTRY[exclusion.clause_id].description} for exclusion in matched]
        case Fact.SUBLIMITS:
            matched = [s for s in terms.sublimits if _matches(s.match, claim)]
            return [{sublimit.name, sublimit.name.split(",")[0]}
                    | _cap_spellings(sublimit.cap_per_unit, case.policy.sum_insured, doc)
                    for sublimit in matched]
        case Fact.MIN_STAY:
            return [{f"{terms.min_stay_hours} hours", f"{terms.min_stay_hours} consecutive hours",
                     f"{terms.min_stay_hours}-hour"}]
        case Fact.DAY_CARE_LIST:
            return [{"day care", "day-care"}]
        case Fact.PRE_POST_WINDOWS:
            return [{f"{terms.pre_hospitalisation_days} days prior", f"{terms.pre_hospitalisation_days} days before"},
                    {f"{terms.post_hospitalisation_days} days from", f"{terms.post_hospitalisation_days} days after"}]
        case Fact.AYUSH_TERMS:
            return [{"AYUSH"}]
        case Fact.ROOM_ASSOCIATED:
            return [{"proportion", "proportionate"}]
        case _:
            return []  # the non-payable lists and the document list: no short phrase stands for them


# ---------------------------------------------------------------- the checks


def fact_presence(case: Case, texts: dict[Doc, str]) -> list[Finding]:
    """Every fact the answer needs, in the documents the plan puts it in."""
    findings = []
    for fact, docs in case.placement.facts.items():
        for doc in docs:
            if doc not in texts:
                continue
            for wanted in requirements(case, fact, doc):
                if not any(holds(texts[doc], spelling) for spelling in wanted):
                    findings.append(Finding("fact_presence", doc, f"{fact.value} is missing ({_one(wanted)})"))
    return findings


def _one(wanted: set[str]) -> str:
    return sorted(wanted)[0]


def leakage(case: Case, texts: dict[Doc, str]) -> list[Finding]:
    """No document may name a clause or state how the claim came out. Hospital
    documents may not use insurance vocabulary at all."""
    findings = []
    for doc, text in texts.items():
        plain = normalise(text)
        lowered = plain.lower()
        for clause in C.REGISTRY:
            if clause.lower() in lowered:
                findings.append(Finding("leakage", doc, f"names the clause {clause}"))
        for verdict in Verdict:  # the gold wording itself, which no real document uses
            if re.search(rf"\b{verdict.value}\b", plain):
                findings.append(Finding("leakage", doc, f"states the verdict {verdict.value}"))
        for phrase in VERDICT_PHRASES:
            if phrase in lowered:
                findings.append(Finding("leakage", doc, f"states a conclusion: {phrase!r}"))
        if doc in HOSPITAL_DOCS:
            for word in BANNED + CONCLUSION_WORDS:
                if re.search(rf"\b{re.escape(word)}\b", lowered):
                    findings.append(Finding("leakage", doc, f"a hospital document uses {word!r}"))
    return findings


def allowed_dates(case: Case) -> set[dt.date]:
    claim, policy = case.claim, case.policy
    dates = {policy.period_start, policy.period_end, claim.admitted_at.date(), claim.discharged_at.date()}
    dates |= {member.first_inception for member in policy.members}
    dates |= {member.dob for member in policy.members}
    dates |= {line.date for line in claim.bill}
    if claim.claim_form:
        dates |= {claim.claim_form.admitted_at.date(), claim.claim_form.discharged_at.date()}
    return dates


def allowed_amounts(case: Case) -> set[int]:
    """Every rupee figure a document may show: the case's own, and the sums a
    bill legitimately adds up."""
    claim, policy, terms = case.claim, case.policy, case.policy.terms
    amounts = {line.amount for line in claim.bill} | {line.unit_price for line in claim.bill}
    amounts |= {policy.sum_insured, policy.cumulative_bonus, policy.deductible,
                policy.sum_insured + policy.cumulative_bonus}
    if claim.claim_form:
        amounts.add(claim.claim_form.claimed_amount)
    inpatient = [line for line in claim.bill if line.phase is Phase.INPATIENT]
    amounts.add(sum(line.amount for line in claim.bill))
    amounts.add(sum(line.amount for line in inpatient))
    for phase in Phase:
        amounts.add(sum(line.amount for line in claim.bill if line.phase is phase))
    for category in BillCategory:
        amounts.add(sum(line.amount for line in claim.bill if line.category is category))
    for cap in (terms.room_cap, terms.icu_cap, terms.ayush.cap, *(s.cap_per_unit for s in terms.sublimits)):
        if cap is None:
            continue
        # The limit that applies, and both halves of how it is arrived at: a
        # certificate states "₹2,000 (2% of the sum insured, at most ₹5,000)".
        amounts.add(int(cap_amount(cap, policy.sum_insured)))
        amounts.add(int(cap_amount(cap, policy.sum_insured)) * 2)  # a per-eye cap, both eyes
        if cap.rupees:
            amounts.add(cap.rupees)
        if cap.bp_of_si:
            amounts.add(policy.sum_insured * cap.bp_of_si // BP_SCALE)
    return {amount for amount in amounts if amount}


PER_CASE_DOCS = (Doc.POLICY_CERTIFICATE, Doc.CLAIM_FORM, Doc.DISCHARGE_SUMMARY, Doc.HOSPITAL_BILL)
"""Written for one claim, so every figure on them is that claim's. The policy
wording is shared by every case written against the product and states the
product's own figures, so it is checked against the product (tests/test_render.py)
rather than against a case."""


def no_new_dates(case: Case, texts: dict[Doc, str]) -> list[Finding]:
    known = allowed_dates(case)
    findings = []
    for doc, text in {d: t for d, t in texts.items() if d in PER_CASE_DOCS}.items():
        for found in _dates_in(normalise(text)):
            if found not in known:
                findings.append(Finding("no_fabrication", doc, f"shows the date {found.isoformat()}"))
    return findings


def _dates_in(text: str) -> set[dt.date]:
    months = {name: n for n, name in enumerate(layout.MONTHS_SHORT, start=1)}
    months |= {name: n for n, name in enumerate(layout.MONTHS_LONG, start=1)}
    found = set()
    for pattern in DATE_PATTERNS:
        for day, month, year in pattern.findall(text):
            number = months.get(month, None) if not month.isdigit() else int(month)
            if number is None:
                continue
            try:
                found.add(dt.date(int(year), number, int(day)))
            except ValueError:
                continue
    return found


def no_new_amounts(case: Case, texts: dict[Doc, str]) -> list[Finding]:
    known = allowed_amounts(case)
    findings = []
    for doc, text in {d: t for d, t in texts.items() if d in PER_CASE_DOCS}.items():
        for amount in _amounts_in(normalise(text)):
            if amount not in known:
                findings.append(Finding("no_fabrication", doc, f"shows the amount {amount}"))
    return findings


def _amounts_in(text: str) -> set[int]:
    found = set()
    for marked, _, grouped, _ in MONEY_MARKED.findall(text):
        digits = (marked or grouped).replace(",", "")
        if digits:
            found.add(int(digits))
    return found


def arithmetic(case: Case, texts: dict[Doc, str]) -> list[Finding]:
    """The bill's lines add up to the total it states."""
    text = texts.get(Doc.HOSPITAL_BILL)
    if text is None:
        return []
    total = sum(line.amount for line in case.claim.bill)
    if not any(holds(normalise(text), spelling) for spelling in written_money(total)):
        return [Finding("arithmetic", Doc.HOSPITAL_BILL, f"does not state the total of its lines ({total})")]
    return []


def difficulty_honesty(case: Case, texts: dict[Doc, str]) -> list[Finding]:
    """A hard case must stay hard: its deciding rule is in the wording only."""
    if case.difficulty is not Difficulty.HARD:
        return []
    findings = []
    # The certificate is the one document that restates the product's rules, so it
    # is the one that can restate a rule the tier meant to leave in the wording. A
    # hospital document or a claim form naming a tonsillectomy is not restating the
    # rule that lists tonsillectomy: it is saying what was done, which it must.
    # Insurance vocabulary in a hospital document is leakage, and the leakage check
    # has that.
    if Doc.POLICY_CERTIFICATE in texts:
        for fact in case.placement.wording_only:
            for wanted in (restatement_marks(spellings) for spellings in requirements(case, fact)):
                if wanted and any(holds(texts[Doc.POLICY_CERTIFICATE], spelling) for spelling in wanted):
                    findings.append(Finding("difficulty_honesty", Doc.POLICY_CERTIFICATE,
                                            f"restates {fact.value}, a wording-only rule"))
    # What the claim form must not do is save the agent from reading the bill.
    # Every claim form states the dates and the diagnosis; only the easy tier
    # repeats the money.
    if Doc.CLAIM_FORM in texts:
        for fact in BILL_FACTS:
            if Doc.CLAIM_FORM in case.placement.facts.get(fact, ()):
                continue
            for wanted in bill_marks(case, fact):
                if wanted and any(holds(texts[Doc.CLAIM_FORM], spelling) for spelling in wanted):
                    findings.append(Finding("difficulty_honesty", Doc.CLAIM_FORM,
                                            f"copies {fact.value}, which this tier keeps to the bill"))
    return findings


CHECKS = (fact_presence, leakage, no_new_dates, no_new_amounts, arithmetic, difficulty_honesty)


def validate(case: Case, documents: dict[Doc, Path]) -> list[Finding]:
    """Everything wrong with this case's documents. Empty means keep it."""
    texts = {doc: text_of(path) for doc, path in documents.items()}
    return [finding for check in CHECKS for finding in check(case, texts)]


# ---------------------------------------------------------------- CLI


FILENAMES = {
    Doc.DISCHARGE_SUMMARY: "discharge_summary.pdf",
    Doc.HOSPITAL_BILL: "hospital_bill.pdf",
    Doc.CLAIM_FORM: "claim_form.pdf",
    Doc.POLICY_CERTIFICATE: "policy_certificate.pdf",
}


def documents_of(dataset: Path, case_id: str, product_id: str) -> dict[Doc, Path]:
    """The bundle an agent would be handed: this case's documents, and the policy
    wording its product shares."""
    folder = dataset / "cases" / case_id / "documents"
    found = {doc: folder / name for doc, name in FILENAMES.items() if (folder / name).exists()}
    wording = dataset / "wordings" / f"{product_id}.pdf"
    if wording.exists():
        found[Doc.POLICY_WORDING] = wording
    return found


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--report", type=Path, help="where to write the findings (default: in the dataset)")
    args = parser.parse_args(argv)

    rows = [json.loads(line) for line in (args.dataset / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    checked, discarded, reasons, report = 0, [], Counter(), {}
    for row in rows:
        folder = args.dataset / "cases" / row["case_id"]
        documents = documents_of(args.dataset, row["case_id"], row["product_id"])
        if not (documents.keys() - {Doc.POLICY_WORDING}):
            continue
        case = Case.model_validate_json((folder / "case.json").read_text(encoding="utf-8"))
        findings = validate(case, documents)
        checked += 1
        if findings:
            discarded.append(row["case_id"])
            report[row["case_id"]] = [str(finding) for finding in findings]
            reasons.update(finding.check for finding in findings)

    rate = len(discarded) / checked if checked else 0.0
    path = args.report or args.dataset / "validation.json"
    path.write_text(json.dumps(
        {"checked": checked, "discarded": len(discarded), "discard_rate": round(rate, 4),
         "reasons": dict(sorted(reasons.items())), "findings": report}, indent=2) + "\n", encoding="utf-8")
    print(f"checked {checked} rendered cases, discarded {len(discarded)} ({rate:.1%})")
    for reason, count in sorted(reasons.items()):
        print(f"  {reason}: {count}")
    if rate > 0.15:
        print("  discard rate above 15%: the render prompts need work (CLAUDE.md)")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
