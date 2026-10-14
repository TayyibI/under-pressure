"""Turn a finished run into the data the research-queue app needs, and build the app.

For each screener and profile type (full or sparse), count how often each first-pass label
was given to candidates of each true tier. "research" is its own label: the screener asked
for research instead of rating. These counts are real model outputs from the run; the app
turns them into P(label | tier, profile type) and, with a prior, into the chance that
researching a candidate turns up a great one.

The app also gets every benchmark candidate (synthetic) with the labels the screeners
actually gave, and the exact screening prompts, so a viewer can re-run a first pass live.
"""
from __future__ import annotations

import json
import shutil
from collections import defaultdict
from pathlib import Path

from .briefs import BRIEFS
from .screeners import (INSTRUCTED_EXTRA, SYSTEM_EXTRACT, SYSTEM_SCREEN, THIN_PROFILE_WORDS,
                        _extract_prompt, _screen_prompt)

TIERS = ("poor", "okay", "good", "great")
APP_DIR = Path(__file__).resolve().parent.parent / "app"
PROFILE_SLOT = "⁣PROFILE⁣"  # invisible marker the page replaces with the profile text


def _label(r: dict) -> str:
    return "research" if r.get("research") else r["rating"]


def build(workdir: Path) -> dict:
    data = workdir / "data"
    truth = {p["id"]: p for p in json.loads((data / "truth.json").read_text(encoding="utf-8"))}
    profiles = json.loads((data / "profiles.json").read_text(encoding="utf-8"))
    cfg = json.loads((workdir / "config.json").read_text(encoding="utf-8"))
    model = cfg["models"][0]   # calibrate on the first screening model

    counts: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(lambda: defaultdict(int))))
    recorded: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    n_obs: dict = defaultdict(int)
    for line in (workdir / "results.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if "error" in r or r["model"] != model:
            continue
        kind = "sparse" if r["variant"] == "sparse" else "full"
        tier = truth[r["person"]]["ref_tier"]
        counts[r["screener"]][kind][tier][_label(r)] += 1
        n_obs[r["screener"]] += 1
        if r["variant"] in ("plain", "sparse"):
            recorded[r["person"]][r["screener"]][r["variant"]].append(
                {"label": _label(r), "reason": r.get("reason", "")[:300], "repeat": r["repeat"]})

    candidates = []
    for pid in sorted(truth):
        p, prof = truth[pid], profiles[pid]
        rec = {s: {v: [x["label"] for x in sorted(lst, key=lambda x: x["repeat"])] for v, lst in by_v.items()}
               for s, by_v in recorded[pid].items()}
        candidates.append({
            "id": pid, "brief": p["brief_id"], "tier": p["ref_tier"], "title": p["roles"][0]["title"],
            "years": p["total_years"], "plain": prof["plain"], "sparse": prof["sparse"], "labels": rec,
        })

    briefs = {}
    for bid, b in BRIEFS.items():
        briefs[bid] = {
            "title": b.title, "company": b.company, "text": b.as_text(),
            "criteria": [{"id": c.id, "label": c.label, "kind": c.kind} for c in b.criteria],
            "prompts": {
                "naive": SYSTEM_SCREEN + "\n\n" + _screen_prompt(bid, PROFILE_SLOT, instructed=False),
                "instructed": SYSTEM_SCREEN + "\n\n" + _screen_prompt(bid, PROFILE_SLOT, instructed=True),
                "facts_first": SYSTEM_EXTRACT + "\n\n" + _extract_prompt(bid, PROFILE_SLOT),
            },
        }
    assert INSTRUCTED_EXTRA in briefs["A"]["prompts"]["instructed"]

    return {
        "meta": {
            "model": model, "effort": cfg.get("effort"), "repeats": cfg["repeats"],
            "n_people": len(truth), "tiers": {t: sum(1 for p in truth.values() if p["ref_tier"] == t) for t in TIERS},
            "observations": dict(n_obs), "mock": cfg.get("mock", False), "thin_words": THIN_PROFILE_WORDS,
            "slot": PROFILE_SLOT,
        },
        "counts": json.loads(json.dumps(counts)),
        "candidates": candidates,
        "briefs": briefs,
    }


def build_app(workdir: Path, out_dir: Path, author: str = "") -> list[Path]:
    """Write <out_dir>/index.html (any static host, or open from disk) and artifact.html (claude.ai)."""
    cal = build(workdir)
    cal["author"] = author
    report = workdir / "results" / "index.html"
    cal["chapter_one"] = "kill-test.html" if report.exists() else ""

    template = (APP_DIR / "app_template.html").read_text(encoding="utf-8")
    sim = (APP_DIR / "sim.js").read_text(encoding="utf-8")
    payload = json.dumps(cal, ensure_ascii=False).replace("</", "<\\/")
    body = template.replace("/*__SIM_JS__*/", sim).replace("/*__APP_DATA__*/null", payload)
    assert "__APP_DATA__" not in body and "__SIM_JS__" not in body

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact = out_dir / "artifact.html"   # claude.ai Artifacts add the document shell themselves
    artifact.write_text(body, encoding="utf-8")

    style_end = body.index("</style>") + len("</style>")
    standalone = (
        "<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
        "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
        + body[:style_end] + "\n</head>\n<body>\n" + body[style_end:] + "\n</body>\n</html>\n"
    )
    index = out_dir / "index.html"
    index.write_text(standalone, encoding="utf-8")
    written = [index, artifact]
    if report.exists():
        shutil.copyfile(report, out_dir / "kill-test.html")
        written.append(out_dir / "kill-test.html")
    return written
