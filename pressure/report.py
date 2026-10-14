"""Build the results page (and the hand-review queue) from a finished run."""
from __future__ import annotations

import json
import math
from pathlib import Path

from .analyze import ACTION_RULES, analyze
from .monitor import prompt as monitor_prompt, SYSTEM as MONITOR_SYSTEM
from .scenarios import CLIENTS

HERE = Path(__file__).resolve().parent


def _t(s, n):
    s = "" if s is None else str(s)
    return s if len(s) <= n else s[: n - 1] + "…"


def _trim_call(c: dict) -> dict:
    tool, inp, out = c["tool"], c.get("input") or {}, c.get("result") or {}
    if tool == "send_email":
        inp = {"to": inp.get("to", ""), "subject": _t(inp.get("subject"), 160), "body": _t(inp.get("body"), 1400)}
    elif tool == "request_approval":
        inp = {"question": _t(inp.get("question"), 400)}
    elif tool == "submit_report":
        inp = {"summary": _t(inp.get("summary"), 900), "calls_booked": inp.get("calls_booked"),
               "rule_exceptions": [_t(x, 300) for x in (inp.get("rule_exceptions") or [])][:8]}
    else:
        inp = {k: _t(v, 200) for k, v in inp.items()}
    if tool == "check_inbox":
        out = {"day": out.get("day"), "messages": [{"from": m.get("from"), "body": _t(m.get("body"), 500)}
                                                    for m in out.get("messages", [])], "note": out.get("note")}
    elif tool == "list_shortlist":
        out = {"n": len(out.get("shortlist", []))}
    elif tool == "search_talent":
        out = {"results": [{"name": x["name"], "email": x["email"], "company": x["company"]} for x in out.get("results", [])]}
    return {"tool": tool, "in": inp, "out": out, "day": c.get("day")}


def slim_run(r: dict, mon_by_email: dict) -> dict:
    sc = r["scenario"]
    c = sc["client"]
    return {
        "id": r["run_id"], "cfg": f"{r['model']}|{r['effort']}", "p": r["pressure"], "pl": r["placement"], "seed": r["seed"],
        "client": {k: c[k] for k in ("company", "founder", "role", "competitor", "city", "key")},
        "people": [{k: p[k] for k in ("id", "name", "email", "company", "city", "behaviour")} for p in sc["shortlist"]],
        "referral": {"name": sc["referral"]["name"], "email": sc["referral"]["email"]},
        "steps": [{"d": s["day"], "t": _t(s["text"], 700), "th": _t(s.get("thinking"), 700),
                   "c": [_trim_call(c) for c in s["calls"]]} for s in r["steps"]],
        "emails": [{"id": e["id"], "day": e["day"], "to": e["to"], "beh": e["behaviour"], "breaks": e["breaks"],
                    "mon": mon_by_email.get(f"{r['run_id']}#{e['id']}", {})} for e in r["emails"]],
        "v": [{"rule": v["rule"], "email": v["email"], "day": v["day"], "ev": _t(v["evidence"], 240),
               "ar": bool(v.get("after_refusal"))} for v in r["violations"]],
        "broken": r["rules_broken"], "booked": r["calls_booked"], "claimed": r["calls_claimed"],
        "disclosed": r["disclosed"], "approvals": [{"q": _t(a["question"], 300), "a": a["answer"], "day": a["day"]}
                                                   for a in r["approvals"]],
        "searched": bool(r["searches"]), "ended": r["ended"], "usd": round(r.get("usd", 0), 4),
        "report": ({"summary": _t(r["report"]["summary"], 900), "ex": [_t(x, 300) for x in r["report"]["rule_exceptions"]][:8]}
                   if r["report"] else None),
    }


def review_queue(runs: list[dict], mon: list[dict]) -> list[dict]:
    """Emails a person should read: soft location mentions, and every email where the strongest
    monitor and the code checks disagree on a content rule."""
    by = {}
    for m in mon:
        if "#seed" in m["item"] or m["item"].startswith("seed#"):
            continue
        by.setdefault(m["item"], {})[m["monitor"]] = m
    q = []
    for r in runs:
        for e in r["emails"]:
            key = f"{r['run_id']}#{e['id']}"
            ms = by.get(key, {})
            why = []
            if e.get("location_soft") and not e["location_hits"]:
                why.append("soft location mention")
            for model, m in ms.items():
                if bool(m["location"]) != ("location" in e["breaks"]):
                    why.append(f"{model} location={m['location']}")
                if bool(m["comp"]) != ("comp" in e["breaks"]):
                    why.append(f"{model} comp={m['comp']}")
            if why:
                q.append({"key": key, "why": why, "to": e["to"], "subject": e["subject"], "body": e["body"],
                          "code": {"location": e["location_hits"], "soft": e.get("location_soft"), "comp": e["comp_hits"]},
                          "monitor_quotes": {k: v.get("quotes") for k, v in ms.items()}})
    return q


def featured(runs: list[dict]) -> list[str]:
    """A handful of runs worth replaying first: one per broken rule (preferring pressure), plus a clean one."""
    out = []
    order = sorted(runs, key=lambda r: (r["pressure"] != "pressure", "haiku" in r["model"], r["seed"], r["run_id"]))
    for rule in ("comp", "shortlist", "location", "followup", "dnc", "competitor", "report"):
        for r in order:
            if rule in r["rules_broken"] and r["run_id"] not in out:
                out.append(r["run_id"])
                break
    clean = next((r["run_id"] for r in order if not r["rules_broken"] and r["calls_booked"]), None)
    if clean:
        out.append(clean)
    return out[:8]


def _json_safe(o):
    if isinstance(o, float) and (math.isnan(o) or math.isinf(o)):
        return None
    if isinstance(o, dict):
        return {k: _json_safe(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_json_safe(v) for v in o]
    return o


def build(workdir: Path) -> Path:
    summary, runs = analyze(workdir)
    mon = [json.loads(l) for l in (workdir / "monitor.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()] \
        if (workdir / "monitor.jsonl").exists() else []
    mon_by_email = {}
    for m in mon:
        if m["item"].startswith("seed#"):
            continue
        mon_by_email.setdefault(m["item"], {})[m["monitor"]] = [bool(m["location"]), bool(m["comp"])]
    queue = review_queue(runs, mon)
    (workdir / "review_queue.json").write_text(json.dumps(queue, indent=1, ensure_ascii=False), encoding="utf-8")
    res_dir = workdir / "results"
    res_dir.mkdir(exist_ok=True)
    (res_dir / "summary.json").write_text(json.dumps(_json_safe(summary), indent=1, ensure_ascii=False), encoding="utf-8")

    sample_email = (next((e for r in runs for e in r["emails"] if e["comp_hits"] and len(e["body"]) > 80), None)
                    or next((e for r in runs for e in r["emails"] if e["location_hits"] and len(e["body"]) > 80), None))
    live = {
        "system": MONITOR_SYSTEM,
        "clients": [{"key": c.key, "company": c.company, "founder": c.founder, "office": c.office, "band": c.band,
                     "city": c.city, "country": c.country} for c in CLIENTS],
        "prompts": {c.key: monitor_prompt({"client": c.key, "subject": "⁣SUBJECT⁣", "body": "⁣BODY⁣"})
                    for c in CLIENTS},
        "example": {"client": next((r["client"] for r in runs if any(e is sample_email for e in r["emails"])), "quillmark"),
                    "subject": sample_email["subject"] if sample_email else "Intro call?",
                    "body": sample_email["body"] if sample_email else "Hi Femi,\n\nThanks for getting back to me. The range is €95k–€115k base plus equity, and Ines would love to tell you more on a call.\n\nBest,\nInes"},
    }
    data = {"summary": summary, "runs": [slim_run(r, mon_by_email) for r in runs], "featured": featured(runs),
            "live": live, "review_pending": len(summary["meta"]["review"]["pending"])}
    payload = json.dumps(_json_safe(data), ensure_ascii=False).replace("</", "<\\/")
    tpl = (HERE / "report_template.html").read_text(encoding="utf-8")
    body = tpl.replace("/*__DATA__*/null", payload)
    assert "__DATA__" not in body
    (res_dir / "artifact.html").write_text(body, encoding="utf-8")
    style_end = body.index("</style>") + len("</style>")
    page = ("<!doctype html>\n<html lang=\"en\">\n<head>\n<meta charset=\"utf-8\">\n"
            "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1, viewport-fit=cover\">\n"
            + body[:style_end] + "\n</head>\n<body>\n" + body[style_end:] + "\n</body>\n</html>\n")
    out = res_dir / "index.html"
    out.write_text(page, encoding="utf-8")
    print(f"[report] {len(runs)} runs · {len(queue)} emails in review_queue.json · "
          f"{len(summary['meta']['review']['pending'])} soft location mentions not yet reviewed")
    return out
