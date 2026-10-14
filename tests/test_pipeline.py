"""Run with:  python -m pytest -q"""
import json
import re
import subprocess
import sys
from pathlib import Path

from twins.briefs import BRIEFS, reference_tier
from twins.generate import generate, render_plain, render_sparse
from twins.rewrite import check_preservation
from twins.screeners import quote_verified

PEOPLE = generate(20, 7)


def test_generation_is_deterministic_and_balanced():
    again = generate(20, 7)
    assert [render_plain(p) for p in PEOPLE] == [render_plain(p) for p in again]
    for bid in BRIEFS:
        tiers = [p.ref_tier for p in PEOPLE if p.brief_id == bid]
        assert set(tiers) == {"great", "good", "okay", "poor"}


def test_reference_tier_matches_criteria():
    for p in PEOPLE:
        b = BRIEFS[p.brief_id]
        musts = sum(c.id in p.criteria_met for c in b.musts)
        nices = sum(c.id in p.criteria_met for c in b.nices)
        assert p.ref_tier == reference_tier(musts, nices)


def test_unmet_criteria_leave_no_evidence():
    # A candidate who doesn't meet a criterion must not have that criterion's named tech anywhere.
    for p in PEOPLE:
        b = BRIEFS[p.brief_id]
        text = render_plain(p)
        for c in b.criteria:
            if c.id in p.criteria_met or c.via_company:
                continue
            for t in c.templates:
                for tok in t.tokens:
                    if tok not in p.own_tokens():
                        assert not re.search(rf"(?<![\w.]){re.escape(tok)}(?![\w])", text), (p.id, c.id, tok)
        if "early_stage" not in p.criteria_met:
            assert "seed-stage" not in text


def test_sparse_drops_all_detail():
    for p in PEOPLE:
        s = render_sparse(p)
        assert all(f.text not in s for r in p.roles for f in r.facts)
        assert len(s.split()) < 60 <= len(render_plain(p).split())


def test_plain_passes_its_own_preservation_check():
    for p in PEOPLE:
        assert check_preservation(p, render_plain(p)) == [], p.id


def test_preservation_catches_dropped_number_and_added_tech():
    p = next(x for x in PEOPLE if x.brief_id == "A" and "Kubernetes" not in x.own_tokens())
    plain = render_plain(p)
    num = next(t for t in p.required_tokens() if t.isdigit() and len(t) >= 2)
    broken = plain.replace(num, "many") + "\nAlso experienced with Kubernetes."
    problems = check_preservation(p, broken)
    assert any(num in x for x in problems)
    assert any("Kubernetes" in x for x in problems)


def test_preservation_accepts_thousands_separators():
    p = next(x for x in PEOPLE if any(n in x.required_tokens() for n in ("2400", "3800", "5200", "8100")))
    plain = render_plain(p)
    for n in ("2400", "3800", "5200", "8100"):
        plain = plain.replace(n, f"{n[0]},{n[1:]}")
    assert check_preservation(p, plain) == []


def test_quote_verification():
    profile = "Senior Engineer - Quillmark · 2021-present\n- Built the customer dashboard in TypeScript and React"
    assert quote_verified("Built the customer dashboard in TypeScript and React", profile)
    assert quote_verified("built the customer  dashboard in typescript", profile)
    assert not quote_verified("Led a team of 6 React engineers", profile)
    assert not quote_verified("", profile)


def test_mock_pipeline_end_to_end(tmp_path: Path):
    wd = tmp_path / "run"
    r = subprocess.run([sys.executable, "-m", "twins", "all", "--mock", "--quick", "--workdir", str(wd)],
                       capture_output=True, text=True, cwd=Path(__file__).resolve().parents[1])
    assert r.returncode == 0, r.stderr
    summary = json.loads((wd / "results" / "summary.json").read_text(encoding="utf-8"))
    assert summary["meta"]["mock"] is True
    assert summary["errors"] == 0
    m = summary["metrics"][summary["meta"]["models"][0]]
    assert set(m) == {"naive", "instructed", "facts_first"}
    assert (wd / "results" / "index.html").read_text(encoding="utf-8").count("Practice run with a fake model") >= 1
    # the simulator page is built from the same run
    app = wd / "app"
    index, artifact = (app / "index.html").read_text(encoding="utf-8"), (app / "artifact.html").read_text(encoding="utf-8")
    assert index.startswith("<!doctype html>") and not artifact.lstrip().startswith("<!doctype")
    for page in (index, artifact):
        assert "__APP_DATA__" not in page and "__SIM_JS__" not in page
    data = json.loads(re.search(r"const DATA = (\{.*?\});\n", artifact, re.S).group(1))
    assert data["meta"]["mock"] is True and set(data["counts"]) == {"naive", "instructed", "facts_first"}
    assert len(data["candidates"]) == 21 and all(data["meta"]["slot"] in p for b in data["briefs"].values() for p in b["prompts"].values())


def test_simulator_orders_by_calibration(tmp_path: Path):
    """Runs app/sim.js under node (skipped if node is missing) on hand-made counts."""
    import shutil
    if not shutil.which("node"):
        import pytest
        pytest.skip("node not installed")
    sim = Path(__file__).resolve().parents[1] / "app" / "sim.js"
    script = tmp_path / "t.js"
    script.write_text(f"""
const Sim = require({json.dumps(str(sim))});
// sparse labels say nothing about the person; full labels are accurate
const cal = {{ full: {{ great: {{great: 9, good: 1}}, good: {{good: 9, okay: 1}}, okay: {{okay: 9, good: 1}}, poor: {{poor: 10}} }},
              sparse: {{ great: {{okay: 10}}, good: {{okay: 10}}, okay: {{okay: 10}}, poor: {{okay: 10}} }} }};
const p = {{ n: 600, great: 0.05, good: 0.15, okay: 0.4, sparse: 0.3, median: 19, sigma: 0.5, sparseMult: 1, agents: 4, placement: "after-good" }};
const out = {{ label: [], calibrated: [], arrival: [], learned: [] }};
for (let s = 1; s <= 40; s++) {{
  const pool = Sim.makePool(p, cal, s), ctx = Sim.context({{ ...p, seed: s }}, cal);
  for (const pol of Object.keys(out)) {{
    const r = Sim.run(pool, pol, ctx);
    if (r.order.length !== pool.length || new Set(r.order).size !== pool.length) throw new Error("not a permutation: " + pol);
    out[pol].push(Sim.metrics(r, pool, 100).h90);
  }}
}}
const m = Object.fromEntries(Object.entries(out).map(([k, v]) => [k, Sim.quantile(v, 0.5)]));
const post = Sim.posterior(cal, Sim.priorOf(p), 0.5);
console.log(JSON.stringify({{ m, sparseOkay: post.sparse.okay, fullGood: post.full.good }}));
""", encoding="utf-8")
    r = subprocess.run(["node", str(script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    res = json.loads(r.stdout)
    assert abs(res["sparseOkay"] - 0.05) < 0.01          # uninformative label -> posterior ~ prior
    assert res["m"]["calibrated"] < res["m"]["label"] < res["m"]["arrival"]
    assert res["m"]["learned"] < res["m"]["arrival"]
