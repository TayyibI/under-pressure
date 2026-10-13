"""Metrics. Every comparison is paired within the same synthetic person, so the
only thing that differs between a person's variants is presentation.

Key metrics (per screener x model):
  noise_floor           P(label differs between two repeats of the *same* text)
  flip_plain_polished   P(label differs between plain and polished, same repeat index)
  flip_any_style        P(labels across plain/polished/verbose are not all equal)
  delta_polished        mean rating change plain -> polished (rating points, 0-3 scale)
  sparse_downgrade      P(sparse rated lower than plain AND not routed to research)
  pattern_721           among reference-'great' people: P(sparse rated below great AND not routed to research)
  false_research        P(a full-detail profile gets routed to research)
"""
from __future__ import annotations

import itertools
import json
import statistics
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats

from .briefs import RATINGS

STYLES = ("plain", "polished", "verbose")
VARIANTS = ("plain", "polished", "verbose", "sparse")


def load_results(path: Path) -> tuple[dict, int]:
    recs, errors = {}, 0
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        k = (d["person"], d["variant"], d["screener"], d["model"], d["repeat"])
        if "error" in d:
            errors += 1
            continue
        recs[k] = d
    return recs, errors


def _boot_ci(values: list[float], rng: np.random.Generator, n: int = 2000) -> tuple[float, float]:
    if len(values) < 2:
        return (float("nan"), float("nan"))
    arr = np.asarray(values, dtype=float)
    idx = rng.integers(0, len(arr), size=(n, len(arr)))
    means = arr[idx].mean(axis=1)
    return (float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5)))


def _rate(xs: list[bool]) -> float | None:
    return (sum(xs) / len(xs)) if xs else None


def analyze(results_path: Path, data_dir: Path, models: list[str], screeners: list[str], repeats: int) -> dict:
    recs, n_errors = load_results(results_path)
    truth = {p["id"]: p for p in json.loads((data_dir / "truth.json").read_text())}
    profiles = json.loads((data_dir / "profiles.json").read_text())
    rng = np.random.default_rng(0)

    metrics: dict = {}
    for m in models:
        metrics[m] = {}
        for s in screeners:
            def get(pid, v, r):
                return recs.get((pid, v, s, m, r))

            persons = [pid for pid in profiles
                       if all(any(get(pid, v, r) for r in range(repeats)) for v in VARIANTS if v in profiles[pid])
                       and all(v in profiles[pid] for v in VARIANTS)]
            if not persons:
                continue

            noise, flip_pp, flip_pv, flip_any = [], [], [], []
            down, research_sparse, false_research, pattern = [], [], [], []
            exact_plain, within1_plain, exact_pol = [], [], []
            mean_by_var = {v: [] for v in VARIANTS}
            diffs_pol, diffs_verb, diffs_sparse = [], [], []

            for pid in persons:
                ref = truth[pid]["ref_tier"]
                for v in STYLES:
                    labs = [get(pid, v, r)["rating"] for r in range(repeats) if get(pid, v, r)]
                    for a, b in itertools.combinations(labs, 2):
                        noise.append(a != b)
                per_var_scores = {v: [] for v in VARIANTS}
                for r in range(repeats):
                    rr = {v: get(pid, v, r) for v in VARIANTS}
                    for v, x in rr.items():
                        if x:
                            per_var_scores[v].append(x["score"])
                    if rr["plain"] and rr["polished"]:
                        flip_pp.append(rr["plain"]["rating"] != rr["polished"]["rating"])
                    if rr["plain"] and rr["verbose"]:
                        flip_pv.append(rr["plain"]["rating"] != rr["verbose"]["rating"])
                    if all(rr[v] for v in STYLES):
                        flip_any.append(len({rr[v]["rating"] for v in STYLES}) > 1)
                    for v in STYLES:
                        if rr[v]:
                            false_research.append(bool(rr[v].get("research")))
                    if rr["plain"]:
                        exact_plain.append(rr["plain"]["rating"] == ref)
                        within1_plain.append(abs(rr["plain"]["score"] - RATINGS.index(ref)) <= 1)
                    if rr["polished"]:
                        exact_pol.append(rr["polished"]["rating"] == ref)
                    if rr["sparse"]:
                        research_sparse.append(bool(rr["sparse"].get("research")))
                        if rr["plain"]:
                            down.append(rr["sparse"]["score"] < rr["plain"]["score"] and not rr["sparse"].get("research"))
                        if ref == "great":
                            pattern.append(rr["sparse"]["rating"] != "great" and not rr["sparse"].get("research"))
                means = {v: statistics.mean(xs) for v, xs in per_var_scores.items() if xs}
                for v in VARIANTS:
                    if v in means:
                        mean_by_var[v].append(means[v])
                if "plain" in means:
                    if "polished" in means:
                        diffs_pol.append(means["polished"] - means["plain"])
                    if "verbose" in means:
                        diffs_verb.append(means["verbose"] - means["plain"])
                    if "sparse" in means:
                        diffs_sparse.append(means["sparse"] - means["plain"])

            def wilcoxon_p(d):
                if not d or all(x == 0 for x in d):
                    return 1.0
                return float(stats.wilcoxon(d, zero_method="zsplit").pvalue)

            plain_means = mean_by_var["plain"]
            pol_means = mean_by_var["polished"]
            tau = None
            if len(plain_means) > 2 and len(set(plain_means)) > 1 and len(set(pol_means)) > 1:
                tau = float(stats.kendalltau(plain_means, pol_means).statistic)

            metrics[m][s] = {
                "n_persons": len(persons),
                "noise_floor": _rate(noise),
                "flip_plain_polished": _rate(flip_pp),
                "flip_plain_verbose": _rate(flip_pv),
                "flip_any_style": _rate(flip_any),
                "delta_polished": statistics.mean(diffs_pol) if diffs_pol else None,
                "delta_polished_ci": _boot_ci(diffs_pol, rng),
                "delta_polished_p": wilcoxon_p(diffs_pol),
                "delta_verbose": statistics.mean(diffs_verb) if diffs_verb else None,
                "delta_verbose_ci": _boot_ci(diffs_verb, rng),
                "delta_verbose_p": wilcoxon_p(diffs_verb),
                "delta_sparse": statistics.mean(diffs_sparse) if diffs_sparse else None,
                "delta_sparse_ci": _boot_ci(diffs_sparse, rng),
                "sparse_downgrade": _rate(down),
                "sparse_research": _rate(research_sparse),
                "false_research": _rate(false_research),
                "pattern_721": _rate(pattern),
                "n_great": sum(1 for pid in persons if truth[pid]["ref_tier"] == "great"),
                "agree_ref_plain": _rate(exact_plain),
                "within1_ref_plain": _rate(within1_plain),
                "agree_ref_polished": _rate(exact_pol),
                "kendall_tau_plain_vs_polished": tau,
                "mean_score": {v: (statistics.mean(xs) if xs else None) for v, xs in mean_by_var.items()},
                "mean_score_ci": {v: _boot_ci(xs, rng) for v, xs in mean_by_var.items()},
            }

    word_counts = {v: statistics.mean(len(p[v].split()) for p in profiles.values() if v in p)
                   for v in VARIANTS if any(v in p for p in profiles.values())}
    cards = pick_cards(recs, truth, profiles, models[0], screeners, repeats)
    return {"metrics": metrics, "word_counts": word_counts, "errors": n_errors, "cards": cards}


def _modal(labels: list[str]) -> str | None:
    if not labels:
        return None
    counts = defaultdict(int)
    for lab in labels:
        counts[lab] += 1
    best = max(counts.values())
    tied = [lab for lab in labels if counts[lab] == best]
    return min(tied, key=RATINGS.index)  # ties resolve to the lower rating


def pick_cards(recs, truth, profiles, model, screeners, repeats, k: int = 6) -> list[dict]:
    """Pick the twins that show what happened: style flips first, then sparse 'great' candidates rated down."""
    STY = ("plain", "polished", "verbose")
    rows = []
    for pid, prof in profiles.items():
        if not all(v in prof for v in VARIANTS):
            continue
        labels = {}
        for s in screeners:
            labels[s] = {}
            for v in VARIANTS:
                keys = [(pid, v, s, model, r) for r in range(repeats) if (pid, v, s, model, r) in recs]
                labs = [recs[x]["rating"] for x in keys]
                res = [bool(recs[x].get("research")) for x in keys]
                labels[s][v] = {"rating": _modal(labs), "all": labs, "research": bool(res) and sum(res) * 2 > len(res)}
        lead = labels[screeners[0]]
        sty = [RATINGS.index(lead[v]["rating"]) for v in STY if lead[v]["rating"]]
        style_spread = (max(sty) - min(sty)) if sty else 0
        great = truth[pid]["ref_tier"] == "great"
        sparse_drop = bool(lead["sparse"]["rating"] and lead["plain"]["rating"] and not lead["sparse"]["research"]
                           and RATINGS.index(lead["sparse"]["rating"]) < RATINGS.index(lead["plain"]["rating"]))
        rows.append({"pid": pid, "labels": labels, "style_spread": style_spread, "great": great, "sparse_drop": sparse_drop})
    style = sorted([r for r in rows if r["style_spread"] > 0], key=lambda r: (r["style_spread"], r["great"]), reverse=True)
    sparse = [r for r in rows if r["great"] and r["sparse_drop"] and r not in style]
    chosen = style[: k // 2]
    chosen += sparse[: k - len(chosen)]
    chosen += [r for r in style[k // 2:] if r not in chosen][: k - len(chosen)]
    chosen += [r for r in rows if r not in chosen and r["great"]][: k - len(chosen)]
    cards = []
    for r in chosen:
        pid = r["pid"]
        evidence = {}
        if "facts_first" in screeners:
            for v in ("plain", "sparse"):
                r0 = recs.get((pid, v, "facts_first", model, 0))
                if r0:
                    evidence[v] = r0.get("evidence", {})
        cards.append({
            "id": pid, "brief": truth[pid]["brief_id"], "ref_tier": truth[pid]["ref_tier"],
            "criteria_met": truth[pid]["criteria_met"], "labels": r["labels"],
            "style_flip": r["style_spread"] > 0, "sparse_drop": r["sparse_drop"],
            "texts": {v: profiles[pid][v] for v in VARIANTS}, "evidence": evidence,
        })
    return cards
