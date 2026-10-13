"""Role briefs and the evidence templates used to build synthetic candidates.

Everything here is fictional: company names, roles and candidates are invented,
so no real person's data is used anywhere in the benchmark.

Each brief has three must-haves and three nice-to-haves. Each criterion carries
evidence templates (facts that demonstrate it) so the generator can control
exactly which criteria a synthetic candidate meets. Every template contains at
least one number, so a rewrite that silently drops a fact is detectable.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Template:
    text: str                 # may contain {n} {m} {p} {k}
    tokens: tuple[str, ...]   # named tech/proper-noun tokens that must survive a rewrite


@dataclass(frozen=True)
class Criterion:
    id: str
    kind: str                 # "must" | "nice"
    label: str                # shown to screeners
    templates: tuple[Template, ...] = ()
    requires: tuple[str, ...] = ()  # criteria this one implies (e.g. FastAPI implies Python)
    via_company: bool = False       # evidenced by a company descriptor, not a bullet


@dataclass(frozen=True)
class Brief:
    id: str
    title: str
    company: str
    blurb: str
    years: tuple[int, int]
    titles: tuple[str, ...]
    criteria: tuple[Criterion, ...]
    distractors: tuple[Template, ...]
    skills_hint: tuple[str, ...] = field(default=())

    @property
    def musts(self) -> list[Criterion]:
        return [c for c in self.criteria if c.kind == "must"]

    @property
    def nices(self) -> list[Criterion]:
        return [c for c in self.criteria if c.kind == "nice"]

    def criterion(self, cid: str) -> Criterion:
        for c in self.criteria:
            if c.id == cid:
                return c
        raise KeyError(cid)

    def as_text(self) -> str:
        lines = [
            f"Role: {self.title} at {self.company}",
            self.blurb,
            "",
            "Must-haves:",
            *[f"- {c.label}" for c in self.musts],
            "",
            "Nice-to-haves:",
            *[f"- {c.label}" for c in self.nices],
            "",
            f"Experience: {self.years[0]}-{self.years[1]} years",
        ]
        return "\n".join(lines)


T = Template

BRIEF_A = Brief(
    id="A",
    title="Senior Product Engineer",
    company="Quillmark",
    blurb="Quillmark is a seed-stage startup building collaborative design tools. "
          "We want an engineer with real product taste who can own features end to end.",
    years=(4, 10),
    titles=("Senior Frontend Engineer", "Frontend Engineer", "Product Engineer", "Software Engineer"),
    criteria=(
        Criterion("ts_react", "must", "Production TypeScript and React experience", (
            T("Built the customer dashboard in TypeScript and React, used by {n}k weekly users", ("TypeScript", "React")),
            T("Rewrote the checkout flow in React with TypeScript, lifting conversion by {p}%", ("React", "TypeScript")),
        )),
        Criterion("design_systems", "must", "Built or owned a design system or component library", (
            T("Created the company design system: {n} shared components adopted by {m} product teams", ()),
            T("Owned the component library and Figma-to-code design tokens used across {m} apps", ("Figma",)),
        )),
        Criterion("product_ownership", "must", "Owned user-facing product features end to end", (
            T("Owned the onboarding experience end to end, from spec to launch, cutting drop-off by {p}%", ()),
            T("Led the launch of the web editor (used by {n}k creators), working directly with customers and design", ()),
        )),
        Criterion("graphics", "nice", "WebGL, shaders or creative coding", (
            T("Wrote WebGL shaders for the 3D product preview, rendering {n}k models a day", ("WebGL",)),
            T("Built a GLSL shader pipeline for image filters, processing {n}k images daily", ("GLSL",)),
        )),
        Criterion("early_stage", "nice", "Experience at an early-stage startup", via_company=True),
        Criterion("mentoring", "nice", "Mentoring or leading engineers", (
            T("Mentored {k} junior engineers through their first year", ()),
            T("Managed a squad of {k} frontend engineers", ()),
        )),
    ),
    distractors=(
        T("Migrated CI from Jenkins to GitHub Actions, cutting build times by {p}%", ("Jenkins", "GitHub Actions")),
        T("Built the marketing site in Vue.js, serving {n}k monthly visitors", ("Vue.js",)),
        T("Added end-to-end tests with Playwright, raising test coverage by {p} points", ("Playwright",)),
        T("Improved the Lighthouse performance score on landing pages by {p} points", ("Lighthouse",)),
        T("Shipped {n} features from the sprint backlog in Angular", ("Angular",)),
        T("Wrote internal scripts in Python to automate {n} weekly reports", ("Python",)),
    ),
)

BRIEF_B = Brief(
    id="B",
    title="Senior Infrastructure Engineer",
    company="Copperline",
    blurb="Copperline runs payments infrastructure for online marketplaces. "
          "We need someone who has run large distributed systems in production.",
    years=(5, 12),
    titles=("Senior Backend Engineer", "Platform Engineer", "Site Reliability Engineer", "Software Engineer"),
    criteria=(
        Criterion("go_lang", "must", "Production Go experience", (
            T("Wrote the event ingestion service in Go, handling {n}k requests per second", ("Go",)),
            T("Built a Go-based rate limiter used by {m} internal services", ("Go",)),
        )),
        Criterion("kubernetes", "must", "Operated Kubernetes in production", (
            T("Ran {m} production Kubernetes clusters across {k} regions", ("Kubernetes",)),
            T("Migrated {m} services from VMs to Kubernetes with zero downtime", ("Kubernetes",)),
        )),
        Criterion("distributed_scale", "must", "Built distributed systems at high scale", (
            T("Designed a sharded queueing system processing {n} million events per day", ()),
            T("Scaled the payments ledger to {n} million transactions per day across {k} data centres", ()),
        )),
        Criterion("postgres", "nice", "Deep Postgres experience", (
            T("Tuned Postgres for a {m} TB dataset, cutting p99 query latency by {p}%", ("Postgres",)),
        )),
        Criterion("incident", "nice", "Led incident response or on-call", (
            T("Led incident response for {k} SEV-1 outages and ran the on-call rotation", ()),
            T("Ran on-call for a platform team of {m} engineers", ()),
        )),
        Criterion("terraform", "nice", "Infrastructure as code with Terraform", (
            T("Managed all infrastructure as code in Terraform across {m} AWS accounts", ("Terraform", "AWS")),
        )),
    ),
    distractors=(
        T("Built internal admin tools in Ruby on Rails used by {n} support staff", ("Ruby on Rails",)),
        T("Wrote Java services for the billing team, {m} services in total", ("Java",)),
        T("Set up Grafana dashboards covering {n} key service metrics", ("Grafana",)),
        T("Automated deploys with Ansible for {m} legacy servers", ("Ansible",)),
        T("Maintained a MySQL reporting database of {n} GB", ("MySQL",)),
    ),
)

BRIEF_C = Brief(
    id="C",
    title="Machine Learning Engineer, LLM Applications",
    company="Kestrel Data",
    blurb="Kestrel Data builds AI assistants for customer support teams. "
          "We need someone who has shipped LLM features and knows how to evaluate them.",
    years=(3, 9),
    titles=("Machine Learning Engineer", "Senior ML Engineer", "Data Scientist", "Software Engineer"),
    criteria=(
        Criterion("python", "must", "Production Python experience", (
            T("Built data pipelines in Python processing {n} GB a day", ("Python",)),
            T("Maintained the Python model-serving codebase for {m} production models", ("Python",)),
        )),
        Criterion("llm_prod", "must", "Shipped LLM features to production (RAG, agents)", (
            T("Shipped a RAG-based support assistant to production, resolving {p}% of tickets without escalation", ("RAG",)),
            T("Built an LLM agent in production that drafts {n}k customer emails a month", ("LLM",)),
        )),
        Criterion("evals", "must", "Built evaluation pipelines for ML or LLM systems", (
            T("Built the evaluation pipeline for the company's LLM features: {n} test cases run on every release", ("LLM",)),
            T("Designed offline evaluation suites for {m} ML models, gating releases on regression checks", ()),
        )),
        Criterion("pytorch", "nice", "PyTorch model training or fine-tuning", (
            T("Fine-tuned transformer models in PyTorch on {n} million labelled examples", ("PyTorch",)),
        ), requires=("python",)),
        Criterion("vector_db", "nice", "Vector databases or retrieval infrastructure", (
            T("Ran retrieval over {n} million embeddings stored in pgvector", ("pgvector",)),
            T("Operated a Qdrant vector database holding {n} million vectors", ("Qdrant",)),
        )),
        Criterion("fastapi", "nice", "Built APIs with FastAPI", (
            T("Exposed model inference through FastAPI services handling {n} requests per second", ("FastAPI",)),
        ), requires=("python",)),
    ),
    distractors=(
        T("Built churn models in scikit-learn that reduced churn by {p}%", ("scikit-learn",)),
        T("Created Tableau dashboards for {m} business teams", ("Tableau",)),
        T("Ran {n} A/B pricing experiments with the growth team", ()),
        T("Built Spark jobs in Scala processing {n} GB a day", ("Spark", "Scala")),
    ),
)

BRIEFS: dict[str, Brief] = {b.id: b for b in (BRIEF_A, BRIEF_B, BRIEF_C)}

# Named technologies across every brief. A rewrite may not introduce one of
# these unless the candidate's own facts contain it.
VOCAB: tuple[str, ...] = tuple(sorted({
    tok
    for b in BRIEFS.values()
    for tpl in [*(t for c in b.criteria for t in c.templates), *b.distractors]
    for tok in tpl.tokens
} | {"Docker"}))

RATINGS = ("poor", "okay", "good", "great")
RATING_SCORE = {r: i for i, r in enumerate(RATINGS)}

RATING_GUIDE = (
    "Rating scale:\n"
    "- great: meets every must-have and several nice-to-haves\n"
    "- good: meets the must-haves\n"
    "- okay: meets some must-haves; notable gaps\n"
    "- poor: little alignment with the brief"
)


def reference_tier(musts_met: int, nices_met: int, n_musts: int = 3) -> str:
    """Rubric used both to define the synthetic ground truth and by the facts-first scorer."""
    if musts_met >= n_musts and nices_met >= 2:
        return "great"
    if musts_met >= n_musts:
        return "good"
    if musts_met == n_musts - 1:
        return "okay"
    return "poor"
