# Who's worth 19 minutes? · Same Person, Different Profile

Two connected pieces of work on first-pass candidate screening:

1. **Who's worth 19 minutes?** (`app/`, deployable `site/`): an interactive research-queue simulator. When research agents are the bottleneck, which candidate should an idle agent research next? Four policies race on the same simulated pool, using first-pass labels drawn from what a real LLM screener did in the benchmark below.
2. **Same Person, Different Profile** (`twins/`): the benchmark that measured those labels. It asks whether an LLM first-pass screener judges the candidate or the way the profile is written.

## Who's worth 19 minutes?

In Metaview's fillmore case study, 720 engineers were researched over 24 days before candidate #721. His role descriptions were sparse, so the profile-only first pass scored him "good, not great". Then 19 minutes of research (58 actions) turned that into "great", and he was hired. Research is where agent-hours go. This simulator asks what order to research candidates in.

**Open it:** `site/index.html` in any browser, or double-click `open_simulator.bat`. No server or install is needed. It's one static file with no dependencies besides Google Fonts.

**Deploy it:** any static host works.
- **GitHub Pages:** push the repo, then set Settings → Pages → Source to "GitHub Actions". `.github/workflows/pages.yml` publishes `site/`.
- **Netlify:** drag `site/` onto app.netlify.com/drop.

The claude.ai Artifact version (`artifact.html`) adds one feature, "run this first pass live". It sends a profile to Claude with the benchmark's exact screening prompt, on the viewer's own account.

**What it simulates.**
- **The pool.** Candidates have a true tier, a profile type (full or titles-and-dates only) and a first-pass label. Labels are drawn from the counts measured in the kill test: how often the screener gave each label to candidates of each true tier, per profile type.
- **Research** takes a lognormal time around 19 minutes and reveals the true tier.
- **The race.** K agents per lane work in parallel. Every lane gets the same pool with the same research times; only the order differs.
- **The four policies:**
  - **Arrival order:** candidates in the order they were sourced.
  - **Label order:** great, then good, then okay, then poor. Where "needs research" sits is a setting.
  - **Learns as it goes:** Thompson sampling over label × profile-type buckets. It starts with no table and learns only from research it has finished.
  - **Calibrated:** ranks by P(great | label, profile type) per expected research-minute. It uses the measured table with +0.5 smoothing.

**Result at the defaults.** These come from 300 simulated pools of 900 candidates, with 4% great, 30% sparse and 6 agents per lane. A "#721" means a great candidate whose first pass said less than great.

| Agent-hours to find 90% of the #721s (median) | Arrival | Label order | Learns as it goes | Calibrated |
|---|---|---|---|---|
| Naive screener's labels | 286 | 286 | 178 | 145 |
| Instructed screener's labels | 285 | 249 | 187 | 132 |
| Facts-first screener's labels ("needs research" after good) | 286 | 131 | 130 | 94 |
| Facts-first screener's labels ("needs research" after great) | 286 | 94 | 130 | 94 |

- With the naive screener's labels, label order finds the #721s no faster than arrival order. It finds the obvious greats fast, then it reaches sparse profiles only when it gets to the "okay" band.
- Calibrated order beat label order in 300 of 300 pools.
- The gap narrows as sparse profiles get more common, or when sparse profiles take longer to research.
- With facts-first and "needs research" placed right after "great", the gap is zero. A well-placed flag on a well-behaved screener already gives the calibrated order. The page shows all of this live.

**Checks.**
- `tests/test_pipeline.py` runs the simulator under node, if it's installed, on hand-made counts.
- An independent Python re-implementation of the static policies matched the JavaScript medians within about 1%.

**What it is not.** It is not fillmore's ranking, data or code. Labels come from a synthetic benchmark (21 candidates, 2 repeats, Sonnet 5.5 at low effort), so read the posterior bars as directions. The calibrated lane uses the same table the simulator draws labels from, so it is a best case. The learns-as-it-goes lane is the realistic version.

**Rebuild after a new run.** `python -m twins app --quick` (or without `--quick` for the full run) writes `<run>/app/`. Copy `index.html` and `kill-test.html` into `site/` to redeploy.

---

## Same Person, Different Profile

**Does an LLM first-pass screener judge the candidate, or the way the profile is written?**

Every synthetic candidate in this benchmark appears four ways, with identical facts:

| Variant | What it is |
|---|---|
| `plain` | terse, human-style profile with every fact |
| `polished` | the same facts rewritten the way an AI writing assistant polishes a LinkedIn profile |
| `verbose` | the same facts, written at ~2.5x the length |
| `sparse` | titles, companies and dates only, with no descriptions |

Three first-pass screeners rate every version against a role brief, with several repeats each:

| Screener | How it works |
|---|---|
| `naive` | one prompt: brief + profile → great / good / okay / poor |
| `instructed` | the same, plus the standard prompt-level mitigation ("judge substance not style, treat unmentioned things as unknown, flag if it needs research") |
| `facts_first` | the fix. The LLM extracts per-criterion evidence with verbatim quotes. Quotes are verified against the profile in code. The rating is then computed deterministically from verified evidence only. Thin profiles that don't reach "great" are routed to research instead of being rated down. |

Because every comparison is within the same person, any change in rating between variants is caused by presentation alone.

## Why this question

- **The #721 near-miss.** In Metaview's published fillmore case study, the eventual hire (candidate #721) was first rated "good, not great" by a profile-only screen. The stated reason was that sparse role descriptions prevented a "great" rating. Deep research later overturned it.
- **Self-preference.** LLM screeners prefer resumes written by an LLM over human-written resumes of equal quality (Xu et al., *AI Self-preferencing in Algorithmic Hiring*, AIES 2025, arXiv:2509.00462).
- **LLM-judge biases.** LLM judges show verbosity and self-enhancement biases (Zheng et al., *Judging LLM-as-a-Judge*, NeurIPS 2023).
- **The method has precedent.** Paired resumes with known ground truth are an established way to audit LLM screeners (Castleman et al., *Measuring Validity in LLM-based Resume Screening*, IASEAI 2026).

What this repo adds: the same questions asked of a **profile-only sourcing screen**, including what happens to **sparse** profiles, plus a fix and a reusable test.

## Windows: double-click setup

1. Double-click **`setup.bat`**. It finds Python 3.10+ (including Anaconda), creates `.venv`, installs packages, runs the tests and a free practice run with a fake model, then opens the practice report. Everything it does is logged to `setup_log.txt`.
2. Double-click **`run_kill_test.bat`**. It asks for your API key once (and offers to remember it), runs the kill test, then opens the report.
3. Double-click **`run_full.bat`** for the full run.
4. Double-click **`open_simulator.bat`** to rebuild and open the research-queue simulator from your latest run.

Every run also writes `<run folder>/run_log.txt`.

## Setup by hand (macOS / Linux / Windows)

Requires Python 3.10+ and an Anthropic API key.

```bash
cd profile-twins
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...                     # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python -m pytest -q                                     # 10 tests, no API calls
```

## Run

```bash
# 1. Kill test first: 21 candidates, Sonnet only, 2 repeats. About 550 calls; the first real run cost $1.94 and took ~3 min.
python -m twins all --quick

# 2. Full run: 60 candidates, Sonnet + Haiku, 3 repeats.
#    About 4,400 calls, roughly $8-12 at the measured rate, 15-30 min.
python -m twins all

# Pipeline check with a fake model (no key, no cost; the report is stamped MOCK)
python -m twins all --mock
```

- **Before any paid call**, the run prints the planned call count and a cost estimate, and asks you to confirm.
- **A preflight call** checks your key and model IDs, so mistakes fail in seconds.
- **Interruptions are safe.** Every API response is cached in `<workdir>/llm_cache.jsonl`, so if a run stops, re-running the same command resumes for free.

**Outputs**, in `run_quick/results/` or `run/results/`:
- `index.html`: open it in a browser. It opens on one candidate written four ways with every screener's verdict, then answers four questions with charts, then lists more candidates and every metric.
- `report.md`: the same numbers as tables.
- `summary.json`: everything, machine-readable.

**Useful flags**

| Flag | Effect |
|---|---|
| `--models a,b` | screening models (default `claude-sonnet-5-5,claude-haiku-5-5`) |
| `--effort low` | effort for screening calls (default `low`, the cheap setting a high-volume first-pass screen would plausibly use). `--effort default` uses the model default (costs more). |
| `--rewrite-model` | which model writes the polished and verbose versions (default `claude-sonnet-5-5`) |
| `--repeats N` | repeats per screen |
| `--per-brief N` | candidates per role brief (3 briefs) |
| `--yes` | skip the cost prompt |
| `--concurrency N` | parallel requests (default 8; lower it if you hit rate limits) |

Model IDs and prices were checked against platform.claude.com/docs on 2026-10-13. Haiku 5.5 is listed "from" $0.10/$0.50 per million tokens, so its cost line is a lower bound.

## How to read the results

| Metric | Meaning |
|---|---|
| **Same-text repeat noise** | how often a screener disagrees with *itself* on identical text. This is the baseline every flip rate must beat. |
| **Plain vs AI-polished, label changed** | compare this with the repeat noise; the per-candidate gap is reported with a 95% interval and a paired Wilcoxon test |
| **Avg rating shift, AI-polished vs plain** | on the 0-3 scale, with a 95% bootstrap CI and a paired Wilcoxon test. Positive means polish is rewarded. |
| **#721 pattern** | of the candidates whose facts make them "great", how often the sparse version is rated below great *and not* sent to research |
| **Full profiles wrongly routed to research** | the cost of the fix. It should be near zero. |

## First result (kill test, 2026-10-14)

21 candidates, Sonnet 5.5 at low effort, 2 repeats, $1.94. Small sample, so treat these as directions to confirm with the full run.

- **AI polish did not move ratings.** Plain vs polished labels changed 2% of the time, the same as re-rating identical text; average shift +0.02 (p = 0.68). The self-preference effect reported by Xu et al. (2025) in head-to-head comparisons did not show up in this one-at-a-time setup.
- **A forced-label screen marks sparse profiles down.** The naive screener rated every great-on-paper candidate below great when only titles and dates were visible, and gave "okay" to 90% of sparse profiles regardless of the person.
- **The prompt-level fix overcorrects.** Adding "treat missing information as unknown and flag for research" sent every sparse profile to research, and also 29% of complete profiles: 0% of great candidates, 14% of good, 58% of okay, 61% of poor.
- **Facts-first routed only the thin profiles** (100% of sparse, 0% of complete). Its thin-profile rule is a word count, which this benchmark separates cleanly, so this is a best case.

## What this does and does not show

- ✅ How these three screeners, on these models, respond to presentation-only changes on a controlled synthetic benchmark.
- ✅ Whether evidence-first scoring plus research routing reduces that sensitivity.
- ❌ Anything about Metaview's production screener. It isn't tested here, and the terms of service rule out probing it. The harness is built so their screener could be plugged in internally.
- ❌ Real-world hiring outcomes. The candidates are synthetic, and the reference tier is a rubric (3 must-haves, 3 nice-to-haves), not a hiring decision.

**Known caveats**
- Facts-first scores with the same rubric that defines the reference tier, so its "agreement with reference" number is flattered by construction.
- The 60-word "thin profile" threshold for research routing is a transparent heuristic, set between the longest sparse profile (35 words) and the shortest plain one (76 words).
- Rewrites and screeners share a model family. This is realistic, since candidates use the same assistants, but it may amplify self-preference. Use `--rewrite-model` to test across models.

## Design choices worth knowing

- **Fully synthetic.** Fictional companies and candidates, with no real person's data anywhere.
- **Code, not an LLM, generates the facts,** so the ground truth is exact. Each candidate meets a chosen set of criteria, and every fact contains a number, so a dropped fact is detectable.
- **The fact-preservation check is deterministic.** An AI rewrite is accepted only if every title, company, year, number and named technology survives and no named technology is added. Rejected rewrites are excluded and counted in the report.
- **Facts-first quote verification:** a claimed piece of evidence that isn't verbatim in the profile is discarded.

## Layout

```
twins/briefs.py      role briefs, criteria, evidence templates, rubric
twins/generate.py    synthetic candidates, plain + sparse renderings
twins/rewrite.py     AI-polished / verbose rewrites + fact-preservation check
twins/screeners.py   naive, instructed, facts_first
twins/run.py         runs screeners x models x variants x repeats (resumable)
twins/analyze.py     metrics, paired tests, bootstrap CIs, twin-card selection
twins/report.py      report.md + index.html
twins/llm.py         Anthropic client (cache, retries, preflight, spend) + mock
twins/calibrate.py   label counts -> simulator data; builds the simulator page
app/sim.js           research-queue simulator (no dependencies; runs in the page and under node)
app/app_template.html  the simulator page
site/                built simulator + first test's results, ready for any static host
tests/               pipeline tests (no API calls)
docs/demo-script.md  2-minute video outline + outreach email draft
```

**Plugging in another screener:** add a branch to `screeners.screen()` that returns `{"rating", "score", "research", "reason"}`, then add its name to `SCREENERS`.
