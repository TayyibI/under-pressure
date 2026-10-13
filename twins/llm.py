"""Thin async LLM layer: Anthropic client with caching, retries and cost tracking,
plus a clearly-labelled mock used only to test the pipeline offline.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

# USD per million tokens (input, output). Source: platform.claude.com/docs/en/models/overview
# (checked 2026-10-13). Haiku is listed as "from" $0.10/$0.50, so its cost is a lower bound.
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


@dataclass
class Usage:
    calls: int = 0
    cached: int = 0
    input_tokens: dict[str, int] = field(default_factory=dict)
    output_tokens: dict[str, int] = field(default_factory=dict)

    def add(self, model: str, inp: int, out: int) -> None:
        self.calls += 1
        self.input_tokens[model] = self.input_tokens.get(model, 0) + inp
        self.output_tokens[model] = self.output_tokens.get(model, 0) + out

    def cost(self) -> float:
        total = 0.0
        for m, inp in self.input_tokens.items():
            pin, pout = PRICES.get(m, (0.0, 0.0))
            total += inp / 1e6 * pin + self.output_tokens.get(m, 0) / 1e6 * pout
        return total


class Cache:
    """Append-only JSONL cache so interrupted runs resume for free."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, dict] = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rec = json.loads(line)
                    self.data[rec["key"]] = rec
        path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = path.open("a", encoding="utf-8")

    def get(self, key: str) -> dict | None:
        return self.data.get(key)

    def put(self, key: str, rec: dict) -> None:
        rec = {"key": key, **rec}
        self.data[key] = rec
        self._fh.write(json.dumps(rec) + "\n")
        self._fh.flush()


def cache_spend(path: Path) -> float:
    """Total spend recorded in the cache, so interrupted runs are still counted."""
    if not path.exists():
        return 0.0
    u = Usage()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            u.add(r.get("model", ""), r.get("in", 0), r.get("out", 0))
    return u.cost()


def cache_key(**parts) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()


class AnthropicLLM:
    is_mock = False

    def __init__(self, cache: Cache, concurrency: int = 8):
        import anthropic  # imported lazily so --mock works without the SDK

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("ANTHROPIC_API_KEY is not set. Export it, or run with --mock to test the pipeline.")
        self._anthropic = anthropic
        self.client = anthropic.AsyncAnthropic(max_retries=0)
        self.sem = asyncio.Semaphore(concurrency)
        self.cache = cache
        self.usage = Usage()

    async def preflight(self, models: list[str], effort: str | None) -> None:
        """One tiny call per model so a bad key, model ID or parameter fails fast."""
        for m in dict.fromkeys(models):
            try:
                await self.client.messages.create(
                    model=m, max_tokens=64, messages=[{"role": "user", "content": "Reply with OK."}],
                    extra_body={"output_config": {"effort": effort}} if effort else None)
            except self._anthropic.APIStatusError as e:
                raise SystemExit(f"Preflight failed for {m} (HTTP {e.status_code}): {e.message}\n"
                                 "Check ANTHROPIC_API_KEY, the model ID (--models / --rewrite-model) and --effort.")
        print(f"  preflight ok: {', '.join(dict.fromkeys(models))}")

    async def aclose(self) -> None:
        await self.client.close()

    async def complete(self, *, task: str, model: str, system: str, user: str,
                       max_tokens: int = 1500, effort: str | None = None, sample: int = 0) -> str:
        key = cache_key(model=model, system=system, user=user, max_tokens=max_tokens,
                        effort=effort, sample=sample)
        hit = self.cache.get(key)
        if hit:
            self.usage.cached += 1
            return hit["text"]

        extra = {"output_config": {"effort": effort}} if effort else None
        delay = 2.0
        for attempt in range(8):
            try:
                async with self.sem:
                    resp = await self.client.messages.create(
                        model=model, max_tokens=max_tokens, system=system,
                        messages=[{"role": "user", "content": user}],
                        extra_body=extra,
                    )
                text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
                self.usage.add(model, resp.usage.input_tokens, resp.usage.output_tokens)
                self.cache.put(key, {"task": task, "model": model, "text": text,
                                     "in": resp.usage.input_tokens, "out": resp.usage.output_tokens})
                return text
            except (self._anthropic.RateLimitError, self._anthropic.APIConnectionError,
                    self._anthropic.InternalServerError) as e:
                wait = delay * (2 ** attempt) * (0.5 + random.random())
                print(f"  ! {type(e).__name__}, retrying in {wait:.0f}s")
                await asyncio.sleep(min(wait, 90))
            except self._anthropic.APIStatusError as e:
                if e.status_code in (429, 500, 502, 503, 504, 529):
                    wait = delay * (2 ** attempt) * (0.5 + random.random())
                    print(f"  ! HTTP {e.status_code}, retrying in {wait:.0f}s")
                    await asyncio.sleep(min(wait, 90))
                else:
                    raise
        raise RuntimeError(f"giving up after retries ({task}, {model})")


class MockLLM:
    """Deterministic fake model. Exists ONLY to test plumbing; its 'results' mean nothing.

    It deliberately bakes in a style bias and a sparsity penalty so every code path
    (flips, downgrades, research flags) gets exercised. Reports built from mock runs
    carry a MOCK banner.
    """
    is_mock = True

    def __init__(self, cache: Cache | None = None, concurrency: int = 8):
        self.usage = Usage()

    async def preflight(self, models, effort) -> None:
        print("  preflight skipped (mock)")

    async def aclose(self) -> None:
        pass

    async def complete(self, *, task: str, model: str, system: str, user: str,
                       max_tokens: int = 1500, effort: str | None = None, sample: int = 0) -> str:
        await asyncio.sleep(0)
        self.usage.add("mock", len(user) // 4, 120)  # no price entry -> $0
        rng = random.Random(cache_key(task=task, model=model, user=user, sample=sample))
        profile = _between(user, "<profile>", "</profile>")
        if task == "rewrite_polished":
            out = []
            for line in profile.splitlines():
                if line.startswith("- "):
                    out.append("- Successfully " + line[2].lower() + line[3:] + ", delivering measurable impact")
                else:
                    out.append(line)
            out.insert(2, "Accomplished, product-minded engineer who cares deeply about craft and outcomes.")
            return "\n".join(out)
        if task == "rewrite_verbose":
            out = []
            for line in profile.splitlines():
                out.append(line)
                if line.startswith("- "):
                    out.append("  This involved close collaboration with stakeholders across the organisation, "
                               "careful planning, iterative delivery and a strong focus on quality and reliability.")
            return "\n".join(out)

        from .briefs import BRIEFS, RATINGS, reference_tier
        bid = _between(user, "Brief-ID: ", "\n").strip()
        brief = BRIEFS[bid]
        found = _mock_detect(brief, profile)
        if task == "extract":
            crits = []
            for c in brief.criteria:
                q = found.get(c.id)
                crits.append({"id": c.id, "status": "evidenced" if q else "not_stated", "quote": q or ""})
            if rng.random() < 0.05 and crits:  # occasionally hallucinate a quote, to exercise verification
                crits[0] = {"id": crits[0]["id"], "status": "evidenced", "quote": "invented evidence that is not in the profile"}
            return json.dumps({"criteria": crits})

        musts = sum(1 for c in brief.musts if c.id in found)
        nices = sum(1 for c in brief.nices if c.id in found)
        score = RATINGS.index(reference_tier(musts, nices))
        words = len(profile.split())
        bias = 0.45 if task == "screen_naive" else 0.2
        if words > 150 and rng.random() < bias:
            score += 1
        if rng.random() < 0.08:
            score += rng.choice([-1, 1])
        score = max(0, min(3, score))
        payload = {"rating": RATINGS[score], "reason": "mock reasoning"}
        if task == "screen_instructed":
            payload["needs_research"] = words < 60 and rng.random() < 0.6
        return json.dumps(payload)


_MOCK_PATTERNS = {
    "ts_react": r"TypeScript|React", "design_systems": r"design system|component library",
    "product_ownership": r"end to end|launch of", "graphics": r"WebGL|GLSL", "early_stage": r"seed-stage",
    "mentoring": r"Mentored|squad of", "go_lang": r"\bGo\b", "kubernetes": r"Kubernetes",
    "distributed_scale": r"million (events|transactions)", "postgres": r"Postgres", "incident": r"incident|on-call",
    "terraform": r"Terraform", "python": r"Python", "llm_prod": r"RAG|LLM agent",
    "evals": r"evaluation", "pytorch": r"PyTorch", "vector_db": r"pgvector|Qdrant", "fastapi": r"FastAPI",
}


def _mock_detect(brief, profile: str) -> dict[str, str]:
    found = {}
    for c in brief.criteria:
        pat = _MOCK_PATTERNS[c.id]
        for line in profile.splitlines():
            m = re.search(pat, line)
            if m:
                found[c.id] = line.strip().lstrip("- ").strip()
                break
    return found


def _between(s: str, a: str, b: str) -> str:
    i = s.find(a)
    if i < 0:
        return ""
    i += len(a)
    j = s.find(b, i)
    return s[i:j if j >= 0 else None]


def parse_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply (tolerates code fences/prose)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    return json.loads(text[start:end + 1])


def make_llm(mock: bool, cache_dir: Path, concurrency: int):
    if mock:
        return MockLLM()
    return AnthropicLLM(Cache(cache_dir / "llm_cache.jsonl"), concurrency=concurrency)


class Progress:
    def __init__(self, total: int, label: str):
        self.total, self.done, self.label, self.t0 = total, 0, label, time.time()

    def tick(self) -> None:
        self.done += 1
        step = max(25, self.total // 10)
        if self.done == self.total or self.done % step == 0:
            el = time.time() - self.t0
            print(f"  {self.label}: {self.done}/{self.total} ({el:.0f}s)")
