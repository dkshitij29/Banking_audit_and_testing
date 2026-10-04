"""The policy wording: one per product, shared by every case written against it.

It is generated from the same ProductTerms the engine adjudicates with, so the
document and the answer key cannot drift apart. Nothing here is copied from the
insurer's PDF: the rules are the real product's, the words are this project's.

Its sections are numbered to match the clause registry (engine/clauses.py), so a
gold clause of 4.2_specific_disease_waiting points at section 4.2 of the document
the agent was given. Every rule the hard tier hides lives here and nowhere else.

The document is deliberately longer than any one case needs. A wording that held
only the rules a claim turns on would make retrieval trivial.
"""

from __future__ import annotations

from pathlib import Path

from engine import clauses as C
from engine.rules import cap_amount
from engine.schema import BillCategory, ProductTerms
from render import layout
from render.layout import Issuer, Style
from sampler.catalogue import CONDITIONS, ITEMS
from sampler.profiles import ProductProfile

PROCEDURE_NAMES = {
    condition.procedure.code: condition.procedure.clinical
    for condition in CONDITIONS.values() if condition.procedure
}

CATEGORY_NAMES = {
    BillCategory.ROOM: "room rent and boarding",
    BillCategory.ICU: "intensive care",
    BillCategory.NURSING: "nursing",
    BillCategory.SURGEON: "the surgeon's fees",
    BillCategory.ANAESTHETIST: "the anaesthetist's fees",
    BillCategory.CONSULTANT: "consultants' and specialists' fees",
    BillCategory.OT: "operation theatre charges",
    BillCategory.INVESTIGATION: "diagnostics and investigations",
    BillCategory.PHARMACY: "pharmacy and medicines",
    BillCategory.CONSUMABLE: "consumables",
    BillCategory.IMPLANT: "implants and medical devices",
    BillCategory.ADMIN: "administrative charges",
    BillCategory.OTHER: "other charges billed by the hospital",
}

STANDARD_EXCLUSION_TEXT = {
    C.INVESTIGATION: "admission only for investigation or evaluation, and diagnostic expenses not "
                     "related to the condition treated",
    C.REST_CURE: "admission primarily for bed rest, custodial care, convalescence or respite care",
    C.OBESITY: "surgical treatment of obesity that does not meet the conditions set out by the Authority",
    C.CHANGE_OF_GENDER: "treatment to change the characteristics of the body to those of the opposite sex",
    C.COSMETIC: "cosmetic or plastic surgery, or treatment to change appearance, unless it is "
                "reconstruction made necessary by an accident, a burn or cancer, or is medically "
                "necessary to remove a direct and immediate health risk",
    C.HAZARDOUS_SPORTS: "treatment made necessary by taking part, as a professional, in a hazardous or "
                        "adventure sport",
    C.BREACH_OF_LAW: "treatment arising from the insured person committing or attempting to commit a "
                     "breach of law with criminal intent",
    C.EXCLUDED_PROVIDERS: "treatment at a hospital or by a practitioner named on our excluded list, "
                          "except emergency care up to stabilisation",
    C.SUBSTANCE_ABUSE: "treatment for alcoholism, drug or substance abuse, and anything arising from it",
    C.HYDROS_SPAS: "treatment at a health hydro, nature cure clinic, spa or similar establishment",
    C.DIETARY_SUPPLEMENTS: "dietary supplements and substances that can be bought without a "
                           "prescription, including vitamins and minerals, unless a medical "
                           "practitioner has prescribed them as part of the treatment in hospital",
    C.REFRACTIVE_ERROR: "treatment to correct eyesight for a refractive error of less than 7.5 dioptres",
    C.UNPROVEN_TREATMENTS: "unproven treatments, services and supplies, being those that lack "
                           "significant medical documentation of their effectiveness",
    C.STERILITY_INFERTILITY: "treatment for sterility and infertility, including contraception, "
                             "sterilisation, assisted reproduction and its reversal",
    C.MATERNITY: "expenses traceable to childbirth, including caesarean section, and to miscarriage "
                 "other than one caused by an accident",
}


def _money(amount: int, style: Style) -> str:
    return layout.format_money(amount, style)


def _cap(cap, sum_insured: int, style: Style) -> str:
    """'2% of the sum insured, at most ₹5,000' — the wording's own way of putting a limit."""
    amount = _money(int(cap_amount(cap, sum_insured)), style)
    if cap.bp_of_si is None:
        return amount
    share = f"{cap.bp_of_si // 100}% of the sum insured"
    return f"{share}, at most {_money(cap.rupees, style)}" if cap.rupees else share


def _list(items: list[str]) -> str:
    return layout.tag("ul", "".join(layout.tag("li", layout.esc(item)) for item in items))


def _clause(number: str, title: str, text: str, style: Style) -> str:
    head = layout.tag("h3", layout.esc(f"{number} {title}"))
    return head + (text if text.lstrip().startswith("<") else layout.tag("p", layout.esc(text)))


def _example_sum_insured(profile: ProductProfile) -> int:
    """Limits written as a share of the sum insured are shown against one, so the
    document can state a rupee figure without pretending every policy has it."""
    return profile.sum_insured_options[0]


def wording_html(profile: ProductProfile, style: Style) -> str:
    terms: ProductTerms = profile.terms(_example_sum_insured(profile))
    sum_insured = _example_sum_insured(profile)
    body = layout.letterhead(profile.insurer, profile.insurer_address, style,
                             tagline=f"{profile.product_name}  |  UIN {profile.uin}")
    body += layout.tag("div", layout.esc(layout.heading("Policy Wording", style)), class_="title")
    body += layout.tag("p", layout.esc(
        f"This document sets out what is covered under the {profile.product_name}, what is not, and on "
        "what conditions. It is to be read with the certificate of insurance, which states the sum "
        "insured, the policy period and the persons insured. Where a limit below is given as a share of "
        f"the sum insured, the rupee figure shown is worked out on a sum insured of "
        f"{_money(sum_insured, style)}."))

    # ---------------------------------------------------------------- 1 and 2
    body += layout.section("1. Words used in this policy", "".join([
        _clause("1.1", "Accident", "a sudden, unforeseen and involuntary event caused by external, "
                "visible and violent means.", style),
        _clause("1.2", "Illness", "a sickness, disease or pathological condition that impairs normal "
                "functioning and needs medical treatment.", style),
        _clause("1.3", "Hospital", "an institution registered with the local authorities for in-patient "
                "care, with qualified nursing staff and a medical practitioner in charge round the "
                "clock, an operation theatre of its own, at least ten in-patient beds in towns of under "
                "ten lakh people and fifteen elsewhere, and daily records for every patient.", style),
        _clause("1.4", "AYUSH hospital", "a healthcare facility providing in-patient treatment under "
                "Ayurveda, Yoga and Naturopathy, Unani, Siddha or Homeopathy, run by the government, "
                "attached to a recognised AYUSH college, or registered with the local authorities under "
                "a qualified AYUSH practitioner, with at least five in-patient beds, a practitioner in "
                "charge round the clock, dedicated therapy sections or an equipped operation theatre "
                "where surgery is done, and daily records for every patient.", style),
        _clause("1.5", "Pre-existing disease", "a condition, ailment, injury or disease diagnosed by a "
                f"physician, or for which medical advice or treatment was received, within "
                f"{terms.ped_wait.describe()} before this policy first began.", style),
        _clause("1.6", "Room rent", "the amount the hospital charges for room and boarding, together "
                "with the charges it bills with them.", style),
        _clause("1.7", "Sum insured", "the amount shown in the certificate of insurance, which is the "
                "most we will pay for all claims for that insured person in a policy year, together "
                "with any cumulative bonus.", style),
    ]), style)

    day_care = sorted(PROCEDURE_NAMES.get(code, code) for code in terms.day_care_procedures)
    body += layout.section("2. Hospitalisation", "".join([
        _clause("2.1", "Minimum period of hospitalisation",
                f"We pay for hospitalisation only where the insured person was admitted for at least "
                f"{terms.min_stay_hours} consecutive hours. Treatment taken as an out-patient is not "
                "hospitalisation, however long the visit.", style),
        _clause("2.2", "Day care treatment",
                layout.tag("p", layout.esc(
                    f"The {terms.min_stay_hours}-hour requirement in 2.1 does not apply to day care "
                    "treatment: a medical treatment or surgical procedure carried out under general, "
                    f"regional or local anaesthesia in a hospital or day care centre in under "
                    f"{terms.min_stay_hours} hours because of technological advancement, which would "
                    "otherwise have needed a longer stay. Treatment normally taken as an out-patient is "
                    "not day care treatment. The following are treated as day care treatment under this "
                    "policy:")) + _list(day_care), style),
    ]), style)

    # ---------------------------------------------------------------- 3 what we cover
    covered = []
    if terms.room_cap:
        spared = [CATEGORY_NAMES[c] for c in BillCategory
                  if c not in terms.room_associated and c not in terms.room_rate_includes
                  and c not in (BillCategory.ROOM, BillCategory.ICU)]
        counted = [CATEGORY_NAMES[c] for c in terms.room_rate_includes]
        text = (f"We pay room rent, boarding{' and ' + _list_words(counted) if counted else ''} up to "
                f"{_cap(terms.room_cap, sum_insured, style)} for each day of the stay.")
        if counted:
            text += (f" Where the hospital bills {_list_words(counted)} separately, we treat those "
                     "charges as part of the daily room rent for this limit.")
        text += (" Where the room occupied is charged at more than this limit, we pay the other "
                 "expenses of the hospitalisation in the same proportion as the limit bears to the "
                 f"rate actually charged. This proportion is not applied to {_list_words(spared)}.")
        covered.append(_clause("3.1", "Room rent, boarding and nursing", text, style))
    if terms.icu_cap:
        covered.append(_clause("3.2", "Intensive care",
                               f"We pay intensive care unit and intensive cardiac care unit charges up to "
                               f"{_cap(terms.icu_cap, sum_insured, style)} for each day spent there. Where "
                               "the rate charged is higher, no proportionate deduction is made from the "
                               "other expenses of the hospitalisation.", style))
    for n, sublimit in enumerate(terms.sublimits, start=3):
        covered.append(_clause(f"3.{n}", f"Limit for {sublimit.name.split(',')[0].lower()}",
                               f"Expenses for the treatment of {sublimit.name.split(',')[0].lower()} are "
                               f"payable up to {_cap(sublimit.cap_per_unit, sum_insured, style)}, "
                               f"{sublimit.name.split(',')[-1].strip()} in one policy year.", style))
    ayush_number = 3 + len(terms.sublimits)
    if terms.ayush.covered:
        limit = ("up to the sum insured" if terms.ayush.cap is None
                 else f"up to {_cap(terms.ayush.cap, sum_insured, style)}")
        where = (" The treatment must be taken in an AYUSH hospital as defined in 1.4."
                 if terms.ayush.requires_ayush_hospital else "")
        covered.append(_clause(f"3.{ayush_number}", "AYUSH treatment",
                               f"We pay for in-patient treatment taken under Ayurveda, Yoga and "
                               f"Naturopathy, Unani, Siddha or Homeopathy {limit} in a policy year.{where}",
                               style))
    covered.append(_clause(f"3.{ayush_number + 1}", "Expenses before admission",
                           f"We pay medical expenses incurred for {terms.pre_hospitalisation_days} days "
                           f"before the date of admission, where they relate to the same condition and the "
                           "hospitalisation itself is payable.", style))
    covered.append(_clause(f"3.{ayush_number + 2}", "Expenses after discharge",
                           f"We pay medical expenses incurred for {terms.post_hospitalisation_days} days "
                           f"after the date of discharge, where they relate to the same condition and the "
                           "hospitalisation itself is payable.", style))
    body += layout.section("3. What we cover", "".join(covered), style)

    # ---------------------------------------------------------------- 4 waiting periods and exclusions
    groups = sorted(terms.specific_wait.groups, key=lambda g: (-g.duration.value, g.name))
    by_wait: dict[str, list[str]] = {}
    for group in groups:
        by_wait.setdefault(group.duration.describe(), []).append(group.name)
    listed = "".join(
        layout.tag("p", layout.esc(f"The following wait {wait} from the date this policy first began:"))
        + _list(sorted(names)) for wait, names in by_wait.items()
    )
    accident_note = (" This waiting period does not apply where the hospitalisation follows an accident."
                     if terms.specific_wait.accident_exempt else "")
    excluded = [
        _clause("4.1", "Pre-existing diseases",
                f"Expenses for the treatment of a pre-existing disease, and its direct complications, "
                f"are excluded until {terms.ped_wait.describe()} of continuous cover have passed since "
                "this policy first began. Cover afterwards is only for those pre-existing diseases "
                "declared in the proposal and accepted by us, as shown in the certificate of insurance.",
                style),
        _clause("4.2", "Conditions and treatments that wait",
                layout.tag("p", layout.esc(
                    "Expenses for the treatment of the conditions, surgeries and treatments listed below "
                    "are excluded until the period shown has passed." + accident_note
                    + " Where a condition is also a declared pre-existing disease, the longer of the two "
                      "waiting periods applies."))
                + listed, style),
        _clause("4.3", "The first days of cover",
                f"Expenses for the treatment of any illness within {terms.initial_wait.duration.describe()} "
                "of the date this policy first began are excluded."
                + (" This does not apply to hospitalisation following an accident."
                   if terms.initial_wait.accident_exempt else ""), style),
    ]
    modelled = {exclusion.clause_id for exclusion in terms.exclusions}
    modelled |= {rule.clause_id for rule in terms.line_exclusions}
    for clause_id in C.STANDARD_EXCLUSIONS:
        number = clause_id.split("_")[0]
        title = C.REGISTRY[clause_id].description
        excluded.append(_clause(number, title, "We do not pay for " + STANDARD_EXCLUSION_TEXT[clause_id]
                                + ".", style))
    body += layout.section("4. What we do not pay for", "".join(excluded), style)

    # ---------------------------------------------------------------- 5, 6, 7
    sharing = []
    if profile.deductible_options:
        sharing.append(_clause("5.1", "Deductible", "Where the certificate of insurance shows a "
                               "deductible, we pay only that part of an admissible claim which exceeds "
                               "it, for each and every claim.", style))
    if profile.mandatory_copay_bp or profile.copay_options_bp:
        share = (f"{profile.mandatory_copay_bp // 100}%" if profile.mandatory_copay_bp
                 else "the percentage shown in the certificate of insurance")
        sharing.append(_clause("5.2", "Co-payment",
                               f"Each and every claim under this policy is subject to a co-payment of "
                               f"{share} of the amount otherwise admissible, which the insured person "
                               "bears.", style))
    sharing.append(_clause("5.3", "Sum insured and cumulative bonus",
                           "The most we pay for all claims in a policy year is the sum insured shown in "
                           "the certificate of insurance, together with any cumulative bonus. The "
                           f"cumulative bonus increases the amount available by "
                           f"{profile.bonus_step_bp // 100}% of the sum insured for each claim-free "
                           f"policy year, up to {profile.bonus_max_bp // 100}%, and reduces at the same "
                           "rate in a year in which a claim is made.", style))
    body += layout.section("5. What the insured person bears", "".join(sharing), style)

    body += layout.section("6. General conditions", "".join([
        _clause("6.1", "Policy period",
                "We pay only where the insured person was admitted to hospital within the policy period "
                "shown in the certificate of insurance. Cover is not available during the grace period "
                "allowed for renewal.", style),
        _clause("6.2", "Territory", "Treatment must be taken in India, and claims are paid in Indian "
                "rupees.", style),
        _clause("6.3", "Reasonable and customary charges", "We pay expenses that are medically necessary "
                "and no more than the charges usual for the same treatment in the same locality.", style),
    ]), style)

    documents = {
        "CLAIM_FORM": "the claim form, completed and signed",
        "HOSPITAL_BILL": "the hospital's original bill, with the charges itemised",
        "DISCHARGE_SUMMARY": "the discharge summary issued by the hospital",
    }
    required = [text for name, text in documents.items() if name in {d.value for d in terms.required_documents}]
    body += layout.section("7. Making a claim", "".join([
        _clause("7.1", "Documents to be submitted",
                layout.tag("p", layout.esc("A claim for reimbursement must be supported by:"))
                + _list(required)
                + layout.tag("p", layout.esc(
                    "We may ask for the prescription advising admission, investigation reports, the "
                    "operation notes, proof of identity and bank details before settling a claim.")), style),
        _clause("7.2", "Time limits",
                "A claim for hospitalisation should reach us within thirty days of discharge, and a claim "
                "for expenses after discharge within fifteen days of the end of that treatment. We may "
                "condone a delay where the insured person shows it could not be helped.", style),
    ]), style)

    # ---------------------------------------------------------------- annexure
    non_payable = next((rule for rule in terms.line_exclusions if rule.clause_id == C.NON_PAYABLE), None)
    if non_payable:
        names = sorted(ITEMS.get(code, (code, None))[0] for code in non_payable.item_codes)
        body += layout.section(
            "Annexure A — items for which no separate payment is made",
            layout.tag("p", layout.esc(
                "The items below are not paid for as separate charges. Some are not covered at all; the "
                "rest are taken to form part of the room charge, the procedure charge or the cost of "
                "treatment, and are not billed to us on their own."))
            + _list(names),
            style,
        )
    return layout.page(f"Policy wording {profile.product_id}", body, style)


def _list_words(items: list[str]) -> str:
    if not items:
        return ""
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def wording_style(profile: ProductProfile) -> Style:
    return layout.style_for(profile.product_id, issuer=Issuer.INSURER)


def render_policy_wording(profile: ProductProfile, out_dir: Path) -> Path:
    """One document per product, shared by every case written against it."""
    style = wording_style(profile)
    return layout.to_pdf(wording_html(profile, style), out_dir / f"{profile.product_id}.pdf",
                         created=_issued_on(profile))


def _issued_on(profile: ProductProfile):
    import datetime as dt

    return profile.launched or dt.date(2025, 1, 1)
