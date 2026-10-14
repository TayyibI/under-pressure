/* Research-queue simulator. Plain JS, no dependencies; runs in the page and under node for tests.
 *
 * A pool of candidates has a true tier (poor/okay/good/great), a profile type (full or sparse) and a
 * first-pass label drawn from MEASURED counts: how often the benchmark screener gave each label to
 * candidates of each true tier, by profile type. Research takes time and reveals the true tier.
 * K agents work in parallel. Policies differ only in which candidate an idle agent researches next.
 * Every policy sees the same pool with the same research durations (common random numbers).
 */
(function (root) {
  "use strict";

  const TIERS = ["poor", "okay", "good", "great"];
  const LABELS = ["great", "good", "research", "okay", "poor"];
  const POLICIES = ["arrival", "label", "learned", "calibrated"];

  // ---------- random numbers (seeded, so every pool is reproducible) ----------
  function rng32(seed) {
    let a = (seed >>> 0) || 1;
    return function () {
      a = (a + 0x6d2b79f5) >>> 0;
      let t = a;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function normal(r) {
    let u = 0, v = 0;
    while (u === 0) u = r();
    while (v === 0) v = r();
    return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
  }
  function gamma(r, k) {                       // Marsaglia-Tsang, k > 0
    if (k < 1) return gamma(r, k + 1) * Math.pow(r(), 1 / k);
    const d = k - 1 / 3, c = 1 / Math.sqrt(9 * d);
    for (;;) {
      let x, v;
      do { x = normal(r); v = 1 + c * x; } while (v <= 0);
      v = v * v * v;
      const u = r();
      if (u < 1 - 0.0331 * x * x * x * x) return d * v;
      if (Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v;
    }
  }
  function beta(r, a, b) { const x = gamma(r, a); return x / (x + gamma(r, b)); }
  function pick(r, weights) {                  // weights: [[key, w], ...]
    let tot = 0;
    for (const [, w] of weights) tot += w;
    let u = r() * tot;
    for (const [k, w] of weights) { if ((u -= w) < 0) return k; }
    return weights[weights.length - 1][0];
  }

  // ---------- calibration ----------
  function labelsOf(cal) {                     // labels this screener ever produced
    const seen = new Set();
    for (const kind of Object.keys(cal)) for (const t of Object.keys(cal[kind])) for (const l of Object.keys(cal[kind][t])) seen.add(l);
    return LABELS.filter((l) => seen.has(l));
  }

  /** P(label | tier, kind), Laplace-smoothed over the labels this screener uses. */
  function likelihood(cal, alpha) {
    const labels = labelsOf(cal), out = {};
    for (const kind of ["full", "sparse"]) {
      out[kind] = {};
      for (const t of TIERS) {
        const c = (cal[kind] && cal[kind][t]) || {};
        let n = 0;
        for (const l of labels) n += c[l] || 0;
        out[kind][t] = {};
        for (const l of labels) out[kind][t][l] = ((c[l] || 0) + alpha) / (n + alpha * labels.length);
      }
    }
    return out;
  }

  /** P(great | label, kind) from the smoothed likelihoods and a tier prior. */
  function posterior(cal, prior, alpha) {
    const L = likelihood(cal, alpha), labels = labelsOf(cal), out = {};
    for (const kind of ["full", "sparse"]) {
      out[kind] = {};
      for (const l of labels) {
        let num = 0, den = 0;
        for (const t of TIERS) {
          const p = L[kind][t][l] * prior[t];
          den += p;
          if (t === "great") num = p;
        }
        out[kind][l] = den > 0 ? num / den : 0;
      }
    }
    return out;
  }

  function priorOf(p) {
    const great = p.great, good = p.good, okay = p.okay;
    return { great, good, okay, poor: Math.max(0, 1 - great - good - okay) };
  }

  // ---------- pools ----------
  /**
   * params: {n, great, good, okay, sparse, median (min), sigma, sparseMult}
   * cal: counts for one screener: cal[kind][tier][label] = count
   */
  function makePool(params, cal, seed) {
    const r = rng32(seed), prior = priorOf(params);
    const tierW = TIERS.map((t) => [t, prior[t]]);
    const labW = {};
    for (const kind of ["full", "sparse"]) {
      labW[kind] = {};
      for (const t of TIERS) {
        const c = (cal[kind] && cal[kind][t]) || {};
        const w = Object.entries(c).filter(([, v]) => v > 0);
        labW[kind][t] = w.length ? w : [["okay", 1]];
      }
    }
    const out = new Array(params.n);
    for (let i = 0; i < params.n; i++) {
      const tier = pick(r, tierW);
      const sparse = r() < params.sparse;
      const kind = sparse ? "sparse" : "full";
      const label = pick(r, labW[kind][tier]);
      const dur = params.median * Math.exp(params.sigma * normal(r)) * (sparse ? params.sparseMult : 1);
      out[i] = { i, tier, sparse, kind, label, dur, great: tier === "great" };
    }
    return out;
  }

  // ---------- policies ----------
  const PLACEMENT = { "after-great": 0.5, "after-good": 1.5, "with-okay": 2, "last": 4 };
  function labelRank(label, placement) {
    if (label === "research") return PLACEMENT[placement] ?? 1.5;
    return { great: 0, good: 1, okay: 2, poor: 3 }[label];
  }

  /** Static queue order (indices) for arrival / label / calibrated. */
  function staticOrder(pool, policy, ctx) {
    const idx = pool.map((c) => c.i);
    if (policy === "arrival") return idx;
    if (policy === "label") {
      return idx.sort((a, b) => (labelRank(pool[a].label, ctx.placement) - labelRank(pool[b].label, ctx.placement)) || a - b);
    }
    if (policy === "calibrated") {
      const key = (c) => -calibratedValue(c.label, c.kind, ctx);
      return idx.sort((a, b) => (key(pool[a]) - key(pool[b])) || a - b);
    }
    throw new Error("not static: " + policy);
  }

  function expectedDur(kind, ctx) {
    return ctx.median * Math.exp((ctx.sigma * ctx.sigma) / 2) * (kind === "sparse" ? ctx.sparseMult : 1);
  }
  /** Chance of a great per research-minute, the calibrated policy's sort key. */
  function calibratedValue(label, kind, ctx) {
    return (ctx.post[kind][label] || 0) / expectedDur(kind, ctx);
  }

  // ---------- min-heap ----------
  function Heap() { this.a = []; }
  Heap.prototype.push = function (t, v) {
    const a = this.a; a.push([t, v]);
    let i = a.length - 1;
    while (i > 0) { const p = (i - 1) >> 1; if (a[p][0] <= a[i][0]) break; [a[p], a[i]] = [a[i], a[p]]; i = p; }
  };
  Heap.prototype.pop = function () {
    const a = this.a, top = a[0], last = a.pop();
    if (a.length) {
      a[0] = last;
      let i = 0;
      for (;;) {
        const l = 2 * i + 1, r = l + 1;
        let m = i;
        if (l < a.length && a[l][0] < a[m][0]) m = l;
        if (r < a.length && a[r][0] < a[m][0]) m = r;
        if (m === i) break;
        [a[m], a[i]] = [a[i], a[m]]; i = m;
      }
    }
    return top;
  };
  Heap.prototype.peek = function () { return this.a[0]; };
  Heap.prototype.size = function () { return this.a.length; };

  /**
   * Run one policy. Returns per-candidate start/end/agent, dispatch order, and the find curve.
   * The learned policy decides each dispatch from research results completed by then, and nothing else.
   */
  function run(pool, policy, ctx) {
    const n = pool.length, K = Math.max(1, ctx.agents | 0);
    const start = new Float64Array(n), end = new Float64Array(n), agent = new Int16Array(n), pos = new Int32Array(n);
    const order = [];
    const agents = new Heap();
    for (let a = 0; a < K; a++) agents.push(0, a);

    let next;
    if (policy === "learned") next = learnedChooser(pool, ctx);
    else {
      const q = staticOrder(pool, policy, ctx);
      let k = 0;
      next = { take: () => (k < q.length ? q[k++] : -1), learn: () => {} };
    }
    const done = new Heap();
    let lastStart = 0;
    for (;;) {
      const [t, a] = agents.pop();
      while (done.size() && done.peek()[0] <= t) next.learn(done.pop()[1]);
      const c = next.take();
      if (c < 0) break;
      start[c] = t; end[c] = t + pool[c].dur; agent[c] = a; pos[c] = order.length; order.push(c);
      lastStart = t;
      done.push(end[c], c);
      agents.push(end[c], a);
    }
    // agent-minutes worked by time t: every agent is busy until the last dispatch
    const workAt = (t) => {
      if (t <= lastStart) return K * t;
      let w = 0;
      for (let i = 0; i < n; i++) if (start[i] < t) w += Math.min(t - start[i], pool[i].dur);
      return w;
    };
    const finds = [];
    for (let i = 0; i < n; i++) if (pool[i].great) finds.push(i);
    finds.sort((x, y) => end[x] - end[y]);
    const findT = finds.map((i) => end[i]);
    const findH = findT.map((t) => workAt(t) / 60);
    let finish = 0;
    for (let i = 0; i < n; i++) finish = Math.max(finish, end[i]);
    return { policy, start, end, agent, pos, order, finds, findT, findH, finish, K, workAt };
  }

  /** Thompson sampling over first-pass buckets (label x profile type), starting from no knowledge. */
  function learnedChooser(pool, ctx) {
    const r = rng32((ctx.seed ^ 0x9e3779b9) >>> 0);
    const buckets = new Map();
    for (const c of pool) {
      const k = c.label + "|" + c.kind;
      if (!buckets.has(k)) buckets.set(k, { key: k, kind: c.kind, items: [], next: 0, n: 0, g: 0 });
      buckets.get(k).items.push(c.i);
    }
    const B = [...buckets.values()];
    let R = 0, G = 0;
    const durSum = { full: 0, sparse: 0 }, durN = { full: 0, sparse: 0 };
    const s = ctx.learnStrength ?? 1;
    return {
      take() {
        const pHat = (G + 0.5) / (R + 1);
        let best = null, bestV = -1;
        for (const b of B) {
          if (b.next >= b.items.length) continue;
          const theta = beta(r, s * pHat + b.g, s * (1 - pHat) + (b.n - b.g));
          const d = durN[b.kind] ? durSum[b.kind] / durN[b.kind] : ctx.median;
          const v = theta / d;
          if (v > bestV) { bestV = v; best = b; }
        }
        if (!best) return -1;
        return best.items[best.next++];
      },
      learn(i) {
        const c = pool[i], b = buckets.get(c.label + "|" + c.kind);
        b.n++; R++;
        if (c.great) { b.g++; G++; }
        durSum[c.kind] += c.dur; durN[c.kind]++;
      },
      buckets: B,
    };
  }

  function context(params, cal, extra) {
    const prior = priorOf(params);
    return Object.assign({
      agents: params.agents, median: params.median, sigma: params.sigma, sparseMult: params.sparseMult,
      placement: params.placement, seed: params.seed, prior, post: posterior(cal, prior, 0.5),
    }, extra || {});
  }

  /** Summary numbers for one run. */
  function metrics(res, pool, budgetH) {
    const G = res.finds.length;
    const at = (q) => (G ? res.findH[Math.max(0, Math.ceil(q * G) - 1)] : NaN);
    let hidden = 0, hiddenFound = 0, inBudget = 0;
    for (let k = 0; k < G; k++) {
      const c = pool[res.finds[k]];
      if (c.label !== "great") { hidden++; if (res.findH[k] <= budgetH) hiddenFound++; }
      if (res.findH[k] <= budgetH) inBudget++;
    }
    return { G, h50: at(0.5), h90: at(0.9), h100: at(1), inBudget, hidden, hiddenFound, first: G ? res.findT[0] / 60 : NaN };
  }

  /** Where a single candidate would sit in a static queue built over a pool. */
  function rankIn(pool, policy, ctx, label, kind) {
    let ahead = 0, tie = 0;
    if (policy === "label") {
      const me = labelRank(label, ctx.placement);
      for (const c of pool) { const v = labelRank(c.label, ctx.placement); if (v < me) ahead++; else if (v === me) tie++; }
    } else if (policy === "calibrated") {
      const me = calibratedValue(label, kind, ctx);
      for (const c of pool) { const v = calibratedValue(c.label, c.kind, ctx); if (v > me + 1e-15) ahead++; else if (Math.abs(v - me) <= 1e-15) tie++; }
    } else return null;
    return { best: ahead + 1, worst: ahead + tie + 1, mid: ahead + Math.round(tie / 2) + 1 };
  }

  function quantile(xs, q) {
    const a = xs.filter((x) => Number.isFinite(x)).sort((x, y) => x - y);
    if (!a.length) return NaN;
    const p = (a.length - 1) * q, lo = Math.floor(p), hi = Math.ceil(p);
    return a[lo] + (a[hi] - a[lo]) * (p - lo);
  }

  const api = { TIERS, LABELS, POLICIES, PLACEMENT, rng32, makePool, likelihood, posterior, priorOf, labelsOf, context, run, metrics, rankIn, quantile, labelRank, calibratedValue, expectedDur };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.Sim = api;
})(typeof window !== "undefined" ? window : globalThis);
