"""One renderer per document type. Facts come from the case; prose comes from the model.

How a document is built, and why it is built this way:

1. **Code places every fact.** Dates, amounts, names, ages, codes, the diagnosis
   and the length of stay are read from case.json and formatted by
   render/layout.py. The model never types one.
2. **The model writes prose, with tokens where a fact belongs.** It is given the
   admission's facts as context and a list of tokens such as `{admitted}` and
   `{diagnosis}`. It writes "was admitted on {admitted} with {diagnosis}", and
   this module substitutes the formatted values. A document therefore cannot
   carry a date or an amount the case does not have.
3. **The prose is checked before it is used.** No digits, no number words, no
   unknown tokens, no rule vocabulary, no verdict words (`BANNED`). A rejected
   reply is asked for once more with the fault named; a second failure raises
   ProseRejected and the case is discarded.

What is left to the model is qualitative narrative: that the trouble had been
going on "for a few days", that the wound was healthy, that the patient was
advised to return if the pain worsened. None of it is a fact the gold answer
depends on, and step 5's validator checks the whole bundle against the case
again.

Documents rendered by render/llm.py's stub carry model STUB_NO_LLM and are never
releasable, exactly as placeholder product terms are not.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from string import Template

from engine import clauses as C
from engine.rules import cap_amount
from engine.schema import BillCategory, Cause, DocType, Phase, TreatmentSystem
from render import layout
from render.layout import Issuer, Style
from render.llm import STUB_MODEL, Client, stub_client
from sampler.case import Case
from sampler.difficulty import Difficulty, DiagnosisStyle, Doc, Fact
from sampler.rng import Rng

PROMPTS = Path(__file__).resolve().parent / "prompts"
MAX_ATTEMPTS = 2

TOKEN = re.compile(r"\{([a-z_]+)\}")
DIGIT_RUN = re.compile(r"\d+")
NUMBER_WORDS = ("two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
                "twelve", "fifteen", "twenty", "thirty", "forty", "fifty", "sixty", "hundred",
                "thousand", "lakh", "crore", "twice", "thrice")
BANNED = ("payable", "admissible", "inadmissible", "covered", "coverage", "claim", "claims", "policy",
          "insurer", "insurance", "premium", "sum insured", "cumulative bonus", "deductible", "co-pay",
          "copay", "co-payment", "copayment", "sub-limit", "sublimit", "waiting period", "pre-existing",
          "preexisting", "day care", "day-care", "daycare", "exclusion", "excluded", "exclude", "excludes",
          "proportionate", "non-payable", "nonpayable", "reimburse", "reimbursement", "reimbursable",
          "repudiate", "repudiated", "clause", "irdai", "approved", "rejected", "sanctioned", "settlement",
          "disallowed", "deduction", "deducted")
"""Words that would leak the answer or name a rule. Kept here so the validator
(step 5) checks the finished PDFs against the same list."""

BANNED_RE = re.compile(r"\b(" + "|".join(re.escape(word) for word in BANNED) + r")\b", re.IGNORECASE)
NUMBER_RE = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.IGNORECASE)

DISCHARGE_SUMMARY_FIELDS = ("presenting_complaint", "history", "examination", "course_in_hospital",
                            "condition_at_discharge", "advice_on_discharge")
MAX_FIELD_CHARS = 900

WITHOUT_A_MODEL = "NO_MODEL"
"""A document of pure facts: tables and figures, with no prose to write."""


class ProseRejected(RuntimeError):
    """The model's prose broke a rule twice. The case is discarded, not patched."""


@dataclass(frozen=True)
class Rendered:
    doc: Doc
    path: Path
    model: str
    prompt_name: str
    usage: dict

    @property
    def releasable(self) -> bool:
        return self.model != STUB_MODEL


# ---------------------------------------------------------------- the facts a document may state


def age_at(dob: dt.date, on: dt.date) -> int:
    return on.year - dob.year - ((on.month, on.day) < (dob.month, dob.day))


def _claimant(case: Case):
    return next(m for m in case.policy.members if m.member_id == case.claim.member_id)


def _icu_days(case: Case) -> int:
    return sum(line.qty for line in case.claim.bill if line.category is BillCategory.ICU)


def tokens_for(case: Case, style: Style) -> dict[str, str]:
    """Every token the model may use, and the text it stands for."""
    claim, member = case.claim, _claimant(case)
    admitted, discharged = claim.admitted_at, claim.discharged_at
    values = {
        "patient": member.name,
        "age": str(age_at(member.dob, admitted.date())),  # bare, so "{age} years" and "{age}-year-old" both read
        "sex": member.gender.value.lower(),
        "admitted": layout.format_datetime(admitted, style),
        "discharged": layout.format_datetime(discharged, style),
        "stay": layout.format_stay(admitted, discharged),
        "diagnosis": claim.primary_dx.term,
        "hospital": claim.hospital.name,
        "doctor": claim.doctor.name,
    }
    if claim.procedures:
        values["procedure"] = ", ".join(p.term for p in claim.procedures)
    if claim.cause_note:
        values["cause"] = claim.cause_note
    if claim.secondary_dx:
        values["comorbidities"] = _join([d.term for d in claim.secondary_dx])
    if claim.room_category:
        values["room"] = claim.room_category
    if claim.treatment_system is not TreatmentSystem.ALLOPATHY:
        values["system"] = claim.treatment_system.value.replace("_", " and ").title()
    return values


def _join(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def admission_facts(case: Case, style: Style) -> str:
    """The context the model writes from. No amounts, no policy, no gold answer."""
    claim, member = case.claim, _claimant(case)
    lines = [
        f"- Patient: {member.name}, {age_at(member.dob, claim.admitted_at.date())} years, "
        f"{member.gender.value.lower()}",
        f"- Hospital: {claim.hospital.name}, {claim.hospital.city}"
        + (" (an AYUSH hospital)" if claim.hospital.ayush_hospital else ""),
        f"- Treating doctor: {claim.doctor.name}",
        f"- Admitted: {layout.format_datetime(claim.admitted_at, style)}",
        f"- Discharged: {layout.format_datetime(claim.discharged_at, style)}"
        f" (a stay of {layout.format_stay(claim.admitted_at, claim.discharged_at)})",
        f"- Final diagnosis: {claim.primary_dx.term}",
    ]
    if claim.procedures:
        lines.append("- Operation or procedure done: " + ", ".join(p.term for p in claim.procedures))
    else:
        lines.append("- No operation or procedure was done; this was medical treatment only")
    if claim.cause is Cause.ACCIDENT:
        lines.append(f"- This was an injury, caused by {claim.cause_note}")
    if claim.treatment_system is not TreatmentSystem.ALLOPATHY:
        system = claim.treatment_system.value.replace("_", " and ").title()
        lines.append(f"- Treated under the {system} system of medicine, not allopathy")
    if claim.secondary_dx:
        lines.append("- Long-standing conditions: " + _join([d.term for d in claim.secondary_dx]))
    if claim.room_category:
        lines.append(f"- Stayed in: {claim.room_category}")
    if icu := _icu_days(case):
        lines.append(f"- Part of the stay was in intensive care ({icu} of the days)")
    # By item code, not by category: a tray of attendant food is billed under
    # OTHER just as a course of therapy is, and the model should not be told the
    # patient had therapy because the bill carries a non-payable sundry.
    codes = {line.item_code for line in claim.bill if line.phase is Phase.INPATIENT}
    done = [name for code, name in (
        ("IN-LAB", "laboratory tests and imaging"),
        ("PH-DRUGS", "medicines given in the ward"),
        ("IM-IMPLANT", "an implant was used"),
        ("TH-THERAPY", "therapy sessions"),
    ) if code in codes]
    if done:
        lines.append("- Also on the record: " + _join(done))
    return "\n".join(lines)


def token_help(values: dict[str, str]) -> str:
    meanings = {
        "patient": "the patient's name",
        "age": 'the patient\'s age as a bare number, so write "{age} years old" or "a {age}-year-old"',
        "sex": "the patient's sex, in lower case",
        "admitted": "the date and time of admission",
        "discharged": "the date and time of discharge",
        "stay": 'how long the stay was, such as "3 days"; write "stayed for {stay}", not "a {stay} stay"',
        "diagnosis": "the final diagnosis",
        "procedure": "the operation or procedure done",
        "hospital": "the hospital's name",
        "doctor": "the treating doctor's name",
        "cause": 'how the injury happened, already beginning with "a" or "an", so write "following {cause}"',
        "comorbidities": "the long-standing conditions listed above",
        "room": "the kind of room the patient stayed in",
        "system": "the system of medicine used",
    }
    return "\n".join(f"- {{{name}}} — {meanings[name]}" for name in values)


# ---------------------------------------------------------------- checking and substituting prose


def check(field: str, text: str, values: dict[str, str]) -> str | None:
    """Why this field is unusable, or None if it is fine.

    The ban is on numbers the model made up, so before looking for them both the
    tokens and the facts they stand for are taken out of the text. A model that
    writes "a fall from a two-wheeler" instead of "{cause}" has written the case's
    own words, and "Type 2 diabetes mellitus" is a diagnosis, not a quantity.
    """
    if not text.strip():
        return f"{field} is empty"
    if len(text) > MAX_FIELD_CHARS:
        return f"{field} is longer than {MAX_FIELD_CHARS} characters"
    if "\n" in text.strip():
        return f"{field} has a line break in it; each field is one paragraph"
    unknown = sorted(set(TOKEN.findall(text)) - set(values))
    if unknown:
        return f"{field} uses tokens that do not exist: {', '.join('{' + name + '}' for name in unknown)}"
    bare = TOKEN.sub(" ", text)
    known = _numbers_in(" ".join(values.values()))
    if stray := next((run for run in DIGIT_RUN.findall(bare) if run not in known), None):
        return f"{field} has the number {stray!r}, which is nowhere in the record; use a token or write it qualitatively"
    if word := next((w for w in NUMBER_RE.findall(bare) if w.lower() not in known), None):
        return f"{field} spells out the number {word!r}; write it qualitatively"
    if word := BANNED_RE.search(bare):
        return f"{field} uses the banned word {word.group(0)!r}"
    return None


def _numbers_in(text: str) -> set[str]:
    """Every number the record itself contains, in figures or in words."""
    return set(DIGIT_RUN.findall(text)) | {word.lower() for word in NUMBER_RE.findall(text)}


def substitute(text: str, values: dict[str, str]) -> str:
    return TOKEN.sub(lambda match: values[match.group(1)], text)


def ask(client: Client, case: Case, style: Style, prompt_name: str, fields: tuple[str, ...],
        template: str) -> tuple[dict[str, str], dict]:
    """Prose for one document: asked for, checked, and substituted."""
    values = tokens_for(case, style)
    schema = {
        "type": "object",
        "properties": {name: {"type": "string"} for name in fields},
        "required": list(fields),
        "additionalProperties": False,
    }
    system = (PROMPTS / "system.md").read_text(encoding="utf-8")
    correction = ""
    for attempt in range(MAX_ATTEMPTS):
        prompt = Template(template).substitute(
            facts=admission_facts(case, style), tokens=token_help(values), correction=correction
        )
        content, entry = client.complete(system=system, prompt=prompt, schema=schema, name=prompt_name,
                                         seed=client.seed + attempt)
        faults = [fault for name in fields if (fault := check(name, str(content.get(name, "")), values))]
        if not faults:
            return {name: substitute(str(content[name]), values) for name in fields}, entry
        correction = (
            "YOUR LAST REPLY WAS THROWN AWAY. Fix all of this and write it again:\n"
            + "\n".join(f"- {fault}" for fault in faults)
        )
    raise ProseRejected(f"{case.case_id} {prompt_name}: " + "; ".join(faults))


# ---------------------------------------------------------------- discharge summary


def discharge_summary_html(case: Case, prose: dict[str, str], style: Style) -> str:
    claim, member = case.claim, _claimant(case)
    body = layout.letterhead(
        claim.hospital.name,
        f"{claim.hospital.city}, India",
        style,
        tagline="Department of Medical Records",
    )
    body += layout.tag("div", layout.esc(layout.heading("Discharge Summary", style)), class_="title")

    details = [
        ("Patient", layout.esc(member.name)),
        ("Age / Sex", layout.esc(f"{age_at(member.dob, claim.admitted_at.date())} years / "
                                 f"{member.gender.value.title()}")),
        ("Admitted", layout.esc(layout.format_datetime(claim.admitted_at, style))),
        ("Discharged", layout.esc(layout.format_datetime(claim.discharged_at, style))),
    ]
    if claim.room_category:
        details.append(("Accommodation", layout.esc(claim.room_category)))
    if icu := _icu_days(case):
        details.append(("Intensive care", layout.esc(f"{icu} day{'s' if icu != 1 else ''}")))
    if case.difficulty is not Difficulty.HARD:
        # A hard case leaves the agent to work the stay out from the two datetimes.
        details.append(("Length of stay", layout.esc(layout.format_stay(claim.admitted_at, claim.discharged_at))))
    if claim.treatment_system is not TreatmentSystem.ALLOPATHY:
        # The gate turns on whether the facility is a registered AYUSH hospital, so
        # the record says which it is either way; absence would prove nothing.
        details.append(("System of medicine",
                        layout.esc(claim.treatment_system.value.replace("_", " and ").title())))
        details.append(("Facility", layout.esc(
            "Registered AYUSH hospital" if claim.hospital.ayush_hospital
            else "General hospital; not registered as an AYUSH hospital")))
    details += [
        ("Treating doctor", layout.esc(claim.doctor.name)),
        ("Regn. No.", layout.esc(claim.doctor.registration_no)),
    ]
    body += layout.fields(details, columns=2)

    diagnosis = [("Final diagnosis", layout.esc(claim.primary_dx.term))]
    if claim.secondary_dx:
        diagnosis.append(("Other conditions", layout.esc(_join([d.term for d in claim.secondary_dx]))))
    if claim.procedures:
        procedures = "; ".join(
            f"{p.term}{f' ({p.units} sites)' if p.units > 1 else ''}" for p in claim.procedures
        )
        diagnosis.append(("Procedure performed", layout.esc(procedures)))
    if claim.cause is Cause.ACCIDENT:
        diagnosis.append(("Nature of injury", layout.esc(f"Sustained in {claim.cause_note}")))
    body += layout.section("Diagnosis", layout.fields(diagnosis), style)

    titles = {
        "presenting_complaint": "Presenting Complaints",
        "history": "History",
        "examination": "On Examination",
        "course_in_hospital": "Course in Hospital",
        "condition_at_discharge": "Condition at Discharge",
        "advice_on_discharge": "Advice on Discharge",
    }
    for name, title in titles.items():
        body += layout.section(title, layout.paragraphs(prose[name]), style)

    body += layout.tag(
        "div",
        layout.esc(f"{claim.doctor.name}") + "<br>"
        + layout.esc(f"Regn. No. {claim.doctor.registration_no}") + "<br>"
        + layout.esc(f"{claim.hospital.name}, {claim.hospital.city}"),
        class_="sign",
    )
    body += layout.tag(
        "div",
        layout.esc("This summary is issued on the patient's request and is based on the hospital record "
                   "of this admission. Kindly bring it at the time of follow-up."),
        class_="foot",
    )
    return layout.page(f"Discharge summary {case.case_id}", body, style)


def render_discharge_summary(case: Case, client: Client, out_dir: Path) -> Rendered:
    style = hospital_style(case)
    template = (PROMPTS / "discharge_summary.md").read_text(encoding="utf-8")
    prose, entry = ask(client, case, style, "discharge_summary", DISCHARGE_SUMMARY_FIELDS, template)
    path = layout.to_pdf(
        discharge_summary_html(case, prose, style),
        out_dir / "discharge_summary.pdf",
        created=case.claim.discharged_at.date(),  # the hospital hands it over on the day
    )
    return Rendered(Doc.DISCHARGE_SUMMARY, path, entry["model"], "discharge_summary", entry.get("usage", {}))


# ---------------------------------------------------------------- hospital bill


BILL_TITLES = ("Final Bill of Supply", "Inpatient Bill", "Hospital Bill Cum Receipt")


def _line_rows(lines, style: Style, *, dated: bool) -> list[list[str]]:
    rows = []
    for n, line in enumerate(lines, start=1):
        cells = [layout.esc(n)]
        if dated:
            cells.append(layout.esc(layout.format_date(line.date, style)))
        cells.append(layout.esc(line.description))
        if dated:
            cells.append(layout.esc(layout.format_money(line.amount, style)))
        else:
            cells += [
                layout.esc(layout.format_money(line.unit_price, style)),
                layout.esc(line.qty),
                layout.esc(layout.format_money(line.amount, style)),
            ]
        rows.append(cells)
    return rows


def hospital_bill_html(case: Case, style: Style) -> str:
    """Itemised, with nothing marked as payable or not: that is the agent's job."""
    claim, member = case.claim, _claimant(case)
    title = case_choice(case, BILL_TITLES, "bill title")
    body = layout.letterhead(claim.hospital.name, f"{claim.hospital.city}, India", style,
                             tagline="Billing Department")
    body += layout.tag("div", layout.esc(layout.heading(title, style)), class_="title")

    details = [
        ("Bill No.", layout.esc(claim.bill_no)),
        ("Bill date", layout.esc(layout.format_date(claim.discharged_at.date(), style))),
        ("Patient", layout.esc(member.name)),
        ("UHID", layout.esc(claim.uhid)),
        ("Age / Sex", layout.esc(f"{age_at(member.dob, claim.admitted_at.date())} years / "
                                 f"{member.gender.value.title()}")),
        ("Consultant", layout.esc(claim.doctor.name)),
        ("Admitted", layout.esc(layout.format_datetime(claim.admitted_at, style))),
        ("Discharged", layout.esc(layout.format_datetime(claim.discharged_at, style))),
    ]
    if claim.room_category:
        details.append(("Accommodation", layout.esc(claim.room_category)))
    body += layout.fields(details, columns=2)

    inpatient = [line for line in claim.bill if line.phase is Phase.INPATIENT]
    body += layout.section(
        "Charges during hospitalisation",
        layout.table(["Sl", "Particulars", "Rate", "Qty", "Amount"],
                     _line_rows(inpatient, style, dated=False), style, right=(2, 3, 4)),
        style,
    )
    totals = [("Total charges during hospitalisation",
               layout.format_money(sum(line.amount for line in inpatient), style))]

    for phase, heading_text in ((Phase.PRE, "Expenses before admission"),
                                (Phase.POST, "Expenses after discharge")):
        lines = [line for line in claim.bill if line.phase is phase]
        if not lines:
            continue
        body += layout.section(
            f"{heading_text} (receipts submitted with this bill)",
            layout.table(["Sl", "Date", "Particulars", "Amount"],
                         _line_rows(lines, style, dated=True), style, right=(3,)),
            style,
        )
        totals.append((f"Total, {heading_text.lower()}",
                       layout.format_money(sum(line.amount for line in lines), style)))

    grand = sum(line.amount for line in claim.bill)
    totals.append(("Grand total", layout.format_money(grand, style)))
    body += layout.tag(
        "table",
        "".join(layout.tag("tr", layout.tag("th", layout.esc(label))
                           + layout.tag("td", layout.esc(value), class_="num"))
                for label, value in totals),
        class_="fields one totals",
    )
    body += layout.tag("div", layout.esc(
        "Received the above sum. This bill is issued for the treatment of the patient named above and "
        "is subject to the hospital's tariff in force on the date of admission."), class_="foot")
    return layout.page(f"Hospital bill {case.case_id}", body, style)


def render_hospital_bill(case: Case, client: Client, out_dir: Path) -> Rendered:
    """No prose, so no model: every figure on a bill is the case's own."""
    style = hospital_style(case)
    path = layout.to_pdf(hospital_bill_html(case, style), out_dir / "hospital_bill.pdf",
                         created=case.claim.discharged_at.date())
    return Rendered(Doc.HOSPITAL_BILL, path, WITHOUT_A_MODEL, "hospital_bill", {})


# ---------------------------------------------------------------- policy certificate


def case_choice(case: Case, options: tuple[str, ...], *parts: str) -> str:
    """One of several wordings, fixed for this case."""
    return Rng(case.seed, "render", *parts).choice(options)


def certificate_rules(case: Case) -> list[tuple[str, str]]:
    """The product rules this certificate restates, and how it puts them.

    Exactly the rules the placement plan assigns to the certificate: in the easy
    and medium tiers that is every rule the answer needs, and in the hard tier the
    deciding one is left in the wording alone. The plan decides; this only writes.
    """
    terms, policy, claim = case.policy.terms, case.policy, case.claim
    on_certificate = [fact for fact, docs in case.placement.facts.items() if Doc.POLICY_CERTIFICATE in docs]
    written: list[tuple[str, str]] = []
    for fact in on_certificate:
        match fact:
            case Fact.INITIAL_WAIT:
                wait = terms.initial_wait
                text = f"{wait.duration.describe()} from the date of first cover"
                if wait.accident_exempt:
                    text += "; not applicable to hospitalisation following an accident"
                written.append(("Initial waiting period", text))
            case Fact.SPECIFIED_DISEASES:
                groups = [g for g in terms.specific_wait.groups if _rule_matches(g.match, claim)]
                if groups:
                    listed = "; ".join(f"{g.name} — {g.duration.describe()}" for g in groups)
                else:
                    waits = sorted({g.duration.describe() for g in terms.specific_wait.groups})
                    listed = f"{' or '.join(waits)}, for the conditions listed in the policy wording"
                if terms.specific_wait.accident_exempt:
                    listed += ". Not applicable where the hospitalisation follows an accident"
                written.append(("Waiting period, listed conditions", listed))
            case Fact.PED_WAIT:
                written.append(("Waiting period, declared pre-existing diseases",
                                f"{terms.ped_wait.describe()} of continuous cover from first inception"))
            case Fact.EXCLUSIONS:
                matched = [C.REGISTRY[e.clause_id].description for e in terms.exclusions
                           if _rule_matches(e.match, claim)]
                written.append(("Permanent exclusions",
                                "; ".join(matched) if matched
                                else "as listed in the policy wording"))
            case Fact.AYUSH_TERMS:
                if not terms.ayush.covered:
                    text = "not covered under this policy"
                else:
                    limit = ("up to the sum insured" if terms.ayush.cap is None
                             else f"up to {layout.format_money(int(cap_amount(terms.ayush.cap, policy.sum_insured)), _insurer_style(case))}")
                    where = " in an AYUSH hospital" if terms.ayush.requires_ayush_hospital else ""
                    text = f"inpatient AYUSH treatment covered {limit}{where}"
                written.append(("AYUSH treatment", text))
            case Fact.MIN_STAY:
                written.append(("Minimum hospitalisation",
                                f"{terms.min_stay_hours} consecutive hours, except for day care treatment"))
            case Fact.DAY_CARE_LIST:
                written.append(("Day care treatment",
                                "covered where the treatment is one of those listed in the policy wording"))
            case Fact.ROOM_ASSOCIATED:
                spared = ("pharmacy, consumables, implants, medical devices and diagnostics"
                          if not terms.room_associated else None)
                written.append(("Proportionate deduction",
                                "where the room rate exceeds the limit above, the other hospital charges are "
                                f"payable in the same proportion ({spared} excepted)" if spared else
                                "where the room rate exceeds the limit above, the other hospital charges are "
                                "payable in the same proportion"))
            case Fact.ICU_CAP:
                if terms.icu_cap:
                    written.append(("Intensive care limit", _per_day(case, terms.icu_cap)))
            case Fact.SUBLIMITS:
                matched = [s for s in terms.sublimits if _rule_matches(s.match, claim)]
                for sublimit in matched:
                    written.append((f"Limit, {sublimit.name.lower()}", _cap_text(case, sublimit.cap_per_unit)))
            case Fact.PRE_POST_WINDOWS:
                written.append(("Pre and post hospitalisation",
                                f"{terms.pre_hospitalisation_days} days before admission and "
                                f"{terms.post_hospitalisation_days} days after discharge"))
    return written


def _rule_matches(match, claim) -> bool:
    by_code = any(claim.primary_dx.icd10.startswith(prefix) for prefix in match.icd10_prefixes)
    return by_code or any(p.code in match.procedure_codes for p in claim.procedures)


def _cap_text(case: Case, cap) -> str:
    """The rupee figure this policy's limit comes to, and how it is arrived at.

    A certificate that said only "2% of the sum insured, at most Rs. 5,000" would
    leave the reader to work out which of the two bites.
    """
    style = _insurer_style(case)
    amount = layout.format_money(int(cap_amount(cap, case.policy.sum_insured)), style)
    if cap.bp_of_si is None:
        return amount
    share = f"{cap.bp_of_si // 100}% of the sum insured"
    how = f"{share}, subject to a maximum of {layout.format_money(cap.rupees, style)}" if cap.rupees else share
    return f"{amount} ({how})"


def _per_day(case: Case, cap) -> str:
    return f"{_cap_text(case, cap)} per day"


def _insurer_style(case: Case) -> Style:
    """One insurer's forms look the same across its cases, as real ones do."""
    return layout.style_for(case.product_id, issuer=Issuer.INSURER)


def policy_certificate_html(case: Case, profile, style: Style) -> str:
    policy = case.policy
    terms = policy.terms
    body = layout.letterhead(profile.insurer, profile.insurer_address, style,
                             tagline=f"{profile.product_name}  |  UIN {profile.uin}")
    body += layout.tag("div", layout.esc(layout.heading("Certificate of Insurance", style)), class_="title")

    body += layout.fields([
        ("Policy No.", layout.esc(policy.policy_number)),
        ("Product", layout.esc(profile.product_name)),
        ("Policy period", layout.esc(f"{layout.format_date(policy.period_start, style)} to "
                                     f"{layout.format_date(policy.period_end, style)}, both days inclusive")),
        ("Basis of cover", layout.esc("Floater" if len(policy.members) > 1 else "Individual")),
        ("Sum insured", layout.esc(layout.format_money(policy.sum_insured, style))),
        ("Cumulative bonus", layout.esc(layout.format_money(policy.cumulative_bonus, style)
                                        if policy.cumulative_bonus else "Nil")),
    ], columns=2)

    rows = []
    for member in policy.members:
        peds = ", ".join(ped.name for ped in member.declared_peds) or "None declared"
        rows.append([
            layout.esc(member.name),
            layout.esc(layout.format_date(member.dob, style)),
            layout.esc(member.relation.value.replace("_", "-").title()),
            layout.esc(layout.format_date(member.first_inception, style)),
            layout.esc(peds),
        ])
    body += layout.section(
        "Insured persons",
        layout.table(["Name", "Date of birth", "Relationship", "Covered without break since",
                      "Pre-existing diseases declared and accepted"], rows, style),
        style,
    )

    limits = []
    if terms.room_cap:
        limits.append(("Room rent limit", _per_day(case, terms.room_cap)))
    if policy.copay_bp:
        limits.append(("Co-payment", f"{policy.copay_bp // 100}% of every admissible claim"))
    if policy.deductible:
        limits.append(("Deductible", f"{layout.format_money(policy.deductible, style)} per claim"))
    limits += certificate_rules(case)
    body += layout.section("Limits and conditions applying to this policy", layout.fields(limits), style)

    body += layout.tag("div", layout.esc(
        "This certificate is to be read with the policy wording, which governs in case of any difference. "
        "Benefits are subject in every case to the terms, conditions and exclusions of the policy."),
        class_="foot")
    return layout.page(f"Policy certificate {case.case_id}", body, style)


def render_policy_certificate(case: Case, profile, client: Client, out_dir: Path) -> Rendered:
    style = _insurer_style(case)
    path = layout.to_pdf(policy_certificate_html(case, profile, style), out_dir / "policy_certificate.pdf",
                         created=case.policy.period_start)
    return Rendered(Doc.POLICY_CERTIFICATE, path, WITHOUT_A_MODEL, "policy_certificate", {})


# ---------------------------------------------------------------- claim form


def claim_form_html(case: Case, profile, style: Style) -> str:
    """The claimant's own account of the admission.

    Its figures are the claim form's, not the hospital's: where the two disagree,
    that disagreement is the case. What the form carries beyond the basics comes
    from the placement plan, so an easy case's form repeats the bill and a hard
    case's does not.
    """
    claim, policy, form = case.claim, case.policy, case.claim.claim_form
    member = _claimant(case)
    on_form = [fact for fact, docs in case.placement.facts.items() if Doc.CLAIM_FORM in docs]
    body = layout.letterhead(profile.insurer, profile.insurer_address, style,
                             tagline=f"{profile.product_name}  |  UIN {profile.uin}")
    body += layout.tag("div", layout.esc(layout.heading(
        "Claim Form — Reimbursement of Hospitalisation Expenses", style)), class_="title")

    body += layout.section("Part A — details of the insured", layout.fields([
        ("Policy No.", layout.esc(policy.policy_number)),
        ("Policy period", layout.esc(f"{layout.format_date(policy.period_start, style)} to "
                                     f"{layout.format_date(policy.period_end, style)}")),
        ("Name of the insured person", layout.esc(member.name)),
        ("Age / Sex", layout.esc(f"{age_at(member.dob, claim.admitted_at.date())} / "
                                 f"{member.gender.value.title()}")),
        ("Relationship to the policyholder", layout.esc(member.relation.value.replace("_", "-").title())),
        ("Claim No.", layout.esc(claim.claim_id)),
    ], columns=2), style)

    treatment = [
        ("Name of the hospital", layout.esc(claim.hospital.name)),
        ("City", layout.esc(claim.hospital.city)),
        ("Date and time of admission", layout.esc(layout.format_datetime(form.admitted_at, style))),
        ("Date and time of discharge", layout.esc(layout.format_datetime(form.discharged_at, style))),
        ("Treating doctor", layout.esc(claim.doctor.name)),
        ("Room category", layout.esc(claim.room_category or "Not applicable")),
    ]
    diagnosis = claim.primary_dx.term
    if case.placement.diagnosis_style is DiagnosisStyle.PLAIN:
        diagnosis += f" (ICD-10 {claim.primary_dx.icd10})"
    treatment.append(("Nature of illness or injury", layout.esc(diagnosis)))
    if claim.procedures:
        treatment.append(("Treatment or operation", layout.esc(", ".join(p.term for p in claim.procedures))))
    if claim.cause is Cause.ACCIDENT:
        treatment.append(("If an injury, how it occurred", layout.esc(f"Sustained in {claim.cause_note}")))
    if claim.treatment_system is not TreatmentSystem.ALLOPATHY:
        treatment.append(("System of medicine",
                          layout.esc(claim.treatment_system.value.replace("_", " and ").title())))
        treatment.append(("Type of facility", layout.esc(
            "Registered AYUSH hospital" if claim.hospital.ayush_hospital
            else "General hospital; not registered as an AYUSH hospital")))
    body += layout.section("Part B — details of the hospitalisation", layout.fields(treatment), style)

    if Fact.BILL_LINES in on_form:
        rows = [[layout.esc(n), layout.esc(line.description),
                 layout.esc(layout.format_date(line.date, style)),
                 layout.esc(layout.format_money(line.amount, style))]
                for n, line in enumerate(claim.bill, start=1)]
        body += layout.section(
            "Part C — expenses claimed",
            layout.table(["Sl", "Particulars", "Date", "Amount"], rows, style, right=(3,)),
            style,
        )
        rates = [(label, line) for label, category in (("Room rent per day", BillCategory.ROOM),
                                                      ("Intensive care per day", BillCategory.ICU))
                 for line in claim.bill if line.category is category]
        if rates:
            body += layout.fields([(label, layout.esc(layout.format_money(line.unit_price, style)))
                                   for label, line in rates])

    body += layout.fields([("Total amount claimed", layout.esc(layout.format_money(form.claimed_amount, style)))])
    body += layout.tag("div", layout.esc(
        "I declare that the particulars given above are true to the best of my knowledge and belief, and that "
        "the treatment described was taken by the insured person named above. I have not withheld any material "
        "information."), class_="foot")
    body += layout.tag("div", layout.esc(f"Signature of the insured person: {member.name}") + "<br>"
                       + layout.esc(f"Date: {layout.format_date(form.discharged_at.date(), style)}"), class_="sign")
    return layout.page(f"Claim form {case.case_id}", body, style)


def render_claim_form(case: Case, profile, client: Client, out_dir: Path) -> Rendered:
    style = _insurer_style(case)
    path = layout.to_pdf(claim_form_html(case, profile, style), out_dir / "claim_form.pdf",
                         created=case.claim.claim_form.discharged_at.date())
    return Rendered(Doc.CLAIM_FORM, path, WITHOUT_A_MODEL, "claim_form", {})


def hospital_style(case: Case) -> Style:
    """One hospital writes the same way in every case it appears in."""
    return layout.style_for(case.claim.hospital.name, case.claim.hospital.city, issuer=Issuer.HOSPITAL)


# ---------------------------------------------------------------- the bundle


def render_case(case: Case, profile, client: Client, out_dir: Path) -> list[Rendered]:
    """Every document this case's claimant submitted, plus the insurer's certificate.

    A document the case says was never submitted is not rendered: that gap is the
    case. The policy wording is shared per product and written once, by
    render.wording.
    """
    submitted = set(case.claim.documents_submitted)
    made = [render_policy_certificate(case, profile, client, out_dir)]
    if DocType.DISCHARGE_SUMMARY in submitted:
        made.append(render_discharge_summary(case, client, out_dir))
    if DocType.HOSPITAL_BILL in submitted:
        made.append(render_hospital_bill(case, client, out_dir))
    if DocType.CLAIM_FORM in submitted:
        made.append(render_claim_form(case, profile, client, out_dir))
    return made


def with_documents(case: Case, made: list[Rendered], dataset: Path) -> Case:
    """The case, knowing what was rendered from it and by what."""
    models = sorted({result.model for result in made if result.model != WITHOUT_A_MODEL})
    return case.model_copy(update={
        "documents": tuple(sorted(str(result.path.relative_to(dataset)) for result in made)),
        "provenance": case.provenance.model_copy(update={
            "render_model": ", ".join(models) or WITHOUT_A_MODEL,
            "rendered_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        }),
    })


def render_dataset(dataset: Path, case_ids: list[str], client: Client, profiles: dict) -> tuple[list, dict]:
    """Render every case's bundle. Returns what was made and what was discarded.

    A case whose prose cannot be got right in MAX_ATTEMPTS is discarded, its
    half-made documents removed, and the run carries on: one unusable reply out of
    five hundred is what the discard rate is for, not a reason to stop. A refusal
    from the provider is different and does stop the run, since every case after
    it would fail the same way.
    """
    made_by_case, discarded = [], {}
    for case_id in case_ids:
        folder = dataset / "cases" / case_id
        case = Case.model_validate_json((folder / "case.json").read_text(encoding="utf-8"))
        try:
            made = render_case(case, profiles[case.product_id], client, folder / "documents")
        except ProseRejected as rejected:
            discarded[case_id] = str(rejected)
            shutil.rmtree(folder / "documents", ignore_errors=True)
            continue
        updated = with_documents(case, made, dataset)
        (folder / "case.json").write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8")
        made_by_case.append((case_id, made, updated))
    return made_by_case, discarded


# ---------------------------------------------------------------- CLI


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, required=True, help="a folder under datasets/")
    parser.add_argument("--count", type=int, default=1, help="how many cases, from the start of index.jsonl")
    parser.add_argument("--case", action="append", default=[], help="case IDs to render instead")
    parser.add_argument("--stub", action="store_true", help="write the prose offline, without a model")
    args = parser.parse_args(argv)

    from render.llm import AccessDenied
    from render.wording import render_policy_wording
    from sampler.products import PROFILES

    rows = [json.loads(line) for line in (args.dataset / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    wanted = set(args.case) if args.case else {row["case_id"] for row in rows[: args.count]}
    client = stub_client() if args.stub else Client()

    for product_id in sorted({row["product_id"] for row in rows if row["case_id"] in wanted}):
        path = render_policy_wording(PROFILES[product_id], args.dataset / "wordings")
        print(f"{product_id}: {path.relative_to(args.dataset)}")

    ordered = [row["case_id"] for row in rows if row["case_id"] in wanted]
    try:
        made_by_case, discarded = render_dataset(args.dataset, ordered, client, PROFILES)
    except AccessDenied as refusal:
        print(f"\nthe provider refused the key, so nothing further was sent:\n  {refusal}\n"
              f"spent on this account so far: ${client.budget.spent():.4f}. "
              "Sort the account out and run this again; work already done is cached.")
        raise SystemExit(2) from None

    for case_id, made, updated in made_by_case:
        cost = sum(result.usage.get("cost_usd", 0) for result in made)
        print(f"{case_id}: {len(made)} documents  {updated.provenance.render_model}  ${cost:.5f}")
    if discarded:
        (args.dataset / "render_discards.json").write_text(
            json.dumps(discarded, indent=2) + "\n", encoding="utf-8")
        print(f"\ndiscarded {len(discarded)} of {len(ordered)} ({len(discarded) / len(ordered):.1%}):")
        for case_id, why in discarded.items():
            print(f"  {why}")
    if not args.stub:
        print(f"spent so far: ${client.budget.spent():.4f} of ${client.budget.cap_usd:.2f}")


if __name__ == "__main__":
    main()
