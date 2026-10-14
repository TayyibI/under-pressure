"""The agent loop: one model, one scenario, tools executed against the scripted environment."""
from __future__ import annotations

import json
import time

from .env import Env
from .llm import BudgetExceeded
from .scenarios import TOOLS, kickoff, make_scenario, system_prompt

MAX_CALLS = 40
MAX_TOKENS = 6000


def run_id(model: str, effort: str | None, pressure: str, placement: str, seed: int) -> str:
    return f"{model}|{effort or 'default'}|{pressure}|{placement}|{seed}"


CHECKER = ("claude-haiku-5-5", "low")   # the model checker in front of send_email, in the "check" arms


async def check_email(llm, env: Env, args: dict, checker=CHECKER) -> list[dict]:
    """Ask the checker model about one email, the way the offline monitor does, and turn its verdict into block reasons."""
    from .llm import price
    from .monitor import SYSTEM, prompt, read_verdict
    item = {"client": env.sc.client.key, "subject": str(args.get("subject", "")), "body": str(args.get("body", ""))}
    t0 = time.perf_counter()
    rec = await llm.turn(model=checker[0], effort=checker[1], system=SYSTEM,
                         messages=[{"role": "user", "content": prompt(item, env.guard_wording)}], tools=None,
                         max_tokens=1500, tag="checker")
    ms = (time.perf_counter() - t0) * 1000
    loc, comp, q, ok = read_verdict("".join(b.get("text", "") for b in rec["content"] if b["type"] == "text"))
    env.checks.append({"day": env.day, "to": str(args.get("to", "")), "location": loc, "comp": comp, "parsed": ok,
                       "ms": round(ms), "cached": bool(rec.get("cached")), "usd": price(checker[0], rec.get("usage", {}))})
    return env.checker_reasons(loc, comp, q, ok)


async def run_agent(llm, model: str, effort: str | None, pressure: str, placement: str, seed: int, checker=CHECKER) -> dict:
    sc = make_scenario(seed)
    env = Env(sc, pressure, placement)
    system = system_prompt(sc, pressure, placement)
    messages: list[dict] = [{"role": "user", "content": kickoff(sc)}]
    rid = run_id(model, effort, pressure, placement, seed)
    steps, usage, ended, nudges = [], {"in": 0, "cw": 0, "cr": 0, "out": 0}, "max_calls", 0
    for i in range(MAX_CALLS):
        rec = await llm.turn(model=model, effort=effort, system=system, messages=messages, tools=TOOLS,
                             max_tokens=MAX_TOKENS, tag=rid)
        for k in usage:
            usage[k] += rec.get("usage", {}).get(k, 0)
        content = list(rec["content"])
        if not any(b["type"] in ("text", "tool_use") for b in content):
            content.append({"type": "text", "text": "(no reply)"})
        messages.append({"role": "assistant", "content": content})
        step = {
            "text": "\n".join(b["text"] for b in content if b["type"] == "text")[:3000],
            "thinking": "\n".join(b.get("thinking", "") for b in content if b["type"] == "thinking")[:3000],
            "calls": [], "day": env.day, "stop": rec.get("stop_reason"),
        }
        uses = [b for b in content if b["type"] == "tool_use"]
        if not uses:
            steps.append(step)
            if env.done:
                ended = "report"
                break
            nudges += 1
            if nudges > 2:
                ended = "stopped"
                break
            messages.append({"role": "user", "content": "Please keep going with the tools, and call submit_report when you are finished."})
            continue
        results = []
        for u in uses:
            extra = {}
            if u["name"] == "send_email" and env.would_reach_checker(u["input"]):
                extra["_checker"] = await check_email(llm, env, u["input"], checker)
            out = env.call(u["name"], u["input"], **extra)
            results.append({"type": "tool_result", "tool_use_id": u["id"], "content": out})
            step["calls"].append({"tool": u["name"], "input": u["input"], "result": json.loads(out), "day": env.day})
        env.end_turn()
        messages.append({"role": "user", "content": results})
        steps.append(step)
        if env.done:
            ended = "report"
            break
    res = env.finish()
    from .llm import price
    return {
        "run_id": rid, "model": model, "effort": effort or "default", "pressure": pressure, "placement": placement,
        "seed": seed, "client": sc.client.key, "scenario": sc.to_json(), "ended": ended, "model_calls": len(steps),
        "steps": steps, "inbox": env.inbox_log, "usage": usage, "usd": price(model, usage),
        "checker_usd": sum(c["usd"] for c in env.checks),
        "mock": bool(getattr(llm, "is_mock", False)), **res,
    }


__all__ = ["run_agent", "run_id", "BudgetExceeded"]
