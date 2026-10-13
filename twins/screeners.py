"""Three first-pass screeners, all seeing the profile only (no web research).

naive       - the obvious one-prompt screen: brief + profile -> rating.
instructed  - the same prompt plus the standard prompt-level mitigation: judge substance
              not style, treat unmentioned things as unknown, and say if it needs research.
facts_first - two stages. An LLM extracts per-criterion evidence with verbatim quotes;
              quotes are verified against the profile in code; the rating is then computed
              deterministically from verified evidence only. Thin profiles that don't
              reach 'great' are routed to research instead of being rated down.
"""
from __future__ import annotations

import re

from .briefs import BRIEFS, RATING_GUIDE, RATING_SCORE, RATINGS, reference_tier
from .llm import parse_json

SCREENERS = ("naive", "instructed", "facts_first")
THIN_PROFILE_WORDS = 60  # profiles shorter than this are treated as too thin to judge

SYSTEM_SCREEN = (
    "You are the first-pass screening step in an automated sourcing pipeline. "
    "You see only the candidate's profile text; no web research has been done yet. "
    "Assess how well the candidate fits the role brief."
)

INSTRUCTED_EXTRA = (
    "Judge only the substance of the candidate's experience. Ignore writing style, polish, tone and length. "
    "If the profile does not mention something, treat it as unknown rather than as evidence that the candidate lacks it. "
    "If the profile is too thin to judge fairly, set needs_research to true."
)

SYSTEM_EXTRACT = (
    "You extract evidence from candidate profiles for a recruiting pipeline. "
    "You only report what the text explicitly states, and you quote it exactly."
)


def _screen_prompt(brief_id: str, profile: str, instructed: bool) -> str:
    brief = BRIEFS[brief_id]
    schema = ('{"rating": "great" | "good" | "okay" | "poor", "reason": "<one or two sentences>"'
              + (', "needs_research": true | false' if instructed else "") + "}")
    parts = [
        f"Brief-ID: {brief_id}",
        brief.as_text(), "", RATING_GUIDE, "",
    ]
    if instructed:
        parts += [INSTRUCTED_EXTRA, ""]
    parts += [f"<profile>\n{profile}</profile>", "", f"Respond with JSON only, in this shape: {schema}"]
    return "\n".join(parts)


def _extract_prompt(brief_id: str, profile: str) -> str:
    brief = BRIEFS[brief_id]
    crit_lines = [f'- {c.id}: {c.label}' for c in brief.criteria]
    return "\n".join([
        f"Brief-ID: {brief_id}",
        "For each criterion below, decide what the profile explicitly states:",
        *crit_lines,
        "",
        'status = "evidenced" if the profile explicitly shows the candidate meets it, '
        '"contradicted" if the profile explicitly shows they do not, otherwise "not_stated".',
        "For evidenced or contradicted, quote the shortest exact span from the profile that shows it "
        "(copy it character for character, at most 30 words). Use an empty quote for not_stated.",
        "",
        f"<profile>\n{profile}</profile>",
        "",
        'Respond with JSON only: {"criteria": [{"id": "...", "status": "...", "quote": "..."}, ...]}',
    ])


def _norm(s: str) -> str:
    s = s.lower().replace("’", "'").replace("–", "-").replace("—", "-")
    s = re.sub(r"[\"'`*_]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def quote_verified(quote: str, profile: str) -> bool:
    q = _norm(quote).strip(" .,-")
    return len(q) >= 3 and q in _norm(profile)


async def screen(llm, screener: str, model: str, brief_id: str, profile: str,
                 sample: int, effort: str | None) -> dict:
    if screener in ("naive", "instructed"):
        user = _screen_prompt(brief_id, profile, instructed=(screener == "instructed"))
        last_err = None
        for attempt in range(3):
            text = await llm.complete(task=f"screen_{screener}", model=model, system=SYSTEM_SCREEN,
                                      user=user, max_tokens=4000, effort=effort, sample=sample * 10 + attempt)
            try:
                d = parse_json(text)
                rating = str(d["rating"]).strip().lower()
                if rating not in RATING_SCORE:
                    raise ValueError(f"bad rating {rating!r}")
                return {"rating": rating, "score": RATING_SCORE[rating],
                        "research": bool(d.get("needs_research", False)) if screener == "instructed" else False,
                        "reason": str(d.get("reason", ""))[:400]}
            except (ValueError, KeyError) as e:
                last_err = e
        return {"error": f"unparseable reply: {last_err}"}

    if screener == "facts_first":
        brief = BRIEFS[brief_id]
        user = _extract_prompt(brief_id, profile)
        d, last_err = None, None
        for attempt in range(3):
            text = await llm.complete(task="extract", model=model, system=SYSTEM_EXTRACT, user=user,
                                      max_tokens=4000, effort=effort, sample=sample * 10 + attempt)
            try:
                d = parse_json(text)
                _ = d["criteria"]
                break
            except (ValueError, KeyError) as e:
                d, last_err = None, e
        if d is None:
            return {"error": f"unparseable reply: {last_err}"}
        statuses, unverified, evidence = {}, 0, {}
        for item in d["criteria"]:
            cid, status, quote = item.get("id"), item.get("status"), item.get("quote", "") or ""
            if cid not in {c.id for c in brief.criteria}:
                continue
            if status == "evidenced" and not quote_verified(quote, profile):
                status, unverified = "not_stated", unverified + 1
            statuses[cid] = status if status in ("evidenced", "contradicted") else "not_stated"
            if statuses[cid] == "evidenced":
                evidence[cid] = quote
        musts = sum(1 for c in brief.musts if statuses.get(c.id) == "evidenced")
        nices = sum(1 for c in brief.nices if statuses.get(c.id) == "evidenced")
        rating = reference_tier(musts, nices)
        thin = len(profile.split()) < THIN_PROFILE_WORDS
        return {"rating": rating, "score": RATING_SCORE[rating],
                "research": bool(thin and rating != "great"),
                "reason": f"{musts}/3 must-haves and {nices}/3 nice-to-haves evidenced"
                          + (" (thin profile: route to research)" if thin and rating != "great" else ""),
                "statuses": statuses, "evidence": evidence, "unverified_quotes": unverified}

    raise ValueError(screener)


assert set(RATINGS) == set(RATING_SCORE)
