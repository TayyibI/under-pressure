# Same Person, Different Profile

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

## Setup (about 5 minutes)

Requires Python 3.10+ and an Anthropic API key.

```bash
cd profile-twins
python3 -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...                     # Windows PowerShell: $env:ANTHROPIC_API_KEY="sk-ant-..."
python -m pytest -q                                     # 9 tests, no API calls
```

## Run

```bash
# 1. Kill test first: 21 candidates, Sonnet only, 2 repeats. About 500 calls, roughly $6, ~10 min.
python -m twins all --quick

# 2. Full run if the kill test shows a signal: 60 candidates, Sonnet + Haiku, 3 repeats.
#    About 4,300 calls, roughly $25, 30-60 min.
python -m twins all

# Pipeline check with a fake model (no key, no cost; the report is stamped MOCK)
python -m twins all --mock
```

- **Before any paid call**, the run prints the planned call count and a cost estimate, and asks you to confirm.
- **A preflight call** checks your key and model IDs, so mistakes fail in seconds.
- **Interruptions are safe.** Every API response is cached in `<workdir>/llm_cache.jsonl`, so if a run stops, re-running the same command resumes for free.

**Outputs**, in `run_quick/results/` or `run/results/`:
- `index.html`: open it in a browser. It has the headline numbers, the chart, every metric, and "twin cards" showing the same candidate four ways.
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
| **Label differs across any style** | how often plain, polished and verbose (same facts) get different labels |
| **Avg rating shift, AI-polished vs plain** | on the 0-3 scale, with a 95% bootstrap CI and a paired Wilcoxon test. Positive means polish is rewarded. |
| **#721 pattern** | of the candidates whose facts make them "great", how often the sparse version is rated below great *and not* sent to research |
| **Full profiles wrongly routed to research** | the cost of the fix. It should be near zero. |

**Kill-test decision.** The story is alive if, for the naive screener, at least one of these holds:
- (a) style flips clearly exceed the repeat noise, about 10+ points higher;
- (b) the polish shift's CI excludes zero;
- (c) the #721 pattern is substantial, about 30% or more.

The fix is shown to work if facts-first cuts those numbers without routing full profiles to research.

**If none of this shows up, that's a real finding too:** "current Claude models are robust to presentation on this benchmark." Don't stretch the numbers.

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
tests/               pipeline tests (no API calls)
docs/demo-script.md  2-minute video outline + outreach email draft
```

**Plugging in another screener:** add a branch to `screeners.screen()` that returns `{"rating", "score", "research", "reason"}`, then add its name to `SCREENERS`.
