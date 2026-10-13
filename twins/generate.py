"""Deterministic synthetic candidates plus the two rule-based renderings.

`plain`  - terse, human-style profile containing every fact.
`sparse` - titles, companies and dates only (the shape of candidate #721 in
           Metaview's published fillmore case study: sparse role descriptions).

The LLM-written renderings (`polished`, `verbose`) are produced in rewrite.py
from `plain` and checked for fact preservation.
"""
from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .briefs import BRIEFS, Brief, Template, reference_tier

PRESENT_YEAR = 2026

COMPANIES = (
    "Brightpath", "Lumen Harbor", "Corvid Systems", "Tallyhand", "Ferncastle",
    "Orbitwise", "Mapleforge", "Stillwater Labs", "Paperlane", "Driftwood Analytics",
    "Halcyon Health", "Ironbark", "Nimbusfield", "Saltmarsh", "Quarry Lane",
    "Tidewell", "Larkspur Labs", "Cinderpath", "Oakhollow", "Verdant Freight",
)

TIER_PLAN = ("great",) * 5 + ("good",) * 6 + ("okay",) * 5 + ("poor",) * 4


@dataclass
class Fact:
    text: str
    tokens: list[str]
    criterion: str | None   # None for distractor facts


@dataclass
class Role:
    title: str
    company: str
    company_desc: str
    start: int
    end: int                # PRESENT_YEAR means "present"
    facts: list[Fact] = field(default_factory=list)

    @property
    def years_str(self) -> str:
        end = "present" if self.end == PRESENT_YEAR else str(self.end)
        return f"{self.start}-{end}"


@dataclass
class Person:
    id: str
    brief_id: str
    total_years: int
    roles: list[Role]
    education: str
    criteria_met: list[str]
    ref_tier: str

    def required_tokens(self) -> list[str]:
        """Strings a faithful rewrite must keep: titles, companies, years, numbers, tech."""
        req: list[str] = []
        for r in self.roles:
            req += [r.title, r.company, str(r.start)]
            if r.end != PRESENT_YEAR:
                req.append(str(r.end))
            req += _numbers(r.company_desc)
            if "seed-stage" in r.company_desc:
                req.append("seed-stage")
            for f in r.facts:
                req += f.tokens + _numbers(f.text)
        seen, out = set(), []
        for t in req:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out

    def own_tokens(self) -> set[str]:
        return {t for r in self.roles for f in r.facts for t in f.tokens}


def _numbers(s: str) -> list[str]:
    import re
    return re.findall(r"\d+(?:\.\d+)?", s)


def _fill(tpl: Template, rng: random.Random) -> Fact:
    vals = {
        "n": rng.choice([4, 6, 8, 12, 15, 18, 24, 30, 40, 55, 70, 90]),
        "m": rng.choice([3, 4, 5, 6, 7, 9, 11, 14]),
        "p": rng.choice([7, 9, 12, 14, 18, 22, 27, 31, 35]),
        "k": rng.choice([2, 3, 4, 5, 6]),
    }
    return Fact(text=tpl.text.format(**vals), tokens=list(tpl.tokens), criterion=None)


def _choose_criteria(brief: Brief, tier: str, rng: random.Random) -> set[str]:
    musts = [c.id for c in brief.musts]
    nices = [c.id for c in brief.nices]
    if tier == "great":
        chosen = set(musts) | set(rng.sample(nices, rng.choice([2, 3])))
    elif tier == "good":
        chosen = set(musts) | set(rng.sample(nices, rng.choice([0, 1])))
    elif tier == "okay":
        chosen = set(rng.sample(musts, 2)) | set(rng.sample(nices, rng.choice([0, 1, 2, 3])))
    else:
        chosen = set(rng.sample(musts, rng.choice([0, 1]))) | set(rng.sample(nices, rng.choice([0, 1, 2])))
    # Drop criteria whose prerequisites are missing (e.g. FastAPI without Python).
    changed = True
    while changed:
        changed = False
        for cid in list(chosen):
            if any(req not in chosen for req in brief.criterion(cid).requires):
                chosen.discard(cid)
                changed = True
    return chosen


def make_person(brief: Brief, idx: int, tier_target: str, rng: random.Random) -> Person:
    met = _choose_criteria(brief, tier_target, rng)
    lo, hi = brief.years
    total = rng.randint(lo, hi)
    n_roles = 2 if total < 6 else rng.choice([2, 3])

    # Split total years across roles (most recent first), each role >= 1 year.
    cuts = sorted(rng.sample(range(1, total), n_roles - 1)) if total > n_roles else list(range(1, n_roles))
    spans = [b - a for a, b in zip([0, *cuts], [*cuts, total])]
    spans = [max(1, s) for s in spans][::-1]  # spans[0] = most recent role
    companies = rng.sample(COMPANIES, n_roles)

    roles: list[Role] = []
    end = PRESENT_YEAR
    for i in range(n_roles):
        start = end - spans[i]
        if i == 0:
            title = brief.titles[0] if total >= 6 else brief.titles[2]
        else:
            title = rng.choice(brief.titles[1:])
        roles.append(Role(title=title, company=companies[i], company_desc="", start=start, end=end))
        end = start

    # Company descriptors; exactly one seed-stage company iff early_stage is met.
    early_idx = rng.randrange(n_roles) if "early_stage" in met else None
    for i, r in enumerate(roles):
        if i == early_idx:
            r.company_desc = f"seed-stage, {rng.choice([8, 11, 14, 17, 22, 26])} people"
        else:
            r.company_desc = rng.choice([
                f"Series C, {rng.choice([220, 340, 480, 610])} people",
                f"public company, {rng.choice([2400, 3800, 5200, 8100])} people",
            ])

    # One evidence fact per met criterion (company-based criteria need no bullet).
    for cid in sorted(met):
        crit = brief.criterion(cid)
        if crit.via_company:
            continue
        fact = _fill(rng.choice(crit.templates), rng)
        fact.criterion = cid
        target = roles[0] if (len(roles) == 1 or rng.random() < 0.55) else rng.choice(roles[1:])
        target.facts.append(fact)

    # Distractor facts so every role has 2-3 bullets.
    pool = list(brief.distractors)
    rng.shuffle(pool)
    for r in roles:
        while len(r.facts) < rng.choice([2, 3]) and pool:
            r.facts.append(_fill(pool.pop(), rng))
        rng.shuffle(r.facts)

    musts_met = sum(1 for c in brief.musts if c.id in met)
    nices_met = sum(1 for c in brief.nices if c.id in met)
    return Person(
        id=f"{brief.id}{idx:02d}",
        brief_id=brief.id,
        total_years=total,
        roles=roles,
        education="BSc Computer Science",
        criteria_met=sorted(met),
        ref_tier=reference_tier(musts_met, nices_met),
    )


def render_plain(p: Person) -> str:
    lines = [f"Candidate #{p.id}", f"{p.roles[0].title} at {p.roles[0].company}", "", "Experience"]
    for r in p.roles:
        lines.append(f"{r.title} - {r.company} ({r.company_desc}) · {r.years_str}")
        lines += [f"- {f.text}" for f in r.facts]
        lines.append("")
    skills = sorted(p.own_tokens())
    lines.append(f"Education: {p.education}")
    if skills:
        lines.append("Skills: " + ", ".join(skills))
    return "\n".join(lines).strip() + "\n"


def render_sparse(p: Person) -> str:
    lines = [f"Candidate #{p.id}", f"{p.roles[0].title} at {p.roles[0].company}", "", "Experience"]
    for r in p.roles:
        lines.append(f"{r.title} - {r.company} · {r.years_str}")
    lines += ["", f"Education: {p.education}"]
    return "\n".join(lines).strip() + "\n"


def generate(per_brief: int, seed: int) -> list[Person]:
    people: list[Person] = []
    for bid, brief in BRIEFS.items():
        rng = random.Random(f"{seed}-{bid}")
        plan = [TIER_PLAN[i * len(TIER_PLAN) // per_brief] for i in range(per_brief)]
        for i, tier in enumerate(plan, start=1):
            people.append(make_person(brief, i, tier, rng))
    return people


def save(people: list[Person], data_dir: Path) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    truth = [asdict(p) for p in people]
    (data_dir / "truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    profiles = {
        p.id: {"brief_id": p.brief_id, "plain": render_plain(p), "sparse": render_sparse(p)}
        for p in people
    }
    (data_dir / "profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")


def load_people(data_dir: Path) -> list[Person]:
    raw = json.loads((data_dir / "truth.json").read_text(encoding="utf-8"))
    out = []
    for d in raw:
        roles = [Role(**{**r, "facts": [Fact(**f) for f in r["facts"]]}) for r in d["roles"]]
        out.append(Person(**{**d, "roles": roles}))
    return out
