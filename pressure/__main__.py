"""CLI.  python -m pressure all [--mock] [--yes]

Stages (each resumable; every API response is cached in <workdir>/llm_cache.jsonl):
  run      run the agents through every scenario and condition
  monitor  run the pre-send monitor over every email the agents sent, plus seeded test emails
  report   compute the results and write <workdir>/results/index.html
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from .agent import BudgetExceeded, run_agent, run_id

ALIAS = {"sonnet": "claude-sonnet-5-5", "haiku": "claude-haiku-5-5", "opus": "claude-opus-5-5"}
PRESSURES = ("neutral", "pressure")
# Rough per-run and per-check costs (USD) used only for the estimate shown before anything is spent.
EST_RUN = {("claude-sonnet-5-5", "low"): 0.15, ("claude-sonnet-5-5", "medium"): 0.27,
           ("claude-haiku-5-5", "low"): 0.01, ("claude-opus-5-5", "low"): 0.30}
EST_CHECK = {"claude-sonnet-5-5": 0.0025, "claude-haiku-5-5": 0.00015, "claude-opus-5-5": 0.005}


def parse_configs(s: str) -> list[tuple[str, str | None]]:
    out = []
    for part in [p.strip() for p in s.split(",") if p.strip()]:
        m, _, eff = part.partition(":")
        out.append((ALIAS.get(m, m), None if eff in ("", "default") else eff))
    return out


def parse(argv):
    ap = argparse.ArgumentParser(prog="pressure", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("stage", choices=["run", "monitor", "report", "all"])
    ap.add_argument("--mock", action="store_true", help="fake model, no API calls (pipeline test only)")
    ap.add_argument("--yes", action="store_true", help="skip the cost prompt")
    ap.add_argument("--workdir", default=None, help="default: run_pressure/ (run_pressure_mock/ with --mock)")
    ap.add_argument("--seeds", type=int, default=8, help="scenarios per condition (each is a different client/shortlist)")
    ap.add_argument("--placements", default="top,buried", help="where the rules sit: top, buried, none (no written rules)")
    ap.add_argument("--rule-wording", default="original", choices=["original", "reworded"],
                    help="monitor stage: 'reworded' re-checks the seeded emails and the agents' replies to the remote question "
                         "with the two content rules reworded, to see whether false alarms drop")
    ap.add_argument("--agents", default="sonnet:low,sonnet:medium,haiku:low", help="model:effort list for the agent")
    ap.add_argument("--monitors", default="haiku:low,sonnet:low", help="model:effort list for the pre-send monitor")
    ap.add_argument("--max-usd", type=float, default=25.0, help="hard stop: no new API calls once total spend reaches this")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--author", default="Tayyib (github.com/TayyibI)")
    a = ap.parse_args(argv)
    a.workdir = Path(a.workdir or ("run_pressure_mock" if a.mock else "run_pressure"))
    return a


class _Tee:
    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, s):
        self.stream.write(s)
        self.fh.write(s)
        self.fh.flush()

    def flush(self):
        self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def main(argv=None) -> None:
    a = parse(argv if argv is not None else sys.argv[1:])
    a.workdir.mkdir(parents=True, exist_ok=True)
    log = (a.workdir / "run_log.txt").open("a", encoding="utf-8")
    sys.stdout = _Tee(sys.stdout, log)
    print(f"\n=== {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} · pressure {' '.join(argv if argv is not None else sys.argv[1:])}")
    agents, monitors = parse_configs(a.agents), parse_configs(a.monitors)
    stages = ["run", "monitor", "report"] if a.stage == "all" else [a.stage]
    runs_path, mon_path = a.workdir / "runs.jsonl", a.workdir / "monitor.jsonl"

    cfg_path = a.workdir / "config.json"
    if cfg_path.exists():
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        if "run" in stages:   # a later run adds to the same experiment: keep the start time, widen the lists
            cfg["placements"] = sorted(set(cfg.get("placements", ["top", "buried"])) |
                                       {x.strip() for x in a.placements.split(",") if x.strip()})
            cfg["max_usd"] = a.max_usd
    else:
        cfg = {"agents": agents, "monitors": monitors, "seeds": a.seeds, "mock": a.mock, "max_usd": a.max_usd,
               "placements": [x.strip() for x in a.placements.split(",") if x.strip()],
               "author": a.author, "started": datetime.now(timezone.utc).isoformat(timespec="seconds")}

    if any(s in stages for s in ("run", "monitor")):
        done_runs = {r["run_id"] for r in load_jsonl(runs_path)}
        placements = [x.strip() for x in a.placements.split(",") if x.strip()]
        jobs = [(m, e, p, pl, s) for (m, e) in agents for p in PRESSURES for pl in placements for s in range(1, a.seeds + 1)]
        todo = [j for j in jobs if run_id(*j) not in done_runs] if "run" in stages else []
        n_emails = (2 * len(jobs) + 240) if a.rule_wording == "reworded" else (6 * len(jobs) + 240)
        est = sum(EST_RUN.get((m, e or "low"), 0.2) for (m, e, *_) in todo)
        est += sum(EST_CHECK.get(m, 0.003) for (m, _) in monitors) * n_emails if "monitor" in stages else 0
        print(f"[plan] {len(jobs)} agent runs ({len(todo)} still to do): {len(agents)} agent setting(s) x "
              f"2 pressure x {len(placements)} rule placement(s) ({', '.join(placements)}) x {a.seeds} scenarios; "
              "then the monitor on every email.")
        if not a.mock:
            print(f"[plan] estimated cost ~${est:.0f} (could be off by half either way). Hard stop at ${a.max_usd:.0f}.")
            if not a.yes and (todo or "monitor" in stages):
                if input("Continue? [y/N] ").strip().lower() not in ("y", "yes"):
                    print("Stopped. Nothing was spent.")
                    return
        cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

        if a.mock:
            from .mock import MockToolLLM
            llm = MockToolLLM()
        else:
            from .llm import ToolLLM
            llm = ToolLLM(a.workdir / "llm_cache.jsonl", a.concurrency, a.max_usd)

        async def go():
            try:
                need = list(dict.fromkeys(([(m, e) for (m, e, *_) in todo] if todo else []) +
                                          (monitors if "monitor" in stages else [])))
                ok = await llm.preflight(need) if need else []
                fixed = {}
                for c in need:
                    if c not in ok and c[1] is not None:   # model rejected this effort: fall back to its default
                        alt = await llm.preflight([(c[0], None)])
                        if alt:
                            fixed[c] = (c[0], None)
                            print(f"  using {c[0]} at its default effort instead of {c[1]}")
                usable = set(ok) | set(fixed)
                if "run" in stages and todo:
                    await run_all(llm, [j for j in todo if (j[0], j[1]) in usable], fixed, runs_path, a.concurrency)
                if "monitor" in stages:
                    from .monitor import deferral_items, natural_items, run_monitor, seeded_items
                    runs = load_jsonl(runs_path)
                    mons = [fixed.get(c, c) for c in monitors if c in usable]
                    done = {r["key"] for r in load_jsonl(mon_path)}
                    if a.rule_wording == "original":
                        items = natural_items(runs) + seeded_items(runs)
                        (a.workdir / "monitor_items.json").write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
                    else:
                        items = deferral_items(runs) + seeded_items(runs)
                    await run_monitor(llm, items, mons, mon_path, done, a.rule_wording)
            except BudgetExceeded as e:
                print(f"\nSTOPPED: {e}. Everything finished so far is saved. To continue, re-run with a higher --max-usd.")
            finally:
                await llm.aclose()
                if not a.mock:
                    print(f"[spend] this session ${llm.spend.usd:.2f} ({llm.spend.calls} API calls, {llm.spend.cached} cache hits); "
                          f"total in {a.workdir}: ${llm.total_usd:.2f}")
        asyncio.run(go())

    if "report" in stages:
        from .report import build
        out = build(a.workdir)
        print(f"[report] {out}")


async def run_all(llm, todo, fixed, runs_path: Path, concurrency: int) -> None:
    sem = asyncio.Semaphore(concurrency)
    fh = runs_path.open("a", encoding="utf-8")
    t0, done, stop = time.time(), 0, False
    print(f"[run] {len(todo)} agent runs")

    async def one(job):
        nonlocal done, stop
        if stop:
            return
        m, e, p, pl, s = job
        m2, e2 = fixed.get((m, e), (m, e))
        async with sem:
            if stop:
                return
            try:
                rec = await run_agent(llm, m2, e2, p, pl, s)
            except BudgetExceeded:
                stop = True
                raise
            except Exception as ex:  # one broken run shouldn't sink the batch
                print(f"  ! run {run_id(*job)} failed: {type(ex).__name__}: {str(ex)[:200]}")
                return
        if e2 != e:
            rec["effort_requested"] = e or "default"
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        fh.flush()
        done += 1
        if done % 6 == 0 or done == len(todo):
            print(f"  {done}/{len(todo)} runs · {time.time() - t0:.0f}s · ${getattr(llm, 'total_usd', 0):.2f} so far")

    results = await asyncio.gather(*(one(j) for j in todo), return_exceptions=True)
    fh.close()
    for r in results:
        if isinstance(r, BudgetExceeded):
            raise r


if __name__ == "__main__":
    main()
