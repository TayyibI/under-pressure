"""Run every screener x model x variant x repeat over the benchmark."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from .llm import Progress
from .screeners import screen

VARIANTS = ("plain", "polished", "verbose", "sparse")


def plan_jobs(profiles: dict, screeners, models, repeats: int, limit_ids: set[str] | None = None):
    jobs = []
    for pid, prof in profiles.items():
        if limit_ids and pid not in limit_ids:
            continue
        for variant in VARIANTS:
            if variant not in prof:
                continue
            for s in screeners:
                for m in models:
                    for r in range(repeats):
                        jobs.append((pid, prof["brief_id"], variant, s, m, r))
    return jobs


async def run_screens(llm, profiles: dict, out_path: Path, screeners, models, repeats: int,
                      effort: str | None, limit_ids: set[str] | None = None) -> int:
    jobs = plan_jobs(profiles, screeners, models, repeats, limit_ids)
    done_keys = set()
    if out_path.exists():
        for line in out_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                if "error" not in d:
                    done_keys.add((d["person"], d["variant"], d["screener"], d["model"], d["repeat"]))
    todo = [j for j in jobs if (j[0], j[2], j[3], j[4], j[5]) not in done_keys]
    print(f"  {len(jobs)} screening jobs planned, {len(todo)} to run")
    prog = Progress(len(todo), "screens")
    fh = out_path.open("a", encoding="utf-8")

    async def one(pid, bid, variant, s, m, r):
        try:
            res = await screen(llm, s, m, bid, profiles[pid][variant], sample=r, effort=effort)
        except Exception as e:  # keep going; errors are reported, not hidden
            res = {"error": f"{type(e).__name__}: {e}"[:300]}
        rec = {"person": pid, "brief": bid, "variant": variant, "screener": s, "model": m, "repeat": r, **res}
        fh.write(json.dumps(rec) + "\n")
        fh.flush()
        prog.tick()

    await asyncio.gather(*(one(*j) for j in todo))
    fh.close()
    return len(todo)
