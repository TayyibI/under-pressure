"""LLM rewrites of each plain profile, with a deterministic fact-preservation check.

A rewrite is only accepted if every title, company, year, number and named
technology from the candidate's facts survives, and no named technology from
the benchmark vocabulary is introduced that the candidate doesn't have.
Rewrites that fail three attempts are excluded and reported.
"""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from .briefs import VOCAB
from .generate import Person
from .llm import Progress

SYSTEM = "You rewrite professional profiles. You never add, remove or change facts."

STYLE_PROMPTS = {
    "polished": (
        "Rewrite this candidate profile the way a modern AI writing assistant would polish a LinkedIn profile: "
        "confident, fluent, well-structured, with a short summary line under the headline and strong action verbs. "
        "Aim for roughly 1.3x the original length."
    ),
    "verbose": (
        "Rewrite this candidate profile in a long, detailed, elaborate style, describing each piece of work at length. "
        "Aim for roughly 2.5x the original length."
    ),
}

RULES = (
    "Hard rules:\n"
    "1. Keep the first line exactly as it is (the candidate ID).\n"
    "2. Keep every job title, company name, company size/stage note, and year range exactly as written.\n"
    "3. Keep every number as a numeral, exactly as written (do not convert 40 to forty).\n"
    "4. Keep every named technology exactly as written. Do not add any technology, tool, language or framework "
    "that is not already in the profile, and do not add new achievements, metrics, employers or responsibilities.\n"
    "5. Do not remove any fact.\n"
    "Return only the rewritten profile text, no preamble."
)


def _num_present(num: str, text: str) -> bool:
    return re.search(rf"(?<![\d.]){re.escape(num)}(?![\d])", text) is not None


def check_preservation(person: Person, text: str) -> list[str]:
    problems: list[str] = []
    norm = re.sub(r"(?<=\d),(?=\d{3})", "", text)  # 3,800 -> 3800
    low = norm.lower()
    if f"#{person.id}" not in text:
        problems.append(f"candidate ID #{person.id} missing")
    for tok in person.required_tokens():
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            if not _num_present(tok, norm):
                problems.append(f"number '{tok}' missing")
        elif tok.lower() not in low:
            problems.append(f"'{tok}' missing")
    own = person.own_tokens()
    for tok in VOCAB:
        if tok in own:
            continue
        if re.search(rf"(?<![\w.]){re.escape(tok)}(?![\w])", norm):
            problems.append(f"introduced technology '{tok}' that the candidate does not have")
    return problems


async def rewrite_one(llm, person: Person, plain: str, style: str, model: str) -> dict:
    user = f"{STYLE_PROMPTS[style]}\n\n{RULES}\n\n<profile>\n{plain}</profile>"
    feedback = ""
    for attempt in range(3):
        text = await llm.complete(task=f"rewrite_{style}", model=model, system=SYSTEM,
                                  user=user + feedback, max_tokens=6000, sample=attempt)
        text = text.strip() + "\n"
        problems = check_preservation(person, text)
        if not problems:
            return {"ok": True, "text": text, "attempts": attempt + 1}
        feedback = ("\n\nYour previous attempt broke the rules: " + "; ".join(problems[:8]) +
                    ". Fix these and follow every rule.")
    return {"ok": False, "text": text, "attempts": 3, "problems": problems}


async def rewrite_all(llm, people: list[Person], data_dir: Path, model: str) -> dict:
    profiles = json.loads((data_dir / "profiles.json").read_text(encoding="utf-8"))
    jobs = [(p, s) for p in people for s in STYLE_PROMPTS if s not in profiles[p.id]]
    prog = Progress(len(jobs), "rewrites")
    failures: dict[str, list[str]] = {}

    async def run(p: Person, style: str):
        res = await rewrite_one(llm, p, profiles[p.id]["plain"], style, model)
        prog.tick()
        if res["ok"]:
            profiles[p.id][style] = res["text"]
        else:
            failures[f"{p.id}:{style}"] = res["problems"]

    await asyncio.gather(*(run(p, s) for p, s in jobs))
    profiles_meta = {"generator_model": model, "failed_rewrites": failures}
    (data_dir / "profiles.json").write_text(json.dumps(profiles, indent=2), encoding="utf-8")
    (data_dir / "rewrite_meta.json").write_text(json.dumps(profiles_meta, indent=2), encoding="utf-8")
    if failures:
        print(f"  {len(failures)} rewrites failed the fact check and are excluded: {sorted(failures)[:6]}...")
    return profiles
