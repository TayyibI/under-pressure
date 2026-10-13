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


def headline_lines(summary: dict) -> list[str]:
    meta = summary["meta"]
    m = meta["models"][0]
    met = summary["metrics"].get(m, {})
    out = []
    nv, ff = met.get("naive"), met.get("facts_first")
    if nv:
        out.append(
            f"Naive screener ({m}): labels changed across writing styles for {pct(nv['flip_any_style'])} of screens "
            f"(same-text repeat noise: {pct(nv['noise_floor'])}). AI-polished vs plain shifted the average rating by "
            f"{num(nv['delta_polished'])} points (Wilcoxon p={nv['delta_polished_p']:.3g})."
        )
        out.append(
            f"Sparse profiles: rated below their full version {pct(nv['sparse_downgrade'])} of the time; "
            f"reference-'great' candidates rated below great when sparse (the #721 pattern): {pct(nv['pattern_721'])}."
        )
    if ff:
        out.append(
            f"Facts-first: style flips {pct(ff['flip_any_style'])}, AI-polished shift {num(ff['delta_polished'])}, "
            f"sparse downgrades {pct(ff['sparse_downgrade'])} (sparse profiles routed to research {pct(ff['sparse_research'])}; "
            f"full profiles wrongly routed {pct(ff['false_research'])})."
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
        ("Label differs across any style", "flip_any_style", pct),
        ("Rating shift, AI-polished vs plain", "delta_polished", num),
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
    path.write_text("\n".join(lines))


METHOD_MD = """\
- Every candidate is synthetic and every comparison is within the same person: the four versions of a
  profile carry identical facts except `sparse`, which keeps only titles, companies and dates.
- AI-polished and verbose versions are LLM rewrites that pass a deterministic check: every title, company,
  year, number and named technology must survive, and no named technology may be introduced.
- `noise_floor` is how often a screener disagrees with itself on the *same* text. Style flip rates only
  mean something to the extent they exceed it.
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
    briefs = json.dumps({b.id: b.title for b in BRIEFS.values()})
    page = HTML.replace("__DATA__", data).replace("__BRIEFS__", briefs)
    page = page.replace("__METHOD__", "".join(
        f"<li>{html.escape(line.strip()[2:].replace('`', '').replace('*', ''))}</li>"
        for line in METHOD_MD.replace("\n  ", " ").splitlines() if line.strip().startswith("- ")))
    path.write_text(page)


def write_all(summary: dict, out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    write_markdown(summary, out_dir / "report.md")
    write_html(summary, out_dir / "index.html")


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Same Person, Different Profile</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7; --surface-1: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
  --grid: #e1e0d9; --axis: #c3c2b7; --border: rgba(11,11,11,0.10);
  --s1: #2a78d6; --s2: #eb6834; --s3: #1baf7a; --flag: #fff4d6; --flag-ink: #6b4b00;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page: #0d0d0d; --surface-1: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
    --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
    --s1: #3987e5; --s2: #d95926; --s3: #199e70; --flag: #3a2f12; --flag-ink: #f3d38a;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page: #0d0d0d; --surface-1: #1a1a19; --ink: #f0efec; --ink-2: #c3c2b7; --muted: #898781;
  --grid: #2c2c2a; --axis: #383835; --border: rgba(255,255,255,0.10);
  --s1: #3987e5; --s2: #d95926; --s3: #199e70; --flag: #3a2f12; --flag-ink: #f3d38a;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink);
  font: 15px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
main { max-width: 1080px; margin: 0 auto; padding: 32px 16px 64px; }
h1 { font-size: 28px; line-height: 1.2; margin: 0 0 6px; letter-spacing: -0.01em; }
h2 { font-size: 18px; margin: 40px 0 12px; }
p.lede { color: var(--ink-2); max-width: 760px; margin: 0 0 20px; }
.mock { background: #d03b3b; color: #fff; padding: 12px 16px; border-radius: 8px; font-weight: 700; margin-bottom: 20px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.controls { display: flex; gap: 12px; align-items: center; margin: 8px 0 16px; flex-wrap: wrap; }
select { font: inherit; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border); background: var(--surface-1); color: var(--ink); }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(220px, 100%), 1fr)); gap: 12px; }
.tile .label { color: var(--ink-2); font-size: 13px; }
.tile .value { font-size: 30px; font-weight: 650; margin: 4px 0 2px; }
.tile .vs { color: var(--muted); font-size: 13px; }
.legend { display: flex; gap: 16px; flex-wrap: wrap; font-size: 13px; color: var(--ink-2); margin-bottom: 8px; }
.legend span::before { content: ""; display: inline-block; width: 12px; height: 12px; border-radius: 3px;
  background: var(--c); margin-right: 6px; vertical-align: -1px; }
svg text { fill: var(--muted); font-size: 12px; }
.bar { transition: opacity .1s; }
.bar:hover, .bar:focus { opacity: .8; outline: none; }
#tip { position: fixed; pointer-events: none; background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 8px 10px; font-size: 13px; box-shadow: 0 4px 16px rgba(0,0,0,.12); display: none; z-index: 9; }
#tip strong { font-size: 15px; display: block; }
#tip .k { display: inline-block; width: 14px; height: 2px; background: var(--c); vertical-align: 3px; margin-right: 6px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 7px 10px; border-bottom: 1px solid var(--grid); vertical-align: top; }
th { color: var(--ink-2); font-weight: 600; }
td.n { font-variant-numeric: tabular-nums; }
.scroll { overflow-x: auto; }
.twins { display: grid; gap: 16px; grid-template-columns: minmax(0, 1fr); }
.card { min-width: 0; }
.twin h3 { margin: 0 0 4px; font-size: 16px; }
.twin .sub { color: var(--ink-2); font-size: 13px; margin-bottom: 10px; }
.chip { display: inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); font-size: 13px; white-space: nowrap; }
.chip.chg { border-color: var(--ink-2); font-weight: 650; }
.chip.res { background: var(--flag); color: var(--flag-ink); border-color: transparent; }
details { margin-top: 8px; }
summary { cursor: pointer; color: var(--ink-2); font-size: 13px; }
pre { white-space: pre-wrap; font: 12.5px/1.45 ui-monospace, SFMono-Regular, Menlo, monospace; background: var(--page);
  border: 1px solid var(--border); border-radius: 8px; padding: 10px; margin: 6px 0; max-height: 360px; overflow: auto; }
.texts { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr)); gap: 8px; }
ul.method { color: var(--ink-2); padding-left: 18px; }
.foot { color: var(--muted); font-size: 13px; margin-top: 32px; }
</style>
</head>
<body>
<main>
  <div id="mock"></div>
  <h1>Same person, different profile</h1>
  <p class="lede">Does an LLM first-pass screener judge the candidate, or the way their profile is written?
  Each synthetic candidate appears four ways with the same facts: plain, AI-polished, verbose, and sparse
  (titles and dates only). Three screeners rate every version against the role brief.</p>

  <div class="controls" id="controls"></div>
  <div class="tiles" id="tiles"></div>

  <h2>Average rating by presentation</h2>
  <div class="card">
    <div class="legend" id="legend"></div>
    <div id="chart"></div>
    <div style="color:var(--muted);font-size:13px">Whiskers: 95% bootstrap interval over candidates. Ratings: 0 poor, 1 okay, 2 good, 3 great.
    Sparse profiles carry almost no evidence, so every screener's score drops there; what matters is whether the candidate is rated down or sent to research (see the table and twins).</div>
  </div>

  <h2>All metrics</h2>
  <div class="card scroll"><table id="table"></table></div>

  <h2>Twins: the same candidate, four ways</h2>
  <p class="lede" style="margin-bottom:12px">Ratings shown are the most common label across repeats. A bold chip differs from the plain version; a highlighted chip was routed to research instead of being rated down.</p>
  <div class="twins" id="twins"></div>

  <h2>Method and limits</h2>
  <ul class="method">__METHOD__</ul>
  <div class="foot" id="foot"></div>
</main>
<div id="tip"></div>
<script>
const S = __DATA__;
const BRIEFS = __BRIEFS__;
const SN = {naive: "Naive prompt", instructed: "Prompt-patched", facts_first: "Facts-first (fix)"};
const VN = {plain: "Plain", polished: "AI-polished", verbose: "Verbose", sparse: "Sparse"};
const VARS = ["plain", "polished", "verbose", "sparse"];
const COL = {naive: "var(--s1)", instructed: "var(--s2)", facts_first: "var(--s3)"};
const RAT = ["poor", "okay", "good", "great"];
const $ = (id) => document.getElementById(id);
const el = (tag, attrs = {}, text) => { const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (text != null) e.textContent = text; return e; };
const svgEl = (tag, attrs = {}) => { const e = document.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); return e; };
const pct = (x) => x == null ? "n/a" : Math.round(100 * x) + "%";
const sgn = (x) => x == null ? "n/a" : (x >= 0 ? "+" : "") + x.toFixed(2);

if (S.meta.mock) $("mock").appendChild(el("div", {class: "mock"}, "MOCK RUN: numbers come from a fake model used to test the pipeline. They mean nothing."));

let model = S.meta.models[0];
if (S.meta.models.length > 1) {
  const lab = el("label", {for: "m"}, "Screening model ");
  const sel = el("select", {id: "m"});
  for (const m of S.meta.models) sel.appendChild(el("option", {value: m}, m));
  sel.onchange = () => { model = sel.value; render(); };
  $("controls").append(lab, sel);
}

function tile(label, value, vs) {
  const t = el("div", {class: "card tile"});
  t.append(el("div", {class: "label"}, label), el("div", {class: "value"}, value), el("div", {class: "vs"}, vs));
  return t;
}

function renderTiles(M) {
  const T = $("tiles"); T.replaceChildren();
  const nv = M.naive, ff = M.facts_first, pi = M.instructed;
  if (!nv) return;
  const fix = (f) => ff ? ` · facts-first ${f(ff)}` : "";
  T.append(tile("Label changed purely because of writing style (naive screener)", pct(nv.flip_any_style),
    `same text re-rated: ${pct(nv.noise_floor)}` + fix((x) => pct(x.flip_any_style))));
  T.append(tile("Average rating boost from AI polish (naive, 0-3 scale)", sgn(nv.delta_polished),
    `95% CI ${sgn(nv.delta_polished_ci[0])} to ${sgn(nv.delta_polished_ci[1])}, p=${nv.delta_polished_p.toPrecision(2)}` + fix((x) => sgn(x.delta_polished))));
  T.append(tile("'Great' candidates rated below great when their profile is sparse (the #721 pattern)", pct(nv.pattern_721),
    `n=${nv.n_great} great candidates` + (pi ? ` · prompt-patched ${pct(pi.pattern_721)}` : "") + fix((x) => pct(x.pattern_721) + " (sent to research)")));
}

function renderChart(M) {
  const screeners = Object.keys(M);
  const L = $("legend"); L.replaceChildren();
  for (const s of screeners) { const sp = el("span", {}, SN[s]); sp.style.setProperty("--c", COL[s]); L.append(sp); }
  const W = Math.max(300, Math.min(900, $("chart").clientWidth || 720)), H = W < 500 ? 260 : 300;
  const pad = {l: 60, r: 8, t: 12, b: 36};
  const iw = W - pad.l - pad.r, ih = H - pad.t - pad.b;
  const svg = svgEl("svg", {viewBox: `0 0 ${W} ${H}`, width: W, height: H, role: "img",
    "aria-label": "Mean rating by presentation variant for each screener"});
  const y = (v) => pad.t + ih - (v / 3) * ih;
  for (let i = 0; i <= 3; i++) {
    svg.append(svgEl("line", {x1: pad.l, x2: W - pad.r, y1: y(i), y2: y(i), stroke: i === 0 ? "var(--axis)" : "var(--grid)", "stroke-width": 1}));
    const t = svgEl("text", {x: pad.l - 8, y: y(i) + 4, "text-anchor": "end"}); t.textContent = `${i} ${RAT[i]}`; svg.append(t);
  }
  const gw = iw / VARS.length, bw = Math.max(8, Math.min(28, (gw - 16) / screeners.length - 2));
  VARS.forEach((v, gi) => {
    const gx = pad.l + gi * gw + (gw - (bw + 2) * screeners.length + 2) / 2;
    const t = svgEl("text", {x: pad.l + gi * gw + gw / 2, y: H - 12, "text-anchor": "middle"}); t.textContent = VN[v]; svg.append(t);
    screeners.forEach((s, si) => {
      const val = M[s].mean_score[v]; if (val == null) return;
      const x = gx + si * (bw + 2), top = y(val), base = y(0), r = Math.min(4, (base - top) / 2);
      const d = `M${x},${base} V${top + r} Q${x},${top} ${x + r},${top} H${x + bw - r} Q${x + bw},${top} ${x + bw},${top + r} V${base} Z`;
      const bar = svgEl("path", {d, fill: COL[s], class: "bar", tabindex: 0});
      const ci = M[s].mean_score_ci[v];
      const show = (ev) => tip(ev, val.toFixed(2), `${SN[s]} · ${VN[v]}`, `95% CI ${ci[0].toFixed(2)}-${ci[1].toFixed(2)} · n=${M[s].n_persons}`, COL[s]);
      bar.addEventListener("pointermove", show); bar.addEventListener("focus", show);
      bar.addEventListener("pointerleave", hide); bar.addEventListener("blur", hide);
      svg.append(bar);
      if (ci && !isNaN(ci[0])) {
        const cx = x + bw / 2;
        svg.append(svgEl("line", {x1: cx, x2: cx, y1: y(ci[0]), y2: y(ci[1]), stroke: "var(--ink-2)", "stroke-width": 1.5}));
      }
    });
  });
  $("chart").replaceChildren(svg);
}

function tip(ev, value, name, extra, color) {
  const t = $("tip"); t.replaceChildren();
  const k = el("span", {class: "k"}); k.style.setProperty("--c", color);
  t.append(el("strong", {}, value)); const line = el("div"); line.append(k, document.createTextNode(name)); t.append(line, el("div", {}, extra));
  t.style.display = "block";
  const x = ev.clientX ?? ev.target.getBoundingClientRect().left, yy = ev.clientY ?? ev.target.getBoundingClientRect().top;
  t.style.left = Math.min(x + 14, innerWidth - t.offsetWidth - 8) + "px"; t.style.top = (yy + 14) + "px";
}
function hide() { $("tip").style.display = "none"; }

const ROWS = [
  ["Same-text repeat noise", "noise_floor", pct],
  ["Label flips, plain vs AI-polished", "flip_plain_polished", pct],
  ["Label flips, plain vs verbose", "flip_plain_verbose", pct],
  ["Label differs across any style", "flip_any_style", pct],
  ["Avg rating shift, AI-polished vs plain", "delta_polished", sgn],
  ["Avg rating shift, verbose vs plain", "delta_verbose", sgn],
  ["Avg rating shift, sparse vs plain", "delta_sparse", sgn],
  ["Sparse rated lower, not sent to research", "sparse_downgrade", pct],
  ["Sparse routed to research", "sparse_research", pct],
  ["#721 pattern: great rated below great when sparse", "pattern_721", pct],
  ["Full profiles wrongly routed to research", "false_research", pct],
  ["Agreement with reference tier (plain)", "agree_ref_plain", pct],
  ["Kendall tau, plain vs polished ranking", "kendall_tau_plain_vs_polished", (x) => x == null ? "n/a" : x.toFixed(2)],
];
function renderTable(M) {
  const screeners = Object.keys(M); const T = $("table"); T.replaceChildren();
  const hr = el("tr"); hr.append(el("th", {}, "Metric")); for (const s of screeners) hr.append(el("th", {}, SN[s])); T.append(hr);
  for (const [label, key, f] of ROWS) {
    const tr = el("tr"); tr.append(el("td", {}, label));
    for (const s of screeners) tr.append(el("td", {class: "n"}, f(M[s][key]))); T.append(tr);
  }
}

function renderTwins() {
  const box = $("twins"); box.replaceChildren();
  for (const c of S.cards) {
    const card = el("div", {class: "card twin"});
    card.append(el("h3", {}, `Candidate #${c.id}`),
      el("div", {class: "sub"}, `${BRIEFS[c.brief]} brief · reference tier: ${c.ref_tier} · meets: ${c.criteria_met.join(", ")}`));
    const tbl = el("table"); const hr = el("tr"); hr.append(el("th", {}, "Screener"));
    for (const v of VARS) hr.append(el("th", {}, VN[v])); tbl.append(hr);
    for (const [s, byV] of Object.entries(c.labels)) {
      const tr = el("tr"); tr.append(el("td", {}, SN[s])); const base = byV.plain.rating;
      for (const v of VARS) {
        const L = byV[v]; const td = el("td");
        if (L.rating) {
          let txt = L.rating, cls = "chip";
          if (L.research) { txt = "→ research"; cls += " res"; }
          else if (v !== "plain" && L.rating !== base) {
            const up = RAT.indexOf(L.rating) > RAT.indexOf(base); txt = (up ? "▲ " : "▼ ") + txt; cls += " chg";
          }
          const chip = el("span", {class: cls}, txt); chip.title = "repeats: " + L.all.join(", "); td.append(chip);
        }
        tr.append(td);
      }
      tbl.append(tr);
    }
    const sc = el("div", {class: "scroll"}); sc.append(tbl); card.append(sc);
    const det = el("details"); det.append(el("summary", {}, "Show the four profile texts"));
    const grid = el("div", {class: "texts"});
    for (const v of VARS) { const d = el("div"); d.append(el("div", {class: "sub"}, VN[v]), el("pre", {}, c.texts[v])); grid.append(d); }
    det.append(grid); card.append(det);
    if (c.evidence && c.evidence.plain) {
      const ev = el("details"); ev.append(el("summary", {}, "Facts-first: verified evidence quotes (plain version)"));
      const ul = el("ul"); for (const [k, q] of Object.entries(c.evidence.plain)) ul.append(el("li", {}, `${k}: "${q}"`));
      ev.append(ul); card.append(ev);
    }
    box.append(card);
  }
}

function render() { const M = S.metrics[model] || {}; renderTiles(M); renderChart(M); renderTable(M); }
render(); renderTwins();
let rz; addEventListener("resize", () => { clearTimeout(rz); rz = setTimeout(() => renderChart(S.metrics[model] || {}), 150); });
$("foot").textContent = `${S.meta.n_people} synthetic candidates · ${S.meta.repeats} repeats · models: ${S.meta.models.join(", ")} · rewrites by ${S.meta.generator_model} · generated ${S.meta.generated_at}`;
</script>
</body>
</html>
"""
