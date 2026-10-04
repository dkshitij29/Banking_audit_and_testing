"""The validation gate: it passes real documents and catches doctored ones.

Every check is exercised against a known-bad document, because a gate that never
closes is not a gate (CLAUDE.md: "Leakage is the most likely silent failure.
Test it explicitly.").
"""

import datetime as dt

import pytest

from engine import clauses as C
from render import documents
from render.llm import Budget, stub_client
from sampler.difficulty import Difficulty, Doc, Fact
from sampler.products import PROFILES
from sampler.sample import sample_case
from validate import checks
from validate.checks import Finding, validate

AROGYA = PROFILES["AROGYA_SANJEEVANI_GCI"]
SUMMARY = Doc.DISCHARGE_SUMMARY


@pytest.fixture(scope="module")
def rendered(tmp_path_factory):
    """Sampled cases, rendered offline, with the text of each document."""
    out = tmp_path_factory.mktemp("bundles")
    client = stub_client(cache_dir=out / "cache", budget=Budget(out / "spend.jsonl"))
    made = []
    for seed in range(30):
        case = sample_case(seed, AROGYA)
        result = documents.render_discharge_summary(case, client, out / case.case_id)
        made.append((case, {SUMMARY: result.path}, {SUMMARY: checks.text_of(result.path)}))
    return made


def a_case(rendered, **wanted):
    for case, paths, texts in rendered:
        if wanted.get("tier") in (None, case.difficulty) and (
            wanted.get("accident") is None or (case.claim.cause_note is not None) == wanted["accident"]
        ):
            return case, paths, texts
    pytest.skip(f"nothing sampled is {wanted}")


def checks_of(findings: list[Finding]) -> set[str]:
    return {finding.check for finding in findings}


# ---------------------------------------------------------------- real documents pass


def test_every_rendered_case_passes_every_check(rendered):
    for case, paths, _ in rendered:
        assert validate(case, paths) == [], case.case_id


def test_the_gate_reads_the_pdf_back_rather_than_trusting_the_renderer(rendered):
    case, paths, texts = rendered[0]
    assert case.claim.primary_dx.term in texts[SUMMARY]
    assert checks.text_of(paths[SUMMARY]) == texts[SUMMARY]


# ---------------------------------------------------------------- fact presence


def test_a_missing_fact_is_caught(rendered):
    case, _, texts = rendered[0]
    without = {SUMMARY: texts[SUMMARY].replace(case.claim.primary_dx.term, "something else")}
    findings = checks.fact_presence(case, without)
    assert [f.check for f in findings] == ["fact_presence"]
    assert Fact.DIAGNOSIS.value in findings[0].detail


def test_a_missing_admission_time_is_caught(rendered):
    case, _, texts = rendered[0]
    style = documents.hospital_style(case)
    from render import layout

    written = layout.format_datetime(case.claim.admitted_at, style)
    without = {SUMMARY: texts[SUMMARY].replace(written, "on the day of admission")}
    assert any(Fact.ADMISSION.value in f.detail for f in checks.fact_presence(case, without))


def test_a_fact_written_in_another_house_style_still_counts(rendered):
    """The gate accepts any spelling of a date, not the one this renderer chose."""
    case, _, texts = rendered[0]
    from dataclasses import replace as with_

    from render import layout

    style = documents.hospital_style(case)
    other = with_(style, date="long" if style.date != "long" else "dots", clock_24h=not style.clock_24h)
    swapped = texts[SUMMARY].replace(
        layout.format_datetime(case.claim.admitted_at, style),
        layout.format_datetime(case.claim.admitted_at, other),
    )
    assert not any(Fact.ADMISSION.value in f.detail for f in checks.fact_presence(case, {SUMMARY: swapped}))


def test_a_fact_the_extractor_broke_up_still_counts(rendered):
    case, _, texts = rendered[0]
    term = case.claim.primary_dx.term
    broken = {SUMMARY: texts[SUMMARY].replace(term, term.replace(" ", " \n "))}
    assert not any(Fact.DIAGNOSIS.value in f.detail for f in checks.fact_presence(case, broken))


def test_how_an_accident_happened_must_be_on_the_record(rendered):
    case, _, texts = a_case(rendered, accident=True)
    without = {SUMMARY: texts[SUMMARY].replace(case.claim.cause_note, "an injury")}
    assert any(Fact.CAUSE.value in f.detail for f in checks.fact_presence(case, without))


# ---------------------------------------------------------------- leakage


@pytest.mark.parametrize(
    "leak",
    [
        "Treatment falls under 4.2_specific_disease_waiting.",
        "Final decision: REJECT.",
        "The hospitalisation is not payable under the terms.",
        "The claim was rejected by the insurer.",
        "This expense stands rejected.",
        "The amount was disallowed at the time of settlement.",
    ],
)
def test_a_document_that_states_the_answer_is_caught(rendered, leak):
    case, _, texts = rendered[0]
    findings = checks.leakage(case, {SUMMARY: texts[SUMMARY] + " " + leak})
    assert findings and checks_of(findings) == {"leakage"}


@pytest.mark.parametrize("word", ["waiting period", "co-pay", "sub-limit", "day care", "pre-existing"])
def test_a_hospital_document_may_not_use_insurance_words(rendered, word):
    case, _, texts = rendered[0]
    findings = checks.leakage(case, {SUMMARY: texts[SUMMARY] + f" This was a {word} matter."})
    assert findings and checks_of(findings) == {"leakage"}


@pytest.mark.parametrize(
    "sentence",
    [
        "A waiting period of thirty-six months applies to pre-existing diseases.",
        "Each and every claim is subject to a co-payment of 5%.",
        "Expenses for cataract are subject to a sub-limit per eye.",
        "The expenses listed in Annexure A are not payable under this policy.",
        "Day care treatments are covered without the twenty-four hour requirement.",
    ],
)
def test_an_insurer_document_may_state_the_rules_it_is_made_of(sentence):
    """A policy wording is made of this language. Only a finding about this
    particular claim is leakage."""
    case = sample_case(0, AROGYA)
    assert checks.leakage(case, {Doc.POLICY_WORDING: sentence}) == []
    assert checks.leakage(case, {Doc.POLICY_CERTIFICATE: sentence}) == []


@pytest.mark.parametrize(
    "sentence",
    ["The claim is not payable.", "This claim stands rejected.", "Decision: REJECT.",
     "The amount disallowed is shown alongside.", "Refer 4.2_specific_disease_waiting."],
)
def test_an_insurer_document_still_may_not_state_the_outcome(sentence):
    case = sample_case(0, AROGYA)
    findings = checks.leakage(case, {Doc.POLICY_CERTIFICATE: sentence})
    assert findings and checks_of(findings) == {"leakage"}


def test_every_clause_id_is_looked_for(rendered):
    case, _, texts = rendered[0]
    for clause in C.REGISTRY:
        findings = checks.leakage(case, {SUMMARY: f"Refer {clause} of the wording."})
        assert any(clause in f.detail for f in findings), clause


# ---------------------------------------------------------------- fabricated dates and amounts


def test_a_date_the_case_does_not_have_is_caught(rendered):
    case, _, texts = rendered[0]
    findings = checks.no_new_dates(case, {SUMMARY: texts[SUMMARY] + " Review on 14/09/2029."})
    assert [f.check for f in findings] == ["no_fabrication"]
    assert "2029-09-14" in findings[0].detail


def test_every_date_the_case_does_have_is_accepted(rendered):
    case, _, texts = rendered[0]
    extra = " ".join(sorted(checks.written_dates(date))[0] for date in checks.allowed_dates(case))
    assert checks.no_new_dates(case, {SUMMARY: texts[SUMMARY] + " " + extra}) == []


def test_an_amount_the_case_does_not_have_is_caught(rendered):
    case, _, texts = rendered[0]
    findings = checks.no_new_amounts(case, {SUMMARY: texts[SUMMARY] + " Charges of ₹7,77,777 apply."})
    assert [f.check for f in findings] == ["no_fabrication"]
    assert "777777" in findings[0].detail


def test_the_bill_lines_and_their_sums_are_accepted(rendered):
    case, _, _ = rendered[0]
    amounts = [line.amount for line in case.claim.bill] + [sum(line.amount for line in case.claim.bill)]
    text = " ".join(f"₹{checks.layout.group_digits(amount, 'indian')}" for amount in amounts)
    assert checks.no_new_amounts(case, {Doc.HOSPITAL_BILL: text}) == []


def test_a_registration_or_policy_number_is_not_read_as_money(rendered):
    case, _, _ = rendered[0]
    text = f"Regn. No. {case.claim.doctor.registration_no} Policy No. {case.policy.policy_number}"
    assert checks.no_new_amounts(case, {SUMMARY: text}) == []


@pytest.mark.parametrize(
    "text, expected",
    [("₹1,05,000", {105_000}), ("Rs. 5,000", {5_000}), ("INR 1,05,000.00", {105_000}),
     ("1,05,000/-", {105_000}), ("105000", set()), ("Regn MMC/2010/21559", set())],
)
def test_money_is_only_read_where_it_is_marked_or_grouped(text, expected):
    assert checks._amounts_in(text) == expected


# ---------------------------------------------------------------- arithmetic


def test_a_bill_that_does_not_add_up_to_its_total_is_caught(rendered):
    case, _, _ = rendered[0]
    lines = " ".join(f"₹{checks.layout.group_digits(line.amount, 'indian')}" for line in case.claim.bill)
    wrong = lines + " Total ₹9,99,999"
    findings = checks.arithmetic(case, {Doc.HOSPITAL_BILL: wrong})
    assert [f.check for f in findings] == ["arithmetic"]


def test_a_bill_that_states_its_total_passes(rendered):
    case, _, _ = rendered[0]
    total = sum(line.amount for line in case.claim.bill)
    right = f"Total ₹{checks.layout.group_digits(total, 'indian')}"
    assert checks.arithmetic(case, {Doc.HOSPITAL_BILL: right}) == []


# ---------------------------------------------------------------- difficulty honesty


def test_a_hard_case_whose_certificate_restates_its_deciding_rule_is_caught(rendered):
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    assert case.placement.wording_only
    fact = case.placement.wording_only[0]
    wanted = checks.requirements(case, fact)
    if not wanted:
        pytest.skip(f"{fact} has no text to look for")
    leaked = {**texts, Doc.POLICY_CERTIFICATE: "Policy certificate. " + sorted(wanted[0])[0]}
    findings = checks.difficulty_honesty(case, leaked)
    assert any(f.check == "difficulty_honesty" and f.doc is Doc.POLICY_CERTIFICATE for f in findings)


def test_a_hospital_document_may_name_what_it_did(rendered):
    """The wording lists "Tonsillectomy" as a condition that waits. A discharge
    summary for a tonsillectomy says so, and that is the record doing its job, not
    the certificate restating the rule."""
    hard = [(case, texts) for case, _, texts in rendered
            if case.difficulty is Difficulty.HARD and case.claim.procedures]
    if not hard:
        pytest.skip("nothing sampled fits")
    for case, texts in hard:
        assert checks.difficulty_honesty(case, texts) == [], case.case_id


def test_an_easy_case_is_allowed_to_copy_everything(rendered):
    case, _, texts = a_case(rendered, tier=Difficulty.EASY)
    assert checks.difficulty_honesty(case, {**texts, Doc.CLAIM_FORM: texts[SUMMARY]}) == []


# ---------------------------------------------------------------- the whole gate


def test_one_doctored_document_is_enough_to_discard_a_case(rendered):
    case, paths, _ = rendered[0]
    assert validate(case, paths) == []
    from render import layout

    html = documents.discharge_summary_html(
        case, {f: "The claim was rejected as not payable." for f in documents.DISCHARGE_SUMMARY_FIELDS},
        documents.hospital_style(case),
    )
    bad = layout.to_pdf(html, paths[SUMMARY].parent / "bad.pdf", created=dt.date(2025, 1, 1))
    findings = validate(case, {SUMMARY: bad})
    assert "leakage" in checks_of(findings)


# ---------------------------------------------------------------- matching a value in a page


@pytest.mark.parametrize(
    "text, phrase, expected",
    [
        ("the period ends 11/07/2026, both days inclusive", "11/07/2026", True),
        ("24 consecutive hours, except for day care", "24 consecutive hours", True),
        ("Type 2 diabetes mellitus, Hypertension", "Type 2 diabetes mellitus", True),
        ("Rs. 1,700 only", "700", False),      # not part of a longer number
        ("Rs. 700 only", "700", True),
        ("total 2,00,000", "00,000", False),
        ("Rs. 5,000 per day", "Rs. 5,000", True),
        ("Senile nuclear\ncataract", "Senile nuclear cataract", True),  # the extractor broke it up
    ],
)
def test_a_value_counts_only_where_it_stands_on_its_own(text, phrase, expected):
    assert checks.holds(text, phrase) is expected


# ---------------------------------------------------------------- what a document may show


def test_a_certificate_may_show_a_date_of_birth(rendered):
    case, _, _ = rendered[0]
    member = case.policy.members[0]
    shown = sorted(checks.written_dates(member.dob))[0]
    assert checks.no_new_dates(case, {Doc.POLICY_CERTIFICATE: shown}) == []


def test_a_certificate_may_show_both_halves_of_a_limit(rendered):
    """"₹2,000 (2% of the sum insured, at most ₹5,000)" shows three figures, and
    all three are the product's."""
    case, _, _ = rendered[0]
    cap = case.policy.terms.room_cap
    assert cap and cap.rupees and cap.bp_of_si
    applies = int(checks.cap_amount(cap, case.policy.sum_insured))
    text = " ".join(f"₹{checks.layout.group_digits(amount, 'indian')}"
                    for amount in (applies, cap.rupees, case.policy.sum_insured * cap.bp_of_si // 10_000))
    assert checks.no_new_amounts(case, {Doc.POLICY_CERTIFICATE: text}) == []


def test_a_claim_form_may_state_the_dates_and_the_diagnosis(rendered):
    """Every claim form does. Only repeating the bill would collapse the tier."""
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    style = checks.layout.style_for(case.product_id, issuer=checks.Issuer.INSURER)
    form = " ".join([
        checks.layout.format_datetime(case.claim.admitted_at, style),
        checks.layout.format_datetime(case.claim.discharged_at, style),
        case.claim.primary_dx.term,
        checks.layout.format_date(case.policy.period_start, style),
    ])
    assert checks.difficulty_honesty(case, {**texts, Doc.CLAIM_FORM: form}) == []


def test_a_claim_form_that_repeats_the_bill_is_caught(rendered):
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    if Doc.CLAIM_FORM in case.placement.facts.get(Fact.BILL_LINES, ()):
        pytest.skip("this tier puts the bill on the claim form")
    style = checks.layout.style_for(case.product_id, issuer=checks.Issuer.INSURER)
    form = " ".join(checks.layout.format_money(line.amount, style) for line in case.claim.bill)
    findings = checks.difficulty_honesty(case, {**texts, Doc.CLAIM_FORM: form})
    assert any(f.doc is Doc.CLAIM_FORM and "bill" in f.detail for f in findings)


def test_a_wording_that_omits_a_rule_is_caught(rendered):
    """The gate holds the wording to the rules it is supposed to state, or a hard
    case would have nowhere to find its deciding rule."""
    case, _, texts = rendered[0]
    empty = {**texts, Doc.POLICY_WORDING: "This policy wording says nothing in particular."}
    findings = checks.fact_presence(case, empty)
    assert findings and all(f.doc is Doc.POLICY_WORDING for f in findings)


def test_a_wording_that_states_an_outcome_is_caught():
    case = sample_case(0, AROGYA)
    findings = checks.leakage(case, {Doc.POLICY_WORDING: "This claim stands rejected as not payable."})
    assert findings and checks_of(findings) == {"leakage"}


def test_a_bare_number_in_an_address_is_not_the_bill_showing_through(rendered):
    """The insurer's address ends "Mumbai 400 051". A bill line of ₹400 is not on
    the claim form because of that."""
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    form = "Sanchit House, Bandra Kurla Complex, Mumbai 400 051. Claim No. 90210 dated 400."
    assert checks.difficulty_honesty(case, {**texts, Doc.CLAIM_FORM: form}) == []
    assert checks.unambiguous({"400", "₹400", "1,05,000", "400.00"}) == {"₹400", "1,05,000", "400.00"}


def test_a_word_the_clinic_and_the_insurer_both_use(rendered):
    """"The pain had settled" is how a discharge summary is written. "The claim
    was settled" is the answer. The first must pass and the second must not."""
    case, _, _ = rendered[0]
    assert checks.leakage(case, {SUMMARY: "At discharge the pain had settled and the swelling had settled."}) == []
    assert checks.leakage(case, {SUMMARY: "The claim settled in full."})


def test_the_gate_rejects_no_word_the_model_was_not_warned_about():
    """A hospital document is held to render.documents.BANNED plus
    CONCLUSION_WORDS, and the prompt has to warn about every one of them, or prose
    is thrown away for breaking a rule nobody stated.

    The prompt bans "words and their relatives", so listing "co-payment" covers
    "copayment" and "covered" covers "coverage": a word counts as warned about if
    it contains a listed word, is contained by one, or shares its first five
    letters with one.
    """
    import re as regex
    from pathlib import Path

    from render.documents import BANNED

    def bare(word: str) -> str:
        return word.replace("-", "").replace(" ", "").strip().lower()

    prompt = Path(__file__).resolve().parent.parent / "render" / "prompts" / "system.md"
    quoted = [line.lstrip("> ") for line in prompt.read_text(encoding="utf-8").splitlines()
              if line.lstrip().startswith(">")]
    warned = {bare(word) for word in regex.split(r"[,\n]", " ".join(quoted)) if bare(word)}
    assert len(warned) > 20, "the prompt's banned list did not parse"

    for word in sorted(set(BANNED) | set(checks.CONCLUSION_WORDS)):
        plain = bare(word)
        assert any(plain in listed or listed in plain or plain[:5] == listed[:5] for listed in warned), word


def test_a_declared_disease_on_a_certificate_is_not_the_waiting_rule_restated(rendered):
    """One product's ninety-day group is called "Hypertension", and a certificate
    lists the pre-existing diseases its members declared. The two meeting is the
    member's history, not the rule."""
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    certificate = "Insured persons. Meera Sharma. Pre-existing diseases declared and accepted: Hypertension."
    assert checks.difficulty_honesty(case, {**texts, Doc.POLICY_CERTIFICATE: certificate}) == []
    assert checks.restatement_marks({"Hypertension", "90 days", "Cataract, per eye"}) == {"90 days"}
    assert "proportionate" in checks.restatement_marks({"proportionate", "Hernia of all types"})


def test_a_certificate_that_states_a_hidden_rule_s_period_is_still_caught(rendered):
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    periods = [spelling for fact in case.placement.wording_only
               for wanted in checks.requirements(case, fact)
               for spelling in checks.restatement_marks(wanted)]
    if not periods:
        pytest.skip("this case hides no rule with a period in it")
    leaked = {**texts, Doc.POLICY_CERTIFICATE: f"Policy certificate. Waiting period: {sorted(periods)[0]}."}
    assert any(f.doc is Doc.POLICY_CERTIFICATE for f in checks.difficulty_honesty(case, leaked))


def test_a_bill_dated_on_the_day_of_discharge_is_not_the_bill_on_the_claim_form(rendered):
    """Every document in the bundle carries the discharge date. A post-hospitalisation
    receipt dated that day says nothing about where the money was printed."""
    case, _, texts = a_case(rendered, tier=Difficulty.HARD)
    style = checks.layout.style_for(case.product_id, issuer=checks.Issuer.INSURER)
    form = f"Date of discharge: {checks.layout.format_date(case.claim.discharged_at.date(), style)}"
    assert checks.difficulty_honesty(case, {**texts, Doc.CLAIM_FORM: form}) == []
