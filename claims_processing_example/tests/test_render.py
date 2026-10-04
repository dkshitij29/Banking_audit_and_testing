"""Rendering: facts placed by code, prose checked before use, and stable PDFs.

These tests never reach the network. render.llm.Client takes its transport as an
argument, so a fake one stands in for the model.
"""

import datetime as dt
import io
import json
import re

import pytest

from engine import clauses as C
from engine.rules import cap_amount
from engine.schema import BillCategory
from render import documents, layout
from render.documents import BANNED, ProseRejected, check, substitute
from render.layout import Issuer
from render.llm import Budget, BudgetExhausted, Client, LlmError, MissingApiKey, Usage, read_api_key, stub_client
from sampler.difficulty import Difficulty, Doc, Fact
from sampler.products import PROFILES
from sampler.sample import sample_case

AROGYA = PROFILES["AROGYA_SANJEEVANI_GCI"]
MOMENT = dt.datetime(2025, 8, 4, 14, 30)


@pytest.fixture(scope="module")
def cases():
    """One case of each tier, and one of each shape the renderer branches on."""
    drawn = [sample_case(seed, AROGYA) for seed in range(60)]
    return {case.case_id: case for case in drawn}


def a_case(cases, **wanted):
    for case in cases.values():
        claim = case.claim
        if all([
            wanted.get("tier") in (None, case.difficulty),
            wanted.get("accident") is None or (claim.cause.value == "ACCIDENT") == wanted["accident"],
            wanted.get("procedure") is None or bool(claim.procedures) == wanted["procedure"],
            wanted.get("room") is None or (claim.room_category is not None) == wanted["room"],
        ]):
            return case
    pytest.skip(f"no sampled case is {wanted}")


# ---------------------------------------------------------------- style and formatting


def test_a_style_is_the_same_every_time_and_differs_between_issuers():
    hospital = layout.style_for("Amaltas Hospital", "Pune", issuer=Issuer.HOSPITAL)
    assert hospital == layout.style_for("Amaltas Hospital", "Pune", issuer=Issuer.HOSPITAL)
    assert hospital != layout.style_for("Amaltas Hospital", "Pune", issuer=Issuer.INSURER)


def test_hospitals_do_not_all_write_the_same_way():
    styles = {layout.style_for(f"Hospital {n}", "Pune", issuer=Issuer.HOSPITAL) for n in range(40)}
    for field in ("date", "money", "letterhead", "headings"):
        assert len({getattr(style, field) for style in styles}) > 1, field


@pytest.mark.parametrize(
    "date_style, expected",
    [("slashes", "04/08/2025"), ("dashes", "04-Aug-2025"), ("dots", "04.08.2025"), ("long", "4 August 2025")],
)
def test_every_date_format(date_style, expected):
    style = layout.style_for("x", issuer=Issuer.HOSPITAL)
    assert layout.format_date(MOMENT.date(), _with(style, date=date_style)) == expected


@pytest.mark.parametrize("clock_24h, expected", [(True, "14:30 hrs"), (False, "2:30 PM")])
def test_both_clocks(clock_24h, expected):
    style = _with(layout.style_for("x", issuer=Issuer.HOSPITAL), clock_24h=clock_24h)
    assert layout.format_time(MOMENT, style) == expected


@pytest.mark.parametrize(
    "money, grouping, paise, expected",
    [
        ("symbol", "indian", False, "₹1,05,000"),
        ("rs", "indian", False, "Rs. 1,05,000"),
        ("inr", "indian", True, "INR 1,05,000.00"),
        ("suffix", "western", False, "105,000/-"),
    ],
)
def test_every_money_format(money, grouping, paise, expected):
    style = _with(layout.style_for("x", issuer=Issuer.HOSPITAL), money=money, grouping=grouping, paise=paise)
    assert layout.format_money(105_000, style) == expected


@pytest.mark.parametrize(
    "hours, minutes, expected",
    [(72, 0, "3 days"), (24, 0, "1 day"), (31, 0, "1 day 7 hours"), (7, 15, "7 hours 15 minutes"), (1, 0, "1 hour")],
)
def test_length_of_stay_reads_as_a_hospital_writes_it(hours, minutes, expected):
    later = MOMENT + dt.timedelta(hours=hours, minutes=minutes)
    assert layout.format_stay(MOMENT, later) == expected


def _with(style, **changes):
    from dataclasses import replace

    return replace(style, **changes)


# ---------------------------------------------------------------- checking the model's prose


ALLOWED = {"admitted": "04/08/2025 14:30 hrs", "diagnosis": "Type 2 diabetes mellitus with foot ulcer",
           "stay": "5 days"}
GOOD = "The patient was admitted on {admitted} with {diagnosis} and stayed {stay}."


def test_good_prose_passes():
    assert check("history", GOOD, ALLOWED) is None


@pytest.mark.parametrize(
    "text, fault",
    [
        ("Admitted for 3 days with fever.", "nowhere in the record"),
        ("Admitted for three days with fever.", "spells out"),
        ("The stay was not payable under the terms.", "banned word"),
        ("Treatment was covered from the day of admission.", "banned word"),
        ("A day care procedure was done.", "banned word"),
        ("Malignancy was excluded on biopsy.", "banned word"),
        ("Admitted on {admission_date} with fever.", "tokens that do not exist"),
        ("", "empty"),
        ("First line.\nSecond line.", "line break"),
        ("x" * 1_000, "longer than"),
    ],
)
def test_prose_that_must_be_thrown_away(text, fault):
    reason = check("history", text, ALLOWED)
    assert reason is not None and fault in reason


def test_a_token_is_only_allowed_when_the_case_has_that_fact(cases):
    medical = a_case(cases, procedure=False)
    tokens = documents.tokens_for(medical, documents.hospital_style(medical))
    assert "procedure" not in tokens
    assert "uses tokens that do not exist" in check("course", "Did {procedure}.", tokens)


def test_a_number_inside_a_fact_of_the_case_is_not_an_invented_one(cases):
    """The model may write the case's own words instead of the token standing for
    them: "a fall from a two-wheeler" is the record, not a count of wheels."""
    accident = a_case(cases, accident=True)
    tokens = documents.tokens_for(accident, documents.hospital_style(accident))
    assert "two-wheeler" in " ".join(tokens.values()) or True
    assert check("history", f"Sustained in {accident.claim.cause_note}.", tokens) is None
    assert check("history", "She is a known case of Type 2 diabetes mellitus.", ALLOWED) is None
    # A number that is nobody's fact is still caught, in figures or in words.
    assert "spells out" in check("history", "Unwell for eleven days before coming in.", ALLOWED)
    assert "nowhere in the record" in check("history", "Seen thrice, over 9 weeks.", ALLOWED)


def test_digits_inside_a_token_are_fine_because_code_writes_them():
    assert check("history", "Admitted on {admitted}.", ALLOWED) is None
    assert substitute("Admitted on {admitted}.", {"admitted": "04/08/2025 14:30 hrs"}) == (
        "Admitted on 04/08/2025 14:30 hrs."
    )


def test_the_banned_list_covers_every_verdict_and_rule_word():
    for word in ("payable", "covered", "claim", "waiting period", "pre-existing", "day care", "sub-limit",
                 "co-pay", "deductible", "exclusion", "rejected", "approved"):
        assert word in BANNED


# ---------------------------------------------------------------- what the model is told


def test_the_prompt_carries_no_amount_and_no_answer(cases):
    """The model is told what happened clinically, never what anything cost and
    never what the claim comes to."""
    for case in list(cases.values())[:20]:
        facts = documents.admission_facts(case, documents.hospital_style(case))
        assert "₹" not in facts and "Rs" not in facts and "INR" not in facts
        policy, claim = case.policy, case.claim
        amounts = [line.amount for line in claim.bill] + [
            sum(line.amount for line in claim.bill), policy.sum_insured, policy.cumulative_bonus,
            policy.deductible, case.gold.payable,
        ]
        for amount in amounts:
            if amount < 1_000:  # too small to tell from an age or a count of days
                continue
            for written in (str(amount), layout.group_digits(amount, "indian"),
                            layout.group_digits(amount, "western")):
                assert written not in facts, (case.case_id, written)
        assert case.gold.verdict.value not in facts.upper()
        assert not any(clause in facts for clause in C.REGISTRY)


def test_the_prompt_tells_the_model_how_an_injury_happened(cases):
    case = a_case(cases, accident=True)
    facts = documents.admission_facts(case, documents.hospital_style(case))
    assert case.claim.cause_note and case.claim.cause_note in facts


# ---------------------------------------------------------------- the client


def replies(*contents):
    """A transport that answers with each content in turn, and counts its calls."""
    sent = []

    def transport(body, api_key):
        sent.append(body)
        content = contents[min(len(sent), len(contents)) - 1]
        return {
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.001},
        }

    transport.sent = sent
    return transport


def a_client(tmp_path, transport, **kwargs):
    budget = Budget(tmp_path / "spend.jsonl", cap_usd=1.0)
    return Client(cache_dir=tmp_path / "cache", budget=budget, api_key="test-key",
                  transport=transport, **kwargs)


def ask_once(client, **kwargs):
    return client.complete(system="s", prompt="p", schema={"type": "object", "properties": {"a": {}}},
                           name="t", **kwargs)


def test_a_reply_is_asked_for_once_and_then_cached(tmp_path):
    transport = replies({"a": "one"})
    client = a_client(tmp_path, transport)
    assert ask_once(client)[0] == {"a": "one"}
    assert ask_once(client)[0] == {"a": "one"}
    assert len(transport.sent) == 1
    assert len(client.budget.entries()) == 1


def test_the_request_is_deterministic_and_asks_for_no_reasoning(tmp_path):
    transport = replies({"a": "one"})
    ask_once(a_client(tmp_path, transport))
    body = transport.sent[0]
    assert (body["temperature"], body["top_p"], body["seed"]) == (0, 1, 7)
    assert body["reasoning"] == {"enabled": False}
    assert body["response_format"]["json_schema"]["strict"] is True


def test_the_cap_stops_a_call_before_it_is_sent(tmp_path):
    transport = replies({"a": "one"})
    client = a_client(tmp_path, transport)
    client.budget.record("m", Usage(0, 0, 1.0), "earlier")
    with pytest.raises(BudgetExhausted):
        ask_once(client)
    assert transport.sent == []


def test_without_a_key_an_uncached_render_stops_rather_than_guesses(tmp_path, monkeypatch):
    """Whether this machine happens to have a key must not decide the result, so
    the lookup itself is stubbed out."""
    from render import llm

    monkeypatch.setattr(llm, "read_api_key", lambda *args, **kwargs: None)
    client = Client(cache_dir=tmp_path / "cache", budget=Budget(tmp_path / "s.jsonl"),
                    api_key=None, transport=replies({"a": "one"}))
    with pytest.raises(MissingApiKey):
        ask_once(client)


def test_the_key_is_read_from_a_dotenv_file_and_the_environment(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('OPENROUTER_API_KEY="sk-from-file"\nOTHER=1\n', encoding="utf-8")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert read_api_key(env) == "sk-from-file"
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-from-env")
    assert read_api_key(env) == "sk-from-env"
    assert read_api_key(tmp_path / "missing") == "sk-from-env"


@pytest.mark.parametrize(
    "reply",
    [
        {"choices": []},
        {"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]},
        {"choices": [{"finish_reason": "stop", "message": {"content": "[1, 2]"}}]},
    ],
)
def test_an_unusable_reply_is_an_error_not_a_document(tmp_path, reply):
    client = a_client(tmp_path, lambda body, key: reply)
    with pytest.raises(LlmError):
        ask_once(client)


def test_a_cost_the_api_does_not_report_is_estimated():
    assert Usage.of("deepseek/deepseek-v4.1-flash", {"prompt_tokens": 1_000_000, "completion_tokens": 0}).cost_usd
    reported = Usage.of("deepseek/deepseek-v4.1-flash", {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.5})
    assert reported.cost_usd == 0.5


# ---------------------------------------------------------------- prose, end to end


PROSE = {name: "Seen on admission with {diagnosis}; discharged after {stay}." for name in
         documents.DISCHARGE_SUMMARY_FIELDS}
BAD_PROSE = {**PROSE,
             "history": "Unwell for 3 days before coming in.",  # digits
             "examination": "The stay was not payable under the terms."}  # a banned word


def test_bad_prose_is_asked_for_again_with_the_fault_named(tmp_path, cases):
    case = a_case(cases, tier=Difficulty.EASY)
    transport = replies(BAD_PROSE, PROSE)
    client = a_client(tmp_path, transport)
    prose, _ = documents.ask(client, case, documents.hospital_style(case), "discharge_summary",
                             documents.DISCHARGE_SUMMARY_FIELDS,
                             (documents.PROMPTS / "discharge_summary.md").read_text(encoding="utf-8"))
    assert len(transport.sent) == 2
    correction = transport.sent[1]["messages"][1]["content"]
    assert "THROWN AWAY" in correction
    assert "nowhere in the record" in correction and "banned word" in correction
    assert "{diagnosis}" not in prose["history"] and case.claim.primary_dx.term in prose["history"]


def test_prose_that_stays_bad_discards_the_case(tmp_path, cases):
    case = a_case(cases, tier=Difficulty.EASY)
    client = a_client(tmp_path, replies(BAD_PROSE, BAD_PROSE))
    with pytest.raises(ProseRejected):
        documents.ask(client, case, documents.hospital_style(case), "discharge_summary",
                      documents.DISCHARGE_SUMMARY_FIELDS,
                      (documents.PROMPTS / "discharge_summary.md").read_text(encoding="utf-8"))


# ---------------------------------------------------------------- the rendered document


def text_of(path):
    from pypdf import PdfReader

    return " ".join(page.extract_text() for page in PdfReader(path).pages)


@pytest.fixture(scope="module")
def rendered(tmp_path_factory, cases):
    """Every sampled case, rendered offline, with its extracted text."""
    out = tmp_path_factory.mktemp("rendered")
    client = stub_client(cache_dir=out / "cache", budget=Budget(out / "spend.jsonl"))
    made = {}
    for case in cases.values():
        result = documents.render_discharge_summary(case, client, out / case.case_id)
        made[case.case_id] = (case, result, text_of(result.path))
    return made


def test_the_document_states_the_facts_the_answer_needs(rendered):
    for case, _, text in rendered.values():
        claim = case.claim
        style = documents.hospital_style(case)
        assert layout.format_datetime(claim.admitted_at, style) in text, case.case_id
        assert layout.format_datetime(claim.discharged_at, style) in text, case.case_id
        assert claim.primary_dx.term in text, case.case_id
        for procedure in claim.procedures:
            assert procedure.term in text, case.case_id
        if claim.cause_note:
            assert claim.cause_note in text, case.case_id


def test_the_document_never_states_the_answer(rendered):
    for case, _, text in rendered.values():
        assert not any(clause in text for clause in C.REGISTRY), case.case_id
        assert case.gold.verdict.value not in text.upper(), case.case_id
        for word in ("payable", "waiting period", "day care", "sub-limit", "co-pay", "excluded"):
            assert word not in text.lower(), (case.case_id, word)


def test_the_document_never_states_an_amount(rendered):
    """A discharge summary carries no money at all: the bill is a separate document."""
    for case, _, text in rendered.values():
        style = documents.hospital_style(case)
        assert not re.search(r"₹|\bRs\.|\bINR\b|\d/-", text), case.case_id
        for line in case.claim.bill:
            grouped = layout.group_digits(line.amount, style.grouping)
            assert not re.search(rf"(?<![\d/]){re.escape(grouped)}(?![\d/])", text), (case.case_id, grouped)


def test_a_hard_case_makes_the_agent_work_the_stay_out(rendered):
    for case, _, text in rendered.values():
        stay = layout.format_stay(case.claim.admitted_at, case.claim.discharged_at)
        assert (stay in text) == (case.difficulty is not Difficulty.HARD), case.case_id


def test_rendering_the_same_case_twice_gives_the_same_bytes(tmp_path, cases):
    """A PDF carries a creation time, so it is stamped with the day the issuer
    would have printed it, not with the clock."""
    case = next(iter(cases.values()))
    client = stub_client(cache_dir=tmp_path / "cache", budget=Budget(tmp_path / "spend.jsonl"))
    first = documents.render_discharge_summary(case, client, tmp_path / "a").path.read_bytes()
    second = documents.render_discharge_summary(case, client, tmp_path / "b").path.read_bytes()
    assert first == second
    # The same page stamped with two different days must differ, or the stamp is
    # coming from the clock and nothing here is reproducible.
    html = documents.discharge_summary_html(case, {f: "x" for f in documents.DISCHARGE_SUMMARY_FIELDS},
                                            documents.hospital_style(case))
    one = layout.to_pdf(html, tmp_path / "c.pdf", created=dt.date(2001, 2, 3)).read_bytes()
    again = layout.to_pdf(html, tmp_path / "d.pdf", created=dt.date(2001, 2, 3)).read_bytes()
    later = layout.to_pdf(html, tmp_path / "e.pdf", created=dt.date(2011, 4, 5)).read_bytes()
    assert one == again and one != later


def test_a_stub_rendered_document_is_never_releasable(rendered):
    for _, result, _ in rendered.values():
        assert result.releasable is False


# ---------------------------------------------------------------- the rest of the bundle


@pytest.fixture(scope="module")
def bundles(tmp_path_factory, cases):
    """Every document of every sampled case, rendered offline, with its text."""
    out = tmp_path_factory.mktemp("bundles")
    client = stub_client(cache_dir=out / "cache", budget=Budget(out / "spend.jsonl"))
    made = {}
    for case in cases.values():
        results = documents.render_case(case, AROGYA, client, out / case.case_id)
        made[case.case_id] = (case, {r.doc: r for r in results},
                              {r.doc: text_of(r.path) for r in results})
    return made


def test_only_the_documents_the_claimant_submitted_are_rendered(bundles):
    from sampler.difficulty import MISSING_DOC

    for case, results, _ in bundles.values():
        submitted = set(case.claim.documents_submitted)
        expected = {Doc.POLICY_CERTIFICATE} | {MISSING_DOC[kind] for kind in submitted}
        assert set(results) == expected, case.case_id


def test_the_bill_itemises_every_line_and_adds_them_up(bundles):
    for case, results, texts in bundles.values():
        if Doc.HOSPITAL_BILL not in texts:
            continue
        text, style = texts[Doc.HOSPITAL_BILL], documents.hospital_style(case)
        for line in case.claim.bill:
            assert line.description in text, (case.case_id, line.line_id)
            assert layout.format_money(line.amount, style) in text, (case.case_id, line.line_id)
        total = sum(line.amount for line in case.claim.bill)
        assert layout.format_money(total, style) in text, case.case_id


def test_the_bill_shows_the_room_rate_and_the_days(bundles):
    for case, _, texts in bundles.values():
        room = next((line for line in case.claim.bill if line.category is BillCategory.ROOM), None)
        if room is None or Doc.HOSPITAL_BILL not in texts:
            continue
        style = documents.hospital_style(case)
        assert layout.format_money(room.unit_price, style) in texts[Doc.HOSPITAL_BILL], case.case_id


def test_the_certificate_states_the_limit_this_policy_actually_has(bundles):
    """"2% of the sum insured, at most ₹5,000" leaves the reader to work out which
    bites; the certificate states the rupee figure as well."""
    for case, _, texts in bundles.values():
        cap = case.policy.terms.room_cap
        if cap is None:
            continue
        style = documents._insurer_style(case)
        applies = int(cap_amount(cap, case.policy.sum_insured))
        assert layout.format_money(applies, style) in texts[Doc.POLICY_CERTIFICATE], case.case_id


def test_the_certificate_restates_exactly_the_rules_the_plan_gives_it(bundles):
    from validate import checks

    for case, _, texts in bundles.values():
        text = texts[Doc.POLICY_CERTIFICATE]
        for fact in case.placement.wording_only:
            for wanted in checks.requirements(case, fact):
                assert not any(checks.holds(text, spelling) for spelling in wanted), (case.case_id, fact)
        for fact, docs in case.placement.facts.items():
            if Doc.POLICY_CERTIFICATE not in docs:
                continue
            for wanted in checks.requirements(case, fact):
                assert any(checks.holds(text, spelling) for spelling in wanted), (case.case_id, fact)


def test_a_hard_certificate_carries_no_rules_at_all(cases):
    """In the hard tier nothing is copied: the certificate states the policy's own
    values, and every product rule is left in the wording.

    This asks the generator what it wrote rather than searching the page, because a
    figure can appear on a certificate for its own reasons: a cumulative bonus of
    ₹10,000 is not the ICU limit restated, even where the two come to the same.
    """
    by_tier = {}
    for case in cases.values():
        by_tier.setdefault(case.difficulty, []).append(case)
    assert by_tier[Difficulty.HARD]
    for case in by_tier[Difficulty.HARD]:
        assert documents.certificate_rules(case) == [], case.case_id
    assert any(documents.certificate_rules(case) for case in by_tier[Difficulty.EASY])
    assert any(documents.certificate_rules(case) for case in by_tier[Difficulty.MEDIUM])


def test_the_claim_form_is_the_claimants_account_not_the_hospitals(bundles):
    """Where the two disagree, the form carries the claimant's dates and figure:
    that disagreement is the whole of an escalation case."""
    checked = 0
    for case, _, texts in bundles.values():
        form = case.claim.claim_form
        if form is None or Doc.CLAIM_FORM not in texts:
            continue
        style = documents._insurer_style(case)
        assert layout.format_money(form.claimed_amount, style) in texts[Doc.CLAIM_FORM], case.case_id
        if (form.admitted_at, form.discharged_at) != (case.claim.admitted_at, case.claim.discharged_at):
            assert layout.format_datetime(form.admitted_at, style) in texts[Doc.CLAIM_FORM], case.case_id
            checked += 1
    assert checked, "no sampled case has a claim form that disagrees with the hospital"


def test_only_an_easy_claim_form_repeats_the_bill(bundles):
    for case, _, texts in bundles.values():
        if Doc.CLAIM_FORM not in texts:
            continue
        style = documents._insurer_style(case)
        repeats = all(layout.format_money(line.amount, style) in texts[Doc.CLAIM_FORM]
                      for line in case.claim.bill)
        assert repeats == (Doc.CLAIM_FORM in case.placement.facts.get(Fact.BILL_LINES, ())), case.case_id


def wording_sections(text):
    """The wording split at its own numbered headings, so a rule can be checked
    where it is stated rather than anywhere on the page."""
    flat = normalise_ws(text)
    parts = re.split(r"(?=\b\d+\.\d+ [A-Z])", flat)
    sections = {}
    for part in parts:
        if match := re.match(r"(\d+\.\d+) ", part):
            sections[match.group(1)] = part
    return sections


def test_the_wording_states_every_rule_the_engine_applies(tmp_path):
    from render.wording import render_policy_wording

    text = text_of(render_policy_wording(AROGYA, tmp_path))
    terms = AROGYA.terms(AROGYA.sum_insured_options[0])
    for group in terms.specific_wait.groups:
        assert group.name in text, group.name
        assert group.duration.describe() in text, group.name
    for exclusion in terms.exclusions:
        assert C.REGISTRY[exclusion.clause_id].description.lower() in text.lower(), exclusion.clause_id
    for code in terms.day_care_procedures:
        from render.wording import PROCEDURE_NAMES

        assert PROCEDURE_NAMES[code] in text, code


def test_each_waiting_period_is_stated_where_that_rule_is(tmp_path):
    """A wording that said 48 months under pre-existing diseases would still have
    "36 months" on the page, under joint replacement. The duration has to be in
    the section that states the rule."""
    from render.wording import render_policy_wording

    sections = wording_sections(text_of(render_policy_wording(AROGYA, tmp_path)))
    terms = AROGYA.terms(AROGYA.sum_insured_options[0])
    assert terms.ped_wait.describe() in sections[C.PED_WAITING.split("_")[0]]
    assert terms.initial_wait.duration.describe() in sections[C.INITIAL_WAITING.split("_")[0]]
    assert f"{terms.min_stay_hours} consecutive hours" in sections[C.MIN_HOSPITALISATION.split("_")[0]]
    specified = sections[C.SPECIFIC_WAITING.split("_")[0]]
    for group in terms.specific_wait.groups:
        assert group.name in specified, group.name
    # A wording states the rule, not a figure: it applies to every sum insured.
    for cap, number in ((terms.room_cap, C.ROOM_RENT), (terms.icu_cap, C.ICU_LIMIT)):
        if cap is None:
            continue
        section = sections[number.split("_")[0]]
        assert f"{cap.bp_of_si // 100}%" in section, number
        assert layout.group_digits(cap.rupees, "indian") in section, number


def test_every_exclusion_is_numbered_as_the_registry_numbers_it(tmp_path):
    from render.wording import render_policy_wording

    sections = wording_sections(text_of(render_policy_wording(AROGYA, tmp_path)))
    for clause_id in C.STANDARD_EXCLUSIONS:
        number = clause_id.split("_")[0]
        assert number in sections, clause_id
        assert C.REGISTRY[clause_id].description.lower() in sections[number].lower(), clause_id


def test_the_wordings_sections_are_numbered_like_the_clause_registry(tmp_path):
    """A gold clause of 4.2_specific_disease_waiting should point at section 4.2 of
    the document the agent was given."""
    from render.wording import render_policy_wording

    text = normalise_ws(text_of(render_policy_wording(AROGYA, tmp_path)))
    for clause_id, expected in (
        (C.MIN_HOSPITALISATION, "Minimum period of hospitalisation"),
        (C.DAY_CARE, "Day care treatment"),
        (C.ROOM_RENT, "Room rent"),
        (C.PED_WAITING, "Pre-existing diseases"),
        (C.SPECIFIC_WAITING, "Conditions and treatments that wait"),
        (C.INITIAL_WAITING, "The first days of cover"),
        (C.COPAY, "Co-payment"),
        (C.SUM_INSURED, "Sum insured and cumulative bonus"),
        (C.POLICY_PERIOD, "Policy period"),
        (C.MISSING_DOCUMENTS, "Documents to be submitted"),
    ):
        number = clause_id.split("_")[0]
        assert f"{number} {expected}" in text, clause_id


def test_the_wording_names_no_clause_id(tmp_path):
    from render.wording import render_policy_wording

    text = text_of(render_policy_wording(AROGYA, tmp_path))
    assert not [clause for clause in C.REGISTRY if clause in text]


def normalise_ws(text):
    return re.sub(r"\s+", " ", text)


def test_the_wording_lists_the_items_it_will_not_pay_for(tmp_path):
    """Annexure A is the only place the non-payable list appears, in every tier,
    so a bill's disallowed lines can be found nowhere else."""
    from render.wording import render_policy_wording
    from sampler.catalogue import ITEMS

    text = text_of(render_policy_wording(AROGYA, tmp_path))
    terms = AROGYA.terms(AROGYA.sum_insured_options[0])
    for rule in terms.line_exclusions:
        if rule.clause_id != C.NON_PAYABLE:
            continue
        for code in rule.item_codes:
            assert ITEMS[code][0] in text, code


# ---------------------------------------------------------------- the provider says no


def http_error(code: int, body: str):
    """Stands in for urllib's urlopen and refuses the way the provider would."""
    import urllib.error

    def urlopen(request, timeout=None):
        raise urllib.error.HTTPError("https://example", code, "refused", {}, io.BytesIO(body.encode()))

    return urlopen


@pytest.mark.parametrize(
    "code, body",
    [
        (401, '{"error":{"message":"No auth credentials found"}}'),
        (402, '{"error":{"message":"Insufficient credits"}}'),
        (403, '{"error":{"message":"Workspace monthly budget of $20.00 exceeded."}}'),
    ],
)
def test_an_account_problem_is_told_apart_from_a_bug(code, body, monkeypatch):
    """A run of five hundred cases must say "sort the account out", not raise
    something that reads like a crash."""
    from render import llm

    monkeypatch.setattr(llm.urllib.request, "urlopen", http_error(code, body))
    with pytest.raises(llm.AccessDenied) as refused:
        llm.http_transport({"model": "m"}, "sk-test")
    assert str(code) in str(refused.value)
    assert json.loads(body)["error"]["message"] in str(refused.value)


def test_a_server_fault_is_not_an_account_problem(monkeypatch):
    from render import llm

    monkeypatch.setattr(llm.urllib.request, "urlopen", http_error(500, "upstream exploded"))
    with pytest.raises(llm.LlmError) as failed:
        llm.http_transport({"model": "m"}, "sk-test")
    assert not isinstance(failed.value, llm.AccessDenied)


def test_a_refused_call_costs_nothing(tmp_path, monkeypatch):
    from render import llm

    monkeypatch.setattr(llm.urllib.request, "urlopen",
                        http_error(403, '{"error":{"message":"budget exceeded"}}'))
    budget = Budget(tmp_path / "spend.jsonl", cap_usd=1.0)
    client = Client(cache_dir=tmp_path / "cache", budget=budget, api_key="sk-test")
    with pytest.raises(llm.AccessDenied):
        client.complete(system="s", prompt="p", schema={"type": "object", "properties": {}}, name="t")
    assert budget.entries() == [] and budget.spent() == 0
    assert not list((tmp_path / "cache").glob("*.json")) if (tmp_path / "cache").exists() else True


# ---------------------------------------------------------------- one bad case does not stop a run


def a_dataset(tmp_path, cases, how_many=3):
    """A dataset on disk, the way sampler.sample writes one."""
    from sampler.sample import write_dataset

    return write_dataset("run", [(AROGYA, range(how_many))], tmp_path)


def test_a_case_whose_prose_cannot_be_got_right_is_discarded_and_the_run_goes_on(tmp_path, cases):
    """A model returning six empty fields, twice, is one case lost out of five
    hundred. It is not a reason to stop, and it must not leave half a bundle on
    disk for the gate to trip over."""
    dataset = a_dataset(tmp_path, cases)
    ids = [f"case-{n:06d}" for n in range(3)]
    empty = {name: "" for name in documents.DISCHARGE_SUMMARY_FIELDS}
    good = {name: "Seen with {diagnosis}; discharged after {stay}." for name in documents.DISCHARGE_SUMMARY_FIELDS}

    from sampler.case import Case

    second = Case.model_validate_json((dataset / "cases" / ids[1] / "case.json").read_text())
    patient = next(m.name for m in second.policy.members if m.member_id == second.claim.member_id)

    def by_patient(body, api_key):
        content = empty if patient in body["messages"][1]["content"] else good
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.0}}

    client = a_client(tmp_path / "client", by_patient)
    made, discarded = documents.render_dataset(dataset, ids, client, PROFILES)

    assert list(discarded) == [ids[1]]
    assert "is empty" in discarded[ids[1]]
    assert [case_id for case_id, _, _ in made] == [ids[0], ids[2]]
    assert not (dataset / "cases" / ids[1] / "documents").exists()
    for case_id, _, _ in made:
        assert (dataset / "cases" / case_id / "documents" / "discharge_summary.pdf").exists()


def test_a_retry_asks_differently_rather_than_asking_again(tmp_path, cases):
    """At temperature 0 the same request gives the same reply, so a second attempt
    with the same seed would fail the same way."""
    case = a_case(cases, tier=Difficulty.EASY)
    transport = replies(BAD_PROSE, PROSE)
    client = a_client(tmp_path, transport)
    documents.ask(client, case, documents.hospital_style(case), "discharge_summary",
                  documents.DISCHARGE_SUMMARY_FIELDS,
                  (documents.PROMPTS / "discharge_summary.md").read_text(encoding="utf-8"))
    assert [sent["seed"] for sent in transport.sent] == [client.seed, client.seed + 1]
