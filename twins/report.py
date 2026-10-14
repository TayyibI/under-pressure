"""Write results/summary.json, results/report.md and results/index.html."""
from __future__ import annotations

import html
import json
from pathlib import Path

from .briefs import BRIEFS

SCREENER_NAMES = {"naive": "Naive prompt", "instructed": "Prompt-patched", "facts_first": "Facts-first (fix)"}
VARIANT_NAMES = {"plain": "Plain", "polished": "AI-polished", "verbose": "Verbose", "sparse": "Sparse"}


def pct(x) -> str:
    return "n/a" if x is None else f"{100 * x:.0f}%"


def num(x, d: int = 2) -> str:
    return "n/a" if x is None else f"{x:+.{d}f}"


def ci(c) -> str:
    if not c or c[0] != c[0]:
        return "n/a"
    return f"{c[0]:+.2f} to {c[1]:+.2f}"


def headline_lines(summary: dict) -> list[str]:
    meta = summary["meta"]
    out = []
    for m in meta["models"]:
        met = summary["metrics"].get(m, {})
        nv, ff = met.get("naive"), met.get("facts_first")
        if nv:
            out.append(
                f"[{m}] Naive screener: plain vs AI-polished labels differed {pct(nv['flip_plain_polished'])} of the time, "
                f"vs {pct(nv['noise_floor'])} when re-rating identical text (excess {num(nv['excess_polished'])}, "
                f"95% CI {ci(nv['excess_polished_ci'])}). AI polish shifted the average rating by "
                f"{num(nv['delta_polished'])} points (95% CI {ci(nv['delta_polished_ci'])}, Wilcoxon p={nv['delta_polished_p']:.3g})."
            )
            out.append(
                f"[{m}] Sparse profiles: reference-'great' candidates rated below great without being sent to research "
                f"{pct(nv['pattern_721'])} of the time (n={nv.get('n_obs_great', 'n/a')} screens)."
            )
        if ff:
            out.append(
                f"[{m}] Facts-first: plain vs polished {pct(ff['flip_plain_polished'])} vs noise {pct(ff['noise_floor'])}; "
                f"polish shift {num(ff['delta_polished'])}; #721 pattern {pct(ff['pattern_721'])}; sparse sent to research "
                f"{pct(ff['sparse_research'])}; full profiles wrongly sent {pct(ff['false_research'])}."
            )
    return out


def write_markdown(summary: dict, path: Path) -> None:
    meta = summary["meta"]
    lines = ["# Same Person, Different Profile: results", ""]
    if meta["mock"]:
        lines += ["> **MOCK RUN. These numbers come from a fake model used to test the pipeline. They mean nothing.**", ""]
    lines += [
        f"- Synthetic candidates: {meta['n_people']} across {len(BRIEFS)} role briefs",
        f"- Screening models: {', '.join(meta['models'])} (effort: {meta['effort'] or 'model default'})",
        f"- Rewrite model: {meta.get('generator_model')}; rewrites rejected by the fact check: {meta['failed_rewrites']}",
        f"- Repeats per screen: {meta['repeats']}; failed screens: {summary['errors']}",
        f"- Approx. API spend this run: ${meta['cost_usd']:.2f}",
        "- Mean words per variant: " + ", ".join(f"{VARIANT_NAMES[v]} {w:.0f}" for v, w in summary["word_counts"].items()),
        "", "## Headline", "", *[f"- {s}" for s in headline_lines(summary)], "",
    ]
    rows = [
        ("Same-text repeat noise", "noise_floor", pct),
        ("Label flips, plain vs AI-polished", "flip_plain_polished", pct),
        ("Label flips, plain vs verbose", "flip_plain_verbose", pct),
        ("Excess over noise, plain vs AI-polished", "excess_polished", num),
        ("  95% CI", "excess_polished_ci", ci),
        ("  Wilcoxon p", "excess_polished_p", lambda x: f"{x:.3g}"),
        ("Excess over noise, plain vs verbose", "excess_verbose", num),
        ("Label differs across any style (3-way)", "flip_any_style", pct),
        ("Rating shift, AI-polished vs plain", "delta_polished", num),
        ("  95% CI", "delta_polished_ci", ci),
        ("  Wilcoxon p", "delta_polished_p", lambda x: f"{x:.3g}"),
        ("Rating shift, verbose vs plain", "delta_verbose", num),
        ("Rating shift, sparse vs plain", "delta_sparse", num),
        ("Sparse rated lower, not sent to research", "sparse_downgrade", pct),
        ("Sparse routed to research", "sparse_research", pct),
        ("#721 pattern (great -> below great when sparse)", "pattern_721", pct),
        ("Full profiles wrongly routed to research", "false_research", pct),
        ("Agreement with reference tier (plain)", "agree_ref_plain", pct),
        ("Within one tier of reference (plain)", "within1_ref_plain", pct),
        ("Kendall tau, plain vs polished ranking", "kendall_tau_plain_vs_polished",
         lambda x: "n/a" if x is None else f"{x:.2f}"),
    ]
    for m, by_s in summary["metrics"].items():
        screeners = list(by_s)
        lines += [f"## {m}", "", "| Metric | " + " | ".join(SCREENER_NAMES[s] for s in screeners) + " |",
                  "|---|" + "---|" * len(screeners)]
        for label, key, fmt in rows:
            lines.append(f"| {label} | " + " | ".join(fmt(by_s[s][key]) for s in screeners) + " |")
        lines.append("")
    lines += ["## Method and limits", "", METHOD_MD]
    path.write_text("\n".join(lines), encoding="utf-8")


METHOD_MD = """\
- Every candidate is synthetic and every comparison is within the same person: the four versions of a
  profile carry identical facts except `sparse`, which keeps only titles, companies and dates.
- AI-polished and verbose versions are LLM rewrites that pass a deterministic check: every title, company,
  year, number and named technology must survive, and no named technology may be introduced.
- Repeat noise is how often a screener disagrees with itself when rating the same text twice. A style flip
  rate only means something to the extent it exceeds that. The gap is averaged per candidate, with a 95%
  bootstrap interval over candidates and a paired Wilcoxon test; an effect is reported only when both agree.
- Facts-first sends a profile to research when it is under 60 words and not already rated great. On this
  benchmark that threshold separates sparse from complete profiles cleanly, so its routing accuracy here is a
  best case.
- The reference tier comes from a published rubric applied to the generated facts (3 must-haves, 3
  nice-to-haves). Agreement with it is a sanity check, not the headline. Facts-first scores with that same
  rubric, so its agreement figure is flattered by construction and should not be compared head to head.
- These screeners are built here. Nothing in this repo measures Metaview's production screener; the
  harness is designed so that screener could be plugged in.
- Prior work this builds on: Xu et al., "AI Self-preferencing in Algorithmic Hiring" (AIES 2025,
  arXiv 2509.00462); Zheng et al., "Judging LLM-as-a-Judge" (NeurIPS 2023); Castleman et al.,
  "Measuring Validity in LLM-based Resume Screening" (IASEAI 2026).
"""


def write_html(summary: dict, path: Path) -> None:
    data = json.dumps(summary).replace("</", "<\\/")
    briefs = json.dumps({b.id: {"title": b.title, "company": b.company} for b in BRIEFS.values()})
    template = (Path(__file__).parent / "report_template.html").read_text(encoding="utf-8")
    page = template.replace("__DATA__", data).replace("__BRIEFS__", briefs)
    page = page.replace("__METHOD__", "".join(
        f"<li>{html.escape(line.strip()[2:].replace('`', '').replace('*', ''))}</li>"
        for line in METHOD_MD.replace("\n  ", " ").splitlines() if line.strip().startswith("- ")))
    path.write_text(page, encoding="utf-8")


def write_all(summary: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    write_markdown(summary, out_dir / "report.md")
    write_html(summary, out_dir / "index.html")
