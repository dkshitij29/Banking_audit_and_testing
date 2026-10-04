"""Scenarios: what kind of case each seed is aimed at, and how to build one.

A scenario builds a policy and claim aimed at an outcome ("room above the cap",
"cataract inside the specified-disease wait"). The engine then decides the case.
If the decision is not what the scenario aimed for, the sampler draws again. The
gold answer is always the engine's, never the scenario's intent.

SCHEDULE fixes the mix: every 100 consecutive seeds hold exactly 35 APPROVE, 40
PARTIAL, 13 REJECT and 12 ESCALATE cases, and 34 easy, 33 medium and 33 hard. A
seed's scenario depends only on seed % 100, so adding seeds never changes an
existing case.

Scenarios pick conditions by what the product's terms say about them (listed,
excluded, on the day-care list), never by name, so they carry over unchanged to
real product profiles.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

from engine import clauses as C
from engine.rules import cap_amount
from engine.schema import (
    ALL_DOCUMENTS,
    BillCategory,
    BillLine,
    Cap,
    Cause,
    Claim,
    ClaimForm,
    DeclaredPed,
    Decision,
    Diagnosis,
    DocType,
    Doctor,
    Duration,
    DurationUnit,
    Gender,
    Hospital,
    Match,
    Member,
    Phase,
    Policy,
    Procedure,
    ProductTerms,
    Relation,
    TreatmentSystem,
    Verdict,
)
from sampler.catalogue import (
    CITIES,
    CONDITIONS,
    GIVEN_NAMES,
    HOSPITAL_KINDS,
    HOSPITAL_WORDS,
    ICU_RATES,
    ITEMS,
    PEDS,
    ROOM_CATEGORIES,
    SURNAMES,
    Condition,
)
from sampler.difficulty import Difficulty, DiagnosisStyle, diagnosis_style
from sampler.profiles import ProductProfile
from sampler.rng import Rng

ONE_YEAR = Duration(value=12, unit=DurationUnit.MONTHS)
BIG_TICKET = ("cabg", "knee_oa_tkr", "mi_ptca", "femur_neck_fracture")


class NotRealisable(Exception):
    """This draw cannot make the case the scenario wants; the sampler tries another."""


@dataclass(frozen=True)
class Item:
    """A bill line before it is numbered."""

    category: BillCategory
    item_code: str
    description: str
    unit_price: int
    qty: int = 1
    phase: Phase = Phase.INPATIENT
    on: dt.date | None = None


class Builder:
    """Accumulates one case. Scenario functions call its methods in order: pick a
    condition, admit, set the member's history, then add whatever the scenario
    needs; realise() turns it into a Policy and a Claim."""

    def __init__(self, rng: Rng, profile: ProductProfile, tier: Difficulty) -> None:
        self.rng, self.profile, self.tier = rng, profile, tier
        self.sum_insured = rng.choice(profile.sum_insured_options)
        self.copay_bp = profile.mandatory_copay_bp
        self.deductible = 0
        self.period_start = rng.date_between(dt.date(2025, 1, 1), dt.date(2025, 12, 31))
        self.period_end = ONE_YEAR.add_to(self.period_start) - dt.timedelta(days=1)
        self.condition: Condition | None = None
        self.system = TreatmentSystem.ALLOPATHY
        self.units = 1
        self.age = 0
        self.sex = Gender.FEMALE
        self.dob: dt.date | None = None
        self.admitted_at: dt.datetime | None = None
        self.discharged_at: dt.datetime | None = None
        self.first_inception: dt.date | None = None
        self.declared: list[str] = []
        self.comorbid: list[str] = []
        self.room: tuple[str, int] | None = None
        self.nursing: int | None = None
        self.icu: tuple[int, int] | None = None
        self.extra: list[Item] = []
        self.ayush_hospital = False
        self.documents: set[DocType] = set(ALL_DOCUMENTS)
        self.claimed_delta = 0
        self.form_shift = dt.timedelta(0)
        self._terms: dict[int, ProductTerms] = {}

    # ------------------------------------------------------------ product lookups

    @property
    def terms(self) -> ProductTerms:
        if self.sum_insured not in self._terms:
            self._terms[self.sum_insured] = self.profile.terms(self.sum_insured)
        return self._terms[self.sum_insured]

    @staticmethod
    def matches(condition: Condition, match: Match) -> bool:
        by_code = any(condition.icd10.startswith(prefix) for prefix in match.icd10_prefixes)
        by_procedure = condition.procedure is not None and condition.procedure.code in match.procedure_codes
        return by_code or by_procedure

    def listed(self, condition: Condition) -> bool:
        return any(self.matches(condition, group.match) for group in self.terms.specific_wait.groups)

    def excluded(self, condition: Condition) -> bool:
        return any(self.matches(condition, exclusion.match) for exclusion in self.terms.exclusions)

    def sublimited(self, condition: Condition) -> bool:
        return any(self.matches(condition, sublimit.match) for sublimit in self.terms.sublimits)

    def day_care_listed(self, condition: Condition) -> bool:
        return condition.procedure is not None and condition.procedure.code in self.terms.day_care_procedures

    def pool(
        self,
        *,
        cause: Cause | None = None,
        listed: bool | None = None,
        excluded: bool | None = False,
        sublimited: bool | None = False,
        day_care: bool | None = None,
        day_care_listed: bool | None = None,
        ped: bool | None = None,
        ayush: bool = False,
        icu: bool = False,
        short: bool = False,
        keys: Sequence[str] | None = None,
    ) -> list[str]:
        """Condition keys the product treats as asked. None means "either way"."""
        out = []
        for key, c in CONDITIONS.items():
            checks = (
                keys is None or key in keys,
                ayush == (TreatmentSystem.ALLOPATHY not in c.systems),
                cause is None or c.cause is cause,
                listed is None or self.listed(c) == listed,
                excluded is None or self.excluded(c) == excluded,
                sublimited is None or self.sublimited(c) == sublimited,
                day_care is None or c.day_care == day_care,
                day_care_listed is None or self.day_care_listed(c) == day_care_listed,
                ped is None or (c.ped is not None) == ped,
                not icu or c.icu_days[1] >= 1,
                not short or c.stay_days[0] <= 1,
            )
            if all(checks):
                out.append(key)
        return out

    def normal_pool(self, **filters) -> list[str]:
        """Ordinary inpatient conditions: allopathic, not excluded, no sub-limit."""
        return self.pool(day_care=False, **filters)

    # ------------------------------------------------------------ the claim

    def pick(self, keys: Sequence[str]) -> None:
        if not keys:
            raise NotRealisable("no condition fits")
        c = CONDITIONS[self.rng.choice(sorted(keys))]
        self.condition = c
        self.system = self.rng.choice(c.systems)
        self.units = self.rng.between(*c.procedure.units) if c.procedure else 1
        self.age = self.rng.between(*c.ages)
        self.sex = c.sex or self.rng.choice((Gender.FEMALE, Gender.MALE))

    def admit(self, stay: str = "normal", window: tuple[dt.date, dt.date] | None = None) -> None:
        """Admit on a date in `window` (default: the policy period) for a normal stay,
        a day-care stay, or a short stay under the minimum."""
        first, last = window or (self.period_start, self.period_end)
        day = self.rng.date_between(first, last)
        at = dt.datetime.combine(day, dt.time(self.rng.between(0, 23), self.rng.choice((0, 15, 30, 45))))
        minimum = self.terms.min_stay_hours
        if stay == "normal":
            days = self.rng.between(*self.condition.stay_days)
            hours = max(days * 24 + self.rng.between(-3, 8), minimum + 2)
        elif stay in ("day_care", "short"):
            hours = self.rng.between(4 if stay == "day_care" else 6, max(7, minimum - 3))
        else:
            raise ValueError(stay)
        self.admitted_at = at
        self.discharged_at = at + dt.timedelta(hours=hours, minutes=self.rng.choice((0, 15, 30, 45)))
        self.dob = day - dt.timedelta(days=self.age * 365 + self.rng.between(0, 364))

    def move_admission(self, day: dt.date) -> None:
        """Move the stay to start on `day`, keeping its length and time of day."""
        delta = dt.datetime.combine(day, self.admitted_at.time()) - self.admitted_at
        self.admitted_at += delta
        self.discharged_at += delta
        self.dob += dt.timedelta(days=delta.days)

    def stay_days(self) -> int:
        return max(1, math.ceil((self.discharged_at - self.admitted_at) / dt.timedelta(days=1)))

    # ------------------------------------------------------------ the member's history

    def _waits_over(self, inception: dt.date) -> tuple[dt.date, dt.date, dt.date]:
        terms = self.terms
        initial = terms.initial_wait.duration.add_to(inception)
        specific = max(
            (g.duration.add_to(inception) for g in terms.specific_wait.groups if self.matches(self.condition, g.match)),
            default=inception,
        )
        return initial, specific, terms.ped_wait.add_to(inception)

    def _anniversary(self, years_back: int) -> dt.date:
        year = self.period_start.year - years_back
        try:
            return self.period_start.replace(year=year)
        except ValueError:  # 29 February
            return self.period_start.replace(year=year, day=28)

    def history(self, kind: str) -> None:
        """Choose the member's first inception: "established" (every wait over by
        admission), "inside_specific" (initial wait over, the condition's
        specified-disease wait not), or "inside_ped" (only the PED wait running).

        A policy renewed every year since it began has its first inception on a
        policy anniversary, no earlier than the product's launch. Only when no
        anniversary fits is an arbitrary earlier date used: cover ported from
        another insurer carries its own start date.
        """
        admitted = self.admitted_at.date()
        launched = self.profile.launched or dt.date.min
        earliest = max(self.dob + dt.timedelta(days=91), self.period_start - dt.timedelta(days=9 * 365))
        if earliest > self.period_start:
            raise NotRealisable("member too young for this history")

        def fits(inception: dt.date) -> bool:
            initial, specific, ped = self._waits_over(inception)
            return {
                "established": max(initial, specific, ped) <= admitted,
                "inside_specific": initial <= admitted < specific,
                "inside_ped": max(initial, specific) <= admitted < ped,
            }[kind]

        anniversaries = [self._anniversary(k) for k in self.rng.shuffled(range(1, 10))]
        ported = (self.rng.date_between(earliest, self.period_start) for _ in range(300))
        for inception in [d for d in anniversaries if max(earliest, launched) <= d] + list(ported):
            if fits(inception):
                self.first_inception = inception
                if kind == "established":
                    self.declare_own_ped()
                return
        raise NotRealisable(f"no first inception gives a {kind} history")

    def declare_own_ped(self) -> None:
        """A complication of a known disease: the member declared that disease when
        the cover began. Established members are past the PED wait, so this only
        keeps the case realistic; it never changes the answer."""
        if self.condition.ped and self.condition.ped not in self.declared:
            self.declared.append(self.condition.ped)

    def new_policy_inside_initial_wait(self) -> None:
        self.first_inception = self.period_start
        over = self.terms.initial_wait.duration.add_to(self.period_start)
        if over <= self.period_start:
            raise NotRealisable("the product has no initial wait")
        self.move_admission(self.rng.date_between(self.period_start, min(over - dt.timedelta(days=1), self.period_end)))

    def declare_unrelated(self, count: int, show: bool) -> None:
        """Declare PEDs that do not relate to this admission's diagnosis."""
        code = self.condition.icd10
        unrelated = [key for key, (_, prefixes, _) in PEDS.items() if not any(code.startswith(p) for p in prefixes)]
        self.declared = self.rng.sample(unrelated, count)
        self.comorbid = list(self.declared) if show else []

    def maybe_distractor_peds(self) -> None:
        """Older members often have declared PEDs that have nothing to do with the claim."""
        if self.age >= 35 and self.rng.chance(30):
            own = list(self.declared)
            self.declare_unrelated(self.rng.between(1, 2), show=self.rng.chance(50))
            self.declared = own + [ped for ped in self.declared if ped not in own]

    # ------------------------------------------------------------ room and ICU

    def _per_day(self, cap: Cap) -> int:
        return math.floor(cap_amount(cap, self.sum_insured))

    def _nursing_per_day(self) -> tuple[int, int]:
        """(nursing rate, the part of it the product counts in the daily room rate)."""
        if self.nursing is None:
            self.nursing = self.rng.rupees(*self.condition.bill.nursing_per_day, 50)
        counted = BillCategory.NURSING in self.terms.room_rate_includes
        return self.nursing, self.nursing if counted else 0

    def room_within_cap(self) -> None:
        cap = self.terms.room_cap
        _, counted = self._nursing_per_day()
        limit = self._per_day(cap) - counted if cap else ROOM_CATEGORIES[-1][2]
        options = [(name, low, min(high, limit)) for name, low, high in ROOM_CATEGORIES if low <= limit]
        if not options:
            raise NotRealisable("no room category fits under the cap")
        name, low, high = self.rng.choice(options)
        self.room = (name, self.rng.rupees(low, high, 100))

    def room_above_cap(self) -> None:
        """A daily room rate above the cap. Where the product counts nursing in the
        rate, the room line alone is often within the cap and nursing tips it over."""
        if self.terms.room_cap is None:
            raise NotRealisable("the product has no room cap")
        _, counted = self._nursing_per_day()
        limit = self._per_day(self.terms.room_cap)
        if counted and self.rng.chance(40):
            rate = self.rng.rupees(limit - counted + 100, limit, 50)
        else:
            rate = self.rng.rupees(limit + 500, max(limit + 1_000, limit * 5 // 2), 100) - counted
        if rate < ROOM_CATEGORIES[0][1]:
            raise NotRealisable("no room category is that cheap")
        name = next((n for n, _, high in ROOM_CATEGORIES if rate <= high), ROOM_CATEGORIES[-1][0])
        self.room = (name, rate)

    def icu_stay(self, above_cap: bool) -> None:
        low_days, high_days = self.condition.icu_days
        if high_days < 1 or self.stay_days() < 2:
            raise NotRealisable("no ICU stay for this condition")
        days = self.rng.between(max(1, low_days), min(high_days, self.stay_days() - 1))
        cap = self.terms.icu_cap
        low, high = ICU_RATES
        if above_cap:
            if cap is None:
                raise NotRealisable("the product has no ICU cap")
            limit = self._per_day(cap)
            rate = self.rng.rupees(limit + 1_000, max(limit + 2_000, limit * 2), 500)
        else:
            limit = self._per_day(cap) if cap else high
            if limit < low:
                raise NotRealisable("ICU cap below any ICU rate")
            rate = self.rng.rupees(low, min(high, limit), 500)
        self.icu = (rate, days)

    # ------------------------------------------------------------ cost sharing

    def use_copay(self) -> None:
        if self.profile.copay_options_bp:
            self.copay_bp = max(self.copay_bp, self.rng.choice(self.profile.copay_options_bp))
        elif not self.copay_bp:
            raise NotRealisable("the product has no co-pay")

    def harden(self) -> None:
        """Hard cases stack cost sharing on top of the rule the scenario is about."""
        if self.tier is Difficulty.HARD and (self.profile.copay_options_bp or self.copay_bp):
            self.use_copay()

    def use_deductible(self, smallest: bool = False) -> None:
        options = self.profile.deductible_options
        if not options:
            raise NotRealisable("the product has no deductible")
        self.deductible = min(options) if smallest else self.rng.choice(options)

    # ------------------------------------------------------------ extra bill lines

    def add_excluded_item(self) -> None:
        rules = [rule for rule in self.terms.line_exclusions if rule.clause_id != C.NON_PAYABLE]
        if not rules:
            raise NotRealisable("the product excludes no bill items")
        code = self.rng.choice(self.rng.choice(rules).item_codes)
        description, category = ITEMS.get(code, (code, BillCategory.PHARMACY))
        self.extra.append(Item(category, code, description, self.rng.rupees(600, 4_000, 10)))

    def add_pre_post(self, outside: bool) -> None:
        """Bills from before admission and after discharge; with `outside`, at least
        one dated beyond its window."""
        pre_days, post_days = self.terms.pre_hospitalisation_days, self.terms.post_hospitalisation_days
        admitted, discharged = self.admitted_at.date(), self.discharged_at.date()
        late = self.rng.choice(("pre", "post")) if outside else None

        def before(out: bool) -> dt.date:
            back = self.rng.between(pre_days + 1, pre_days + 40) if out else self.rng.between(0, pre_days)
            return admitted - dt.timedelta(days=back)

        def after(out: bool) -> dt.date:
            ahead = self.rng.between(post_days + 1, post_days + 40) if out else self.rng.between(0, post_days)
            return discharged + dt.timedelta(days=ahead)

        self.extra += [
            Item(BillCategory.CONSULTANT, "PF-CONSULTANT", "Consultation before admission",
                 self.rng.rupees(500, 1_500, 50), phase=Phase.PRE, on=before(late == "pre")),
            Item(BillCategory.INVESTIGATION, "IN-LAB", "Tests before admission",
                 self.rng.rupees(800, 6_000, 10), phase=Phase.PRE, on=before(False)),
            Item(BillCategory.CONSULTANT, "PF-CONSULTANT", "Follow-up consultation",
                 self.rng.rupees(500, 1_500, 50), phase=Phase.POST, on=after(late == "post")),
            Item(BillCategory.PHARMACY, "PH-DRUGS", "Medicines after discharge",
                 self.rng.rupees(300, 4_000, 10), phase=Phase.POST, on=after(False)),
        ]

    # ------------------------------------------------------------ documents

    def misstate_amount(self) -> None:
        self.claimed_delta = self.rng.choice((-1, 1)) * self.rng.rupees(1_000, 25_000, 100)

    def shift_claim_form(self, delta: dt.timedelta) -> None:
        self.form_shift = delta

    # ------------------------------------------------------------ realise

    def _bill(self) -> list[Item]:
        spec, rng, terms = self.condition.bill, self.rng, self.terms
        days = self.stay_days()
        icu_days = self.icu[1] if self.icu else 0
        room_days = max(1, days - icu_days)
        items: list[Item] = []
        if self.room:
            name, rate = self.room
            items.append(Item(BillCategory.ROOM, "RM-ROOM", f"Room rent ({name})", rate, room_days))
        if self.icu:
            items.append(Item(BillCategory.ICU, "RM-ICU", "ICU charges (incl. nursing and monitoring)",
                              self.icu[0], icu_days))
        if self.room:  # ward nursing, for the days on the ward; ICU nursing is in the ICU charges
            nursing, _ = self._nursing_per_day()
            items.append(Item(BillCategory.NURSING, "NS-NURSING", "Nursing charges", nursing, room_days))
        if spec.surgeon:
            fee = rng.rupees(*spec.surgeon, 500) * self.units
            items.append(Item(BillCategory.SURGEON, "PF-SURGEON", "Surgeon's fee", fee))
            share = rng.between(*spec.anaesthetist_pct)
            items.append(Item(BillCategory.ANAESTHETIST, "PF-ANAESTHETIST", "Anaesthetist's fee", fee * share // 100 // 100 * 100))
            items.append(Item(BillCategory.OT, "OT-CHARGES", "Operation theatre charges", rng.rupees(*spec.ot, 500) * self.units))
        if spec.implant:
            description, low, high = spec.implant
            items.append(Item(BillCategory.IMPLANT, "IM-IMPLANT", description, rng.rupees(low, high, 500), self.units))
        if spec.therapy_per_day:
            description, low, high = spec.therapy_per_day
            items.append(Item(BillCategory.OTHER, "TH-THERAPY", description, rng.rupees(low, high, 50), days))
        items.append(Item(BillCategory.CONSULTANT, "PF-CONSULTANT", "Consultant visits",
                          rng.rupees(*spec.consultant_per_day, 50), days))
        low, high = spec.pharmacy_per_day
        items.append(Item(BillCategory.PHARMACY, "PH-DRUGS", "Pharmacy and medicines", rng.between(low * days, high * days)))
        items.append(Item(BillCategory.INVESTIGATION, "IN-LAB", "Laboratory and imaging", rng.between(*spec.investigations)))
        items.append(Item(BillCategory.CONSUMABLE, "CN-MEDICAL", "Medical consumables (syringes, IV sets)",
                          rng.between(500, 3_000)))
        non_payables = next(rule for rule in terms.line_exclusions if rule.clause_id == C.NON_PAYABLE)
        for code in rng.sample(non_payables.item_codes, rng.between(1, 3)):
            description, category = ITEMS.get(code, (code, BillCategory.CONSUMABLE))
            items.append(Item(category, code, description, rng.rupees(100, 1_500, 10)))
        return items + self.extra

    def _family(self, rng: Rng) -> tuple[list[Member], str]:
        surname = rng.choice(SURNAMES)
        admitted = self.admitted_at.date()

        def person(age: int, sex: Gender, relation: Relation, peds: list[str]) -> dict:
            dob = admitted - dt.timedelta(days=age * 365 + rng.between(0, 364))
            return {"dob": dob, "sex": sex, "relation": relation, "peds": peds}

        claimant_relation = (
            Relation.CHILD if self.age < 18 else
            rng.choice((Relation.SELF, Relation.PARENT)) if self.age >= 62 else
            rng.choice((Relation.SELF, Relation.SELF, Relation.SPOUSE))
        )
        people = [{"dob": self.dob, "sex": self.sex, "relation": claimant_relation, "peds": self.declared, "claimant": True}]
        other = Gender.MALE if self.sex is Gender.FEMALE else Gender.FEMALE
        if claimant_relation is Relation.CHILD:
            people.append(person(self.age + rng.between(25, 35), rng.choice(tuple(Gender)[:2]), Relation.SELF, []))
        elif claimant_relation is Relation.PARENT:
            people.append(person(max(18, self.age - rng.between(25, 35)), rng.choice(tuple(Gender)[:2]), Relation.SELF, []))
        elif claimant_relation is Relation.SPOUSE:
            people.append(person(max(18, self.age + rng.between(-5, 5)), other, Relation.SELF, []))
        elif rng.chance(60):
            people.append(person(max(18, self.age + rng.between(-5, 5)), other, Relation.SPOUSE, []))
        proposer_dob = next((p["dob"] for p in people if p["relation"] is Relation.SELF), self.dob)
        if (admitted - proposer_dob).days // 365 >= 28 and claimant_relation is not Relation.PARENT:
            for _ in range(rng.between(0, 2)):
                people.append(person(rng.between(1, 20), rng.choice(tuple(Gender)[:2]), Relation.CHILD, []))
        for p in people:
            age = (admitted - p["dob"]).days // 365
            if not p.get("claimant") and age >= 40 and rng.chance(20):
                p["peds"] = rng.sample(sorted(PEDS), rng.between(1, 2))

        order = {Relation.SELF: 0, Relation.SPOUSE: 1, Relation.CHILD: 2, Relation.PARENT: 3, Relation.PARENT_IN_LAW: 4}
        people.sort(key=lambda p: (order[p["relation"]], p["dob"]))
        members, claimant_id = [], ""
        for n, p in enumerate(people, start=1):
            inception = self.first_inception if p.get("claimant") else max(
                self.first_inception, p["dob"] + dt.timedelta(days=91))
            if inception > self.period_start:
                continue  # born too recently to be on this policy
            member_id = f"M{n}"
            members.append(Member(
                member_id=member_id,
                name=f"{rng.choice(GIVEN_NAMES[p['sex']])} {surname}",
                dob=p["dob"],
                gender=p["sex"],
                relation=p["relation"],
                first_inception=inception,
                declared_peds=tuple(DeclaredPed(name=PEDS[k][0], icd10_prefixes=PEDS[k][1]) for k in p["peds"]),
            ))
            if p.get("claimant"):
                claimant_id = member_id
        return members, claimant_id

    def realise(self) -> tuple[Policy, Claim]:
        rng, c = self.rng.fork("realise"), self.condition
        members, claimant_id = self._family(rng)

        years = (self.period_start - self.first_inception).days // 365
        bonus_bp = min(rng.between(0, years) * self.profile.bonus_step_bp, self.profile.bonus_max_bp) if years else 0
        policy = Policy(
            policy_number=f"{self.profile.policy_prefix}/{self.period_start.year}/{rng.between(1_000_000, 9_999_999)}",
            period_start=self.period_start,
            period_end=self.period_end,
            sum_insured=self.sum_insured,
            cumulative_bonus=self.sum_insured * bonus_bp // 10_000,
            deductible=self.deductible,
            copay_bp=self.copay_bp,
            members=tuple(members),
            terms=self.terms,
        )

        bill = tuple(
            BillLine(
                line_id=f"L{n:02d}",
                date=item.on or self.admitted_at.date(),
                category=item.category,
                item_code=item.item_code,
                description=item.description,
                unit_price=item.unit_price,
                qty=item.qty,
                amount=item.unit_price * item.qty,
                phase=item.phase,
            )
            for n, item in enumerate(self._bill(), start=1)
        )
        total = sum(line.amount for line in bill)
        claim_form = None
        if DocType.CLAIM_FORM in self.documents:
            claimed = total + self.claimed_delta
            claim_form = ClaimForm(
                claimed_amount=claimed if claimed >= 0 else total - self.claimed_delta,
                admitted_at=self.admitted_at + self.form_shift,
                discharged_at=self.discharged_at + self.form_shift,
            )

        clinical = diagnosis_style(self.tier) is DiagnosisStyle.CLINICAL
        city, council = rng.choice(CITIES)
        if self.system is not TreatmentSystem.ALLOPATHY and self.ayush_hospital:
            kind = "Ayurveda Hospital" if self.system is TreatmentSystem.AYURVEDA else "AYUSH Hospital"
            hospital_name = f"{rng.choice(HOSPITAL_WORDS)} {kind}"
        else:
            hospital_name = f"{rng.choice(HOSPITAL_WORDS)} {rng.choice(HOSPITAL_KINDS)}"
        doctor_sex = rng.choice((Gender.FEMALE, Gender.MALE))
        claim = Claim(
            claim_id=f"CL{self.admitted_at.year}{rng.between(10_000_000, 99_999_999)}",
            member_id=claimant_id,
            cause=c.cause,
            cause_note=rng.choice(c.mechanisms) if c.cause is Cause.ACCIDENT else None,
            treatment_system=self.system,
            primary_dx=Diagnosis(icd10=c.icd10, term=rng.choice(c.clinical) if clinical else c.plain),
            secondary_dx=tuple(Diagnosis(icd10=PEDS[k][2], term=PEDS[k][0]) for k in self.comorbid),
            procedures=(
                (Procedure(code=c.procedure.code, term=c.procedure.clinical if clinical else c.procedure.plain,
                           units=self.units),)
                if c.procedure else ()
            ),
            admitted_at=self.admitted_at,
            discharged_at=self.discharged_at,
            room_category=self.room[0] if self.room else None,
            uhid=f"UH{self.admitted_at.year}{rng.between(100_000, 999_999)}",
            bill_no=f"IP/{self.admitted_at.year}/{rng.between(10_000, 99_999)}",
            hospital=Hospital(name=hospital_name, city=city, ayush_hospital=self.ayush_hospital),
            doctor=Doctor(
                name=f"Dr {rng.choice(GIVEN_NAMES[doctor_sex])} {rng.choice(SURNAMES)}",
                registration_no=f"{council}/{rng.between(1995, 2022)}/{rng.between(10_000, 99_999)}",
            ),
            bill=bill,
            documents_submitted=tuple(sorted(self.documents)),
            claim_form=claim_form,
        )
        return policy, claim


# ---------------------------------------------------------------- scenario building blocks


def payable(b: Builder, pool: list[str], *, room: str = "within", distractors: bool = True) -> None:
    """An ordinary, established member's inpatient claim with the room at or under the cap."""
    b.pick(pool)
    b.admit("normal")
    b.history("established")
    b.room_above_cap() if room == "above" else b.room_within_cap()
    if distractors:
        b.maybe_distractor_peds()


def day_care(b: Builder, pool: list[str]) -> None:
    b.pick(pool)
    b.admit("day_care")
    b.history("established")
    b.maybe_distractor_peds()


def sublimited_claim(b: Builder) -> None:
    b.pick(b.pool(sublimited=True))
    if b.condition.day_care and b.day_care_listed(b.condition):
        day_care(b, [b.condition.key])
    else:
        payable(b, [b.condition.key])


# ---------------------------------------------------------------- scenarios


def clean(b: Builder) -> None:
    payable(b, b.normal_pool())


def copay_only(b: Builder) -> None:
    payable(b, b.normal_pool())
    b.use_copay()


def deductible_only(b: Builder) -> None:
    payable(b, b.normal_pool())
    b.use_deductible()


def day_care_trap(b: Builder) -> None:
    day_care(b, b.pool(day_care_listed=True))
    b.harden()


def accident_initial_wait(b: Builder) -> None:
    b.pick(b.normal_pool(cause=Cause.ACCIDENT, listed=False))
    b.admit("normal")
    b.new_policy_inside_initial_wait()
    b.room_within_cap()
    b.harden()


def accident_specific_wait(b: Builder) -> None:
    b.pick(b.normal_pool(cause=Cause.ACCIDENT, listed=True))
    b.admit("normal")
    b.history("inside_specific")
    b.room_within_cap()
    b.harden()


def ped_unrelated(b: Builder) -> None:
    payable(b, b.normal_pool(ped=False), distractors=False)
    b.declare_unrelated(b.rng.between(1, 2), show=True)
    b.harden()


def near_miss_covered(b: Builder) -> None:
    payable(b, b.normal_pool(keys=("nasal_fracture_reconstruction",)))
    b.harden()


def date_conflict_immaterial(b: Builder) -> None:
    payable(b, b.normal_pool())
    b.shift_claim_form(dt.timedelta(hours=b.rng.choice((-1, 1)) * b.rng.between(1, 10)))
    b.harden()


def room_rent_breach(b: Builder) -> None:
    payable(b, b.normal_pool(), room="above")
    b.harden()


def icu_breach(b: Builder) -> None:
    payable(b, b.normal_pool(icu=True))
    b.icu_stay(above_cap=True)
    b.harden()


def sublimit(b: Builder) -> None:
    sublimited_claim(b)
    b.harden()


def line_exclusion(b: Builder) -> None:
    payable(b, b.normal_pool())
    b.add_excluded_item()
    b.harden()


def pre_post_window(b: Builder) -> None:
    payable(b, b.normal_pool())
    b.add_pre_post(outside=True)
    b.harden()


def si_exhausted(b: Builder) -> None:
    b.sum_insured = min(b.profile.sum_insured_options)
    payable(b, b.normal_pool(keys=BIG_TICKET))


def ayush_capped(b: Builder) -> None:
    payable(b, b.pool(ayush=True))
    b.ayush_hospital = True


def ayush_covered(b: Builder) -> None:
    """AYUSH treatment in an AYUSH hospital, under a product that covers it up to the
    sum insured (a substitute for ayush_capped)."""
    payable(b, b.pool(ayush=True))
    b.ayush_hospital = True


def room_rent_and_copay(b: Builder) -> None:
    payable(b, b.normal_pool(), room="above")
    b.use_copay()


def sublimit_deductible_copay(b: Builder) -> None:
    sublimited_claim(b)
    b.use_deductible(smallest=True)
    b.use_copay()


def room_rent_exclusion_copay(b: Builder) -> None:
    payable(b, b.normal_pool(), room="above")
    b.add_excluded_item()
    b.use_copay()


def policy_lapsed(b: Builder) -> None:
    b.pick(b.normal_pool())
    b.admit("normal", window=(b.period_end + dt.timedelta(days=1), b.period_end + dt.timedelta(days=90)))
    b.history("established")
    b.room_within_cap()


def initial_wait_illness(b: Builder) -> None:
    b.pick(b.normal_pool(cause=Cause.ILLNESS, listed=False, ped=False))
    b.admit("normal")
    b.new_policy_inside_initial_wait()
    b.room_within_cap()


def specific_wait(b: Builder) -> None:
    b.pick(b.pool(cause=Cause.ILLNESS, listed=True, sublimited=None))
    stay = "day_care" if b.condition.day_care and b.day_care_listed(b.condition) else "normal"
    b.admit(stay)
    b.history("inside_specific")
    if stay == "normal":
        b.room_within_cap()


def ped_wait(b: Builder) -> None:
    b.pick(b.normal_pool(ped=True, listed=False))
    b.admit("normal")
    b.declared = [b.condition.ped]
    b.history("inside_ped")
    b.room_within_cap()


def permanent_exclusion(b: Builder) -> None:
    """A treatment the product never covers. One usually done within a day is
    admitted for a day; if it is not on the day-care list, the short stay is a
    second ground for rejection."""
    b.pick(b.pool(excluded=True, sublimited=None))
    if b.condition.day_care:
        b.admit("day_care")
        b.history("established")
    else:
        b.admit("normal")
        b.history("established")
        b.room_within_cap()


def short_stay(b: Builder) -> None:
    b.pick(b.pool(day_care_listed=False, short=True))
    b.admit("short")
    b.history("established")
    b.room_within_cap()


def ayush_not_qualified(b: Builder) -> None:
    if not (b.terms.ayush.covered and b.terms.ayush.requires_ayush_hospital):
        raise NotRealisable("the product does not tie AYUSH cover to AYUSH hospitals")
    payable(b, b.pool(ayush=True))
    b.ayush_hospital = False


def mismatch_on_rejected(b: Builder) -> None:
    short_stay(b)
    b.misstate_amount()


def missing_document(doc: DocType) -> Callable[[Builder], None]:
    def build(b: Builder) -> None:
        payable(b, b.normal_pool())
        b.documents.discard(doc)
    build.__name__ = f"missing_{doc.value.lower()}"
    return build


def amount_mismatch(b: Builder) -> None:
    payable(b, b.normal_pool())
    b.misstate_amount()


def date_conflict_material(b: Builder) -> None:
    """A new policy: one set of dates falls inside the initial wait, the other after it."""
    b.pick(b.normal_pool(cause=Cause.ILLNESS, listed=False, ped=False))
    b.admit("normal")
    b.new_policy_inside_initial_wait()
    b.room_within_cap()
    over = b.terms.initial_wait.duration.add_to(b.period_start)
    if over > b.period_end:
        raise NotRealisable("the initial wait outlasts the policy year")
    late_day = b.rng.date_between(over, min(over + dt.timedelta(days=20), b.period_end))
    shift = dt.datetime.combine(late_day, b.admitted_at.time()) - b.admitted_at
    if b.rng.chance(50):
        b.shift_claim_form(shift)  # hospital: inside the wait; claim form: after it
    else:
        b.move_admission(late_day)  # hospital: after the wait; claim form: inside it
        b.shift_claim_form(-shift)


# ---------------------------------------------------------------- the table


@dataclass(frozen=True)
class Scenario:
    name: str
    verdict: Verdict
    build: Callable[[Builder], None]
    tiers: tuple[int, int, int]
    """Slots per 100 seeds: (easy, medium, hard)."""
    required: frozenset[str] = frozenset()
    """Clauses the answer key must contain."""
    any_of: frozenset[str] = frozenset()
    """If set, the answer key must contain at least one of these."""
    allowed: frozenset[str] = frozenset()
    """Clauses the answer key may contain besides required and any_of."""
    tags: tuple[str, ...] = field(default=())

    def realised_by(self, decision: Decision, profile: ProductProfile) -> bool:
        clauses = set(decision.clauses)
        allowed = self.allowed | self.required | self.any_of
        if self.verdict in (Verdict.APPROVE, Verdict.PARTIAL):
            allowed |= {C.NON_PAYABLE}
            if profile.mandatory_copay_bp:
                allowed |= {C.COPAY}
        return (
            decision.verdict is self.verdict
            and self.required <= clauses
            and (not self.any_of or bool(self.any_of & clauses))
            and clauses <= allowed
        )


def _s(*clauses: str) -> frozenset[str]:
    return frozenset(clauses)


APPROVE, PARTIAL, REJECT, ESCALATE = Verdict.APPROVE, Verdict.PARTIAL, Verdict.REJECT, Verdict.ESCALATE
EXCLUSIONS = frozenset(C.STANDARD_EXCLUSIONS)
CO = C.COPAY

SCENARIOS: tuple[Scenario, ...] = (
    # APPROVE: 35 per 100
    Scenario("clean", APPROVE, clean, (6, 6, 0)),
    Scenario("copay_only", APPROVE, copay_only, (3, 2, 0), required=_s(CO)),
    Scenario("deductible_only", APPROVE, deductible_only, (2, 1, 0), required=_s(C.DEDUCTIBLE)),
    Scenario("day_care_trap", APPROVE, day_care_trap, (0, 1, 3), required=_s(C.DAY_CARE), allowed=_s(CO),
             tags=("day_care_trap",)),
    Scenario("accident_initial_wait", APPROVE, accident_initial_wait, (0, 1, 2),
             required=_s(C.INITIAL_WAITING_ACCIDENT), allowed=_s(CO)),
    Scenario("accident_specific_wait", APPROVE, accident_specific_wait, (0, 0, 2),
             required=_s(C.SPECIFIC_WAITING_ACCIDENT), allowed=_s(C.INITIAL_WAITING_ACCIDENT, CO)),
    Scenario("ped_unrelated", APPROVE, ped_unrelated, (0, 0, 2), allowed=_s(CO), tags=("ped_declared_unrelated",)),
    Scenario("near_miss_covered", APPROVE, near_miss_covered, (0, 0, 2), allowed=_s(CO, C.INITIAL_WAITING_ACCIDENT),
             tags=("exclusion_near_miss",)),
    Scenario("date_conflict_immaterial", APPROVE, date_conflict_immaterial, (0, 0, 2), allowed=_s(CO),
             tags=("immaterial_conflict",)),
    Scenario("ayush_covered", APPROVE, ayush_covered, (0, 0, 0), allowed=_s(CO), tags=("ayush",)),
    # PARTIAL: 40 per 100
    Scenario("room_rent_breach", PARTIAL, room_rent_breach, (4, 3, 1), required=_s(C.ROOM_RENT), allowed=_s(CO)),
    Scenario("icu_breach", PARTIAL, icu_breach, (2, 1, 1), required=_s(C.ICU_LIMIT), allowed=_s(CO)),
    Scenario("sublimit", PARTIAL, sublimit, (1, 2, 2), required=_s(C.DISEASE_SUBLIMIT), allowed=_s(C.DAY_CARE, CO)),
    Scenario("line_exclusion", PARTIAL, line_exclusion, (2, 1, 1), any_of=EXCLUSIONS, allowed=_s(CO),
             tags=("partial_exclusion",)),
    Scenario("pre_post_window", PARTIAL, pre_post_window, (1, 2, 1),
             any_of=_s(C.PRE_HOSPITALISATION, C.POST_HOSPITALISATION), allowed=_s(CO)),
    Scenario("si_exhausted", PARTIAL, si_exhausted, (2, 1, 0), required=_s(C.SUM_INSURED)),
    Scenario("ayush_capped", PARTIAL, ayush_capped, (1, 1, 0), required=_s(C.AYUSH)),
    Scenario("room_rent_and_copay", PARTIAL, room_rent_and_copay, (0, 1, 3), required=_s(C.ROOM_RENT, CO)),
    Scenario("sublimit_deductible_copay", PARTIAL, sublimit_deductible_copay, (0, 0, 3),
             required=_s(C.DISEASE_SUBLIMIT, C.DEDUCTIBLE, CO), allowed=_s(C.DAY_CARE)),
    Scenario("room_rent_exclusion_copay", PARTIAL, room_rent_exclusion_copay, (0, 0, 3),
             required=_s(C.ROOM_RENT, CO), any_of=EXCLUSIONS, tags=("partial_exclusion",)),
    # REJECT: 13 per 100
    Scenario("policy_lapsed", REJECT, policy_lapsed, (1, 0, 0), required=_s(C.POLICY_PERIOD)),
    Scenario("initial_wait_illness", REJECT, initial_wait_illness, (1, 1, 0), required=_s(C.INITIAL_WAITING)),
    Scenario("specific_wait", REJECT, specific_wait, (0, 0, 2), required=_s(C.SPECIFIC_WAITING)),
    Scenario("ped_wait", REJECT, ped_wait, (1, 1, 0), required=_s(C.PED_WAITING)),
    Scenario("permanent_exclusion", REJECT, permanent_exclusion, (1, 1, 0), any_of=EXCLUSIONS,
             allowed=_s(C.MIN_HOSPITALISATION)),
    Scenario("short_stay", REJECT, short_stay, (1, 1, 0), required=_s(C.MIN_HOSPITALISATION)),
    Scenario("ayush_not_qualified", REJECT, ayush_not_qualified, (0, 1, 0), required=_s(C.AYUSH)),
    Scenario("mismatch_on_rejected", REJECT, mismatch_on_rejected, (0, 0, 1), required=_s(C.MIN_HOSPITALISATION),
             tags=("immaterial_conflict",)),
    # ESCALATE: 12 per 100
    Scenario("missing_discharge_summary", ESCALATE, missing_document(DocType.DISCHARGE_SUMMARY), (2, 1, 0),
             required=_s(C.MISSING_DOCUMENTS)),
    Scenario("missing_bill", ESCALATE, missing_document(DocType.HOSPITAL_BILL), (1, 1, 0),
             required=_s(C.MISSING_DOCUMENTS)),
    Scenario("missing_claim_form", ESCALATE, missing_document(DocType.CLAIM_FORM), (0, 1, 0),
             required=_s(C.MISSING_DOCUMENTS)),
    Scenario("amount_mismatch", ESCALATE, amount_mismatch, (2, 1, 0), required=_s(C.DOCUMENT_MISMATCH)),
    Scenario("date_conflict_material", ESCALATE, date_conflict_material, (0, 1, 2), required=_s(C.DOCUMENT_MISMATCH)),
)

SCENARIO_BY_NAME = {scenario.name: scenario for scenario in SCENARIOS}


def _schedule() -> tuple[tuple[str, Difficulty], ...]:
    slots = [
        (scenario.name, tier)
        for scenario in SCENARIOS
        for tier, count in zip(Difficulty, scenario.tiers)
        for _ in range(count)
    ]
    return tuple(Rng(0, "schedule").shuffled(slots))


SCHEDULE = _schedule()
"""100 (scenario, tier) slots; seed n gets SCHEDULE[n % 100]."""
