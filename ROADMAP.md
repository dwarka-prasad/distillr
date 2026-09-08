# Roadmap

Phase 0 validated the core claim: on five realistic payload types Distillr removes 95% of tokens with 100% needle recall (see benchmarks/RESULTS.md).
The phases below follow the specification's order. Each item is a GitHub issue; **help wanted** ones are open to anyone and **good first issue** marks small, well-scoped starts. Comment on an issue to claim it.

Milestones: [Phase 1 · OSS release](https://github.com/dwarka-prasad/distillr/milestone/1) · [Phase 2 · Hosted wedge](https://github.com/dwarka-prasad/distillr/milestone/2) · [Phase 3 · Expand](https://github.com/dwarka-prasad/distillr/milestone/3)

## Phase 1 · OSS release

_LLMLingua-2 in the pipeline, audit polish, self-hosted proxy, PyPI release, positioning._ Target: 2026-10-15.

| # | Task | Open to |
|---|---|---|
| [#1](https://github.com/dwarka-prasad/distillr/issues/1) | Wire LLMLingua-2 (Stage 2) into the default pipeline behind the extra | help wanted |
| [#2](https://github.com/dwarka-prasad/distillr/issues/2) | Self-hosted OpenAI-compatible proxy (FastAPI) + Docker image | help wanted |
| [#3](https://github.com/dwarka-prasad/distillr/issues/3) | Publish to PyPI with trusted publishing on tag | good first issue |
| [#4](https://github.com/dwarka-prasad/distillr/issues/4) | Embedding-based ranking for Stage 1 | help wanted |
| [#5](https://github.com/dwarka-prasad/distillr/issues/5) | Audit checker v2: LLM-judge mode and better token matching | maintainer |
| [#6](https://github.com/dwarka-prasad/distillr/issues/6) | Benchmark on real public datasets, not only generated payloads | help wanted |
| [#7](https://github.com/dwarka-prasad/distillr/issues/7) | TOON: match the upstream spec test suite and add YAML output | help wanted, good first issue |

## Phase 2 · Hosted wedge

_Ledger on Postgres, dashboard, hosted proxy, usage billing, design partners._ Target: 2026-12-15.

| # | Task | Open to |
|---|---|---|
| [#8](https://github.com/dwarka-prasad/distillr/issues/8) | Ledger on PostgreSQL with the same schema; multi-tenant keys | maintainer |
| [#9](https://github.com/dwarka-prasad/distillr/issues/9) | Dashboard: savings over time, per endpoint, audit-risk trend | help wanted |
| [#10](https://github.com/dwarka-prasad/distillr/issues/10) | Hosted proxy: API keys, per-org quotas, usage-based billing (Stripe) | maintainer |

## Phase 3 · Expand

_Routing, semantic caching, TypeScript SDK, enterprise._ Target: 2027-03-31.

| # | Task | Open to |
|---|---|---|
| [#11](https://github.com/dwarka-prasad/distillr/issues/11) | Semantic caching of near-identical requests | maintainer |
| [#12](https://github.com/dwarka-prasad/distillr/issues/12) | Multi-provider routing: compress once, send to the cheapest capable model | maintainer |
| [#13](https://github.com/dwarka-prasad/distillr/issues/13) | TypeScript SDK (@distillr/node) | help wanted |
| [#14](https://github.com/dwarka-prasad/distillr/issues/14) | Enterprise: SSO, audit-log retention, on-prem hosted option | maintainer |

## Principles

- Self-hosted and OSS stay free. Core compression is never paywalled.
- Every stage records what it removed. Silent data loss is a bug.
- Token counts are measured, never estimated silently.
- We integrate LLMLingua and TOON; we do not reimplement them or train models.

## Not planned

- Training or fine-tuning compression models.
- Replacing vector stores or RAG frameworks.
