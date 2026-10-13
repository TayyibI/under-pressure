"""CLI.  python -m twins all [--quick] [--mock] [--yes]

Stages (each resumable; LLM calls are cached in <workdir>/llm_cache.jsonl):
  generate  build synthetic candidates + plain/sparse profiles (no API calls)
  rewrite   LLM rewrites (polished, verbose) with fact-preservation check
  screen    run screeners x models x variants x repeats
  report    compute metrics, write results/report.md + results/index.html
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import analyze, generate, report, rewrite, run
from .llm import PRICES, cache_spend, make_llm
from .screeners import SCREENERS

DEFAULT_MODELS = ["claude-sonnet-5-5", "claude-haiku-5-5"]
QUICK = {"per_brief": 7, "models": ["claude-sonnet-5-5"], "repeats": 2}
FULL = {"per_brief": 20, "models": DEFAULT_MODELS, "repeats": 3}
# Rough per-call token guess used only for the pre-run estimate (actual spend is tracked from API usage).
EST_IN, EST_OUT = 1300, 700


def parse(argv):
    ap = argparse.ArgumentParser(prog="twins", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["generate", "rewrite", "screen", "report", "all"])
    ap.add_argument("--quick", action="store_true", help="kill test: 21 candidates, Sonnet only, 2 repeats")
    ap.add_argument("--mock", action="store_true", help="fake model, no API calls (pipeline test only)")
    ap.add_argument("--workdir", default=None, help="default: run/ (or run_quick/, run_mock/)")
    ap.add_argument("--per-brief", type=int, default=None)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--models", default=None, help="comma-separated model IDs")
    ap.add_argument("--screeners", default=",".join(SCREENERS))
    ap.add_argument("--repeats", type=int, default=None)
    ap.add_argument("--effort", default="low", help="low|medium|high|default (screening calls)")
    ap.add_argument("--rewrite-model", default="claude-sonnet-5-5")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--yes", action="store_true", help="skip the cost confirmation")
    a = ap.parse_args(argv)
    preset = QUICK if a.quick else FULL
    a.per_brief = a.per_brief or preset["per_brief"]
    a.models = a.models.split(",") if a.models else preset["models"]
    a.repeats = a.repeats or preset["repeats"]
    a.screeners = [s for s in a.screeners.split(",") if s]
    a.effort = None if a.effort == "default" else a.effort
    if a.workdir is None:
        a.workdir = "run_mock" if a.mock else ("run_quick" if a.quick else "run")
    a.workdir = Path(a.workdir)
    return a


def estimate(jobs: int, models: list[str], screeners: list[str]) -> float:
    per_model = jobs / max(1, len(models))
    total = 0.0
    for m in models:
        pin, pout = PRICES.get(m, (2.0, 10.0))
        total += per_model * (EST_IN / 1e6 * pin + EST_OUT / 1e6 * pout)
    return total


def main(argv=None) -> None:
    a = parse(argv if argv is not None else sys.argv[1:])
    data_dir, res_dir = a.workdir / "data", a.workdir / "results"
    data_dir.mkdir(parents=True, exist_ok=True)
    cfg_path = a.workdir / "config.json"
    stages = ["generate", "rewrite", "screen", "report"] if a.stage == "all" else [a.stage]

    if "generate" in stages:
        if (data_dir / "truth.json").exists():
            print(f"[generate] {data_dir}/truth.json exists, keeping it (delete the workdir to regenerate)")
        else:
            people = generate.generate(a.per_brief, a.seed)
            generate.save(people, data_dir)
            print(f"[generate] {len(people)} synthetic candidates -> {data_dir}")

    llm = None
    if any(s in stages for s in ("rewrite", "screen")):
        # Ask once, up front, before any paid call. Upper bound: every candidate has all four variants.
        if not a.mock:
            n_people = len(json.loads((data_dir / "truth.json").read_text()))
            calls = n_people * 4 * len(a.screeners) * len(a.models) * a.repeats if "screen" in stages else 0
            est = estimate(calls, a.models, a.screeners) + (n_people * 2 * 0.03 if "rewrite" in stages else 0)
            print(f"[plan] up to {calls} screening calls on {', '.join(a.models)}"
                  + (f" + {n_people * 2} rewrites" if "rewrite" in stages else "")
                  + f"; rough estimate ${est:.2f}. Cached calls are free; real spend is printed at the end.")
            if not a.yes and input("Continue? [y/N] ").strip().lower() != "y":
                print("Stopped before any API calls.")
                return
        llm = make_llm(a.mock, a.workdir, a.concurrency)

    async def llm_stages() -> None:
        # One event loop for every API call: the async HTTP client must not outlive its loop.
        need = ([a.rewrite_model] if "rewrite" in stages else []) + (a.models if "screen" in stages else [])
        await llm.preflight(need, a.effort)
        if "rewrite" in stages:
            people = generate.load_people(data_dir)
            print(f"[rewrite] AI-polished and verbose versions with {a.rewrite_model}")
            await rewrite.rewrite_all(llm, people, data_dir, a.rewrite_model)
        if "screen" in stages:
            profiles = json.loads((data_dir / "profiles.json").read_text())
            cfg = {"models": a.models, "screeners": a.screeners, "repeats": a.repeats, "effort": a.effort,
                   "mock": a.mock, "per_brief": a.per_brief, "seed": a.seed, "rewrite_model": a.rewrite_model}
            cfg_path.write_text(json.dumps(cfg, indent=2))
            print(f"[screen] {', '.join(a.screeners)} x {', '.join(a.models)} x {a.repeats} repeats")
            await run.run_screens(llm, profiles, a.workdir / "results.jsonl", a.screeners, a.models,
                                  a.repeats, a.effort)

    if llm is not None:
        try:
            asyncio.run(llm_stages())
        finally:
            print(f"[spend] this run ${llm.usage.cost():.2f} ({llm.usage.calls} API calls, "
                  f"{llm.usage.cached} cache hits); total so far in {a.workdir}: "
                  f"${cache_spend(a.workdir / 'llm_cache.jsonl'):.2f}")

    if "report" in stages:
        cfg = json.loads(cfg_path.read_text())
        res = analyze.analyze(a.workdir / "results.jsonl", data_dir, cfg["models"], cfg["screeners"], cfg["repeats"])
        meta_path = data_dir / "rewrite_meta.json"
        rmeta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        spend = cache_spend(a.workdir / "llm_cache.jsonl")
        summary = {
            "meta": {
                "mock": cfg["mock"], "models": cfg["models"], "screeners": cfg["screeners"],
                "repeats": cfg["repeats"], "effort": cfg["effort"],
                "n_people": len(json.loads((data_dir / "truth.json").read_text())),
                "generator_model": rmeta.get("generator_model", cfg["rewrite_model"]),
                "failed_rewrites": len(rmeta.get("failed_rewrites", {})),
                "cost_usd": spend,
                "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            },
            **res,
        }
        report.write_all(summary, res_dir)
        print(f"[report] {res_dir}/index.html and {res_dir}/report.md")
        for line in report.headline_lines(summary):
            print("  " + line)


if __name__ == "__main__":
    main()
