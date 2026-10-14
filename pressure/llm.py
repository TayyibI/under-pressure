"""Tool-use client for the agent and monitor calls: prompt caching, a resumable response cache,
retries, a hard spend cap, and cost tracking that prices cache writes and reads separately."""
from __future__ import annotations

import asyncio
import json
import os
import random
from dataclasses import dataclass, field
from pathlib import Path

from twins.llm import Cache, cache_key

# USD per million tokens: base input, 5-minute cache write, cache read, output.
# Source: platform.claude.com/docs/en/build-with-claude/prompt-caching and models overview (checked 2026-10-14).
# Haiku 5.5's input price applies up to 100k prompt tokens; prompts here are far below that.
PRICES = {
    "claude-opus-5-5": (4.0, 5.0, 0.20, 20.0),
    "claude-sonnet-5-5": (2.0, 2.50, 0.10, 10.0),
    "claude-haiku-5-5": (0.10, 0.125, 0.01, 0.50),
}


class BudgetExceeded(Exception):
    pass


def price(model: str, u: dict) -> float:
    p_in, p_w, p_r, p_out = PRICES.get(model, (0, 0, 0, 0))
    return (u.get("in", 0) * p_in + u.get("cw", 0) * p_w + u.get("cr", 0) * p_r + u.get("out", 0) * p_out) / 1e6


@dataclass
class Spend:
    calls: int = 0
    cached: int = 0
    by_model: dict = field(default_factory=dict)

    def add(self, model: str, u: dict) -> None:
        self.calls += 1
        m = self.by_model.setdefault(model, {"in": 0, "cw": 0, "cr": 0, "out": 0, "usd": 0.0})
        for k in ("in", "cw", "cr", "out"):
            m[k] += u.get(k, 0)
        m["usd"] += price(model, u)

    @property
    def usd(self) -> float:
        return sum(m["usd"] for m in self.by_model.values())


def cache_total(path: Path) -> float:
    if not path.exists():
        return 0.0
    tot = 0.0
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            tot += price(r.get("model", ""), r.get("usage", {}))
    return tot


def _clean(block) -> dict | None:
    """Keep only what the API accepts back in an assistant turn."""
    b = block if isinstance(block, dict) else block.model_dump(exclude_none=True)
    t = b.get("type")
    if t == "text":
        return {"type": "text", "text": b.get("text", "")} if b.get("text") else None
    if t == "tool_use":
        return {"type": "tool_use", "id": b["id"], "name": b["name"], "input": b.get("input") or {}}
    if t == "thinking":
        return {"type": "thinking", "thinking": b.get("thinking", ""), "signature": b.get("signature", "")}
    if t == "redacted_thinking":
        return {"type": "redacted_thinking", "data": b.get("data", "")}
    return None


class ToolLLM:
    is_mock = False

    def __init__(self, cache_path: Path, concurrency: int = 8, max_usd: float = 25.0):
        import anthropic
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set. Run run_under_pressure.bat (it asks for the key), or use --mock.")
        self._a = anthropic
        self.client = anthropic.AsyncAnthropic(max_retries=0, timeout=600)
        self.sem = asyncio.Semaphore(concurrency)
        self.cache = Cache(cache_path)
        self.spend = Spend()
        self.prior_usd = cache_total(cache_path)   # money already spent by earlier, interrupted runs
        self.max_usd = max_usd
        self.auto_cache = True

    @property
    def total_usd(self) -> float:
        return self.prior_usd + self.spend.usd

    async def preflight(self, configs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
        """One tiny tool-use call per (model, effort). Returns the configs that work."""
        ok = []
        tool = {"name": "ping", "description": "Reply ping.", "input_schema": {"type": "object", "properties": {}}}
        for model, effort in dict.fromkeys(configs):
            for attempt in range(2):
                body = {"cache_control": {"type": "ephemeral"}} if self.auto_cache else {}
                if effort:
                    body["output_config"] = {"effort": effort}
                try:
                    await self.client.messages.create(model=model, max_tokens=256, tools=[tool],
                                                      messages=[{"role": "user", "content": "Call the ping tool."}],
                                                      extra_body=body or None)
                    ok.append((model, effort))
                    print(f"  preflight ok: {model} effort={effort or 'default'}")
                    break
                except self._a.APIStatusError as e:
                    if attempt == 0 and self.auto_cache and "cache" in str(e.message).lower():
                        self.auto_cache = False   # the API refused top-level caching: run without it (costs more)
                        print("  note: prompt caching was refused, continuing without it (the spend cap still applies)")
                        continue
                    print(f"  preflight FAILED for {model} effort={effort or 'default'} (HTTP {e.status_code}): {e.message}")
                    break
        return ok

    async def aclose(self) -> None:
        await self.client.close()

    async def turn(self, *, model: str, effort: str | None, system: str, messages: list, tools: list | None,
                   max_tokens: int, tag: str) -> dict:
        key = cache_key(model=model, effort=effort, system=system, messages=messages, tools=tools, max_tokens=max_tokens)
        hit = self.cache.get(key)
        if hit:
            self.spend.cached += 1
            return hit
        if self.total_usd >= self.max_usd:
            raise BudgetExceeded(f"spend cap ${self.max_usd:.2f} reached")
        body = {"cache_control": {"type": "ephemeral"}} if self.auto_cache else {}
        if effort:
            body["output_config"] = {"effort": effort}
        kw = dict(model=model, max_tokens=max_tokens, system=system, messages=messages, extra_body=body or None)
        if tools:
            kw["tools"] = tools
        delay = 2.0
        for attempt in range(8):
            try:
                async with self.sem:
                    resp = await self.client.messages.create(**kw)
                u = resp.usage
                usage = {"in": u.input_tokens or 0, "cw": getattr(u, "cache_creation_input_tokens", 0) or 0,
                         "cr": getattr(u, "cache_read_input_tokens", 0) or 0, "out": u.output_tokens or 0}
                rec = {"model": model, "tag": tag, "stop_reason": resp.stop_reason,
                       "content": [c for c in (_clean(b) for b in resp.content) if c], "usage": usage}
                self.spend.add(model, usage)
                self.cache.put(key, rec)
                return rec
            except (self._a.RateLimitError, self._a.APIConnectionError, self._a.InternalServerError) as e:
                wait = delay * (2 ** attempt) * (0.5 + random.random())
                print(f"  ! {type(e).__name__}, retrying in {wait:.0f}s")
                await asyncio.sleep(min(wait, 90))
            except self._a.APIStatusError as e:
                if e.status_code in (429, 500, 502, 503, 504, 529):
                    wait = delay * (2 ** attempt) * (0.5 + random.random())
                    print(f"  ! HTTP {e.status_code}, retrying in {wait:.0f}s")
                    await asyncio.sleep(min(wait, 90))
                else:
                    raise
        raise RuntimeError(f"giving up after retries ({tag})")
