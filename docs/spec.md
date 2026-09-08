# Distillr, product specification

**One line:** Distillr is a unified compression pipeline for LLM inputs. It trims what is irrelevant, re-encodes what is left in a token-efficient format, and tells you exactly how much you saved and whether it is safe to trust.

## 1. Vision and goal

Every team sending structured or semi-structured data to an LLM pays a "syntax tax": repeated JSON keys, irrelevant rows, stale context, verbose formatting. Point tools exist for pieces of this (LLMLingua for semantic trimming, TOON for compact encoding, RAG frameworks for retrieval) but nobody combines them into one pipeline with visibility into what each stage saved and whether the compression is safe.

**Goal:** become the default layer teams drop between their app and their LLM provider to cut token spend, without a PhD in prompt engineering and without silently dropping information the model needed.

**Primary success metric:** tokens saved per dollar spent on Distillr, visible in a dashboard, not just claimed in a README.

## 2. Differentiator

| Competitor | What they do | What they do not do |
|---|---|---|
| LLMLingua (Microsoft) | Semantic token pruning via a small LM | No retrieval stage, no format layer, no observability; research tool, not a product |
| TOON / TRON / ONTO | Compact serialization formats | Format only; does not decide what data to send |
| leanctx | SDK wrapper around LLMLingua-2 | Single technique, no dashboard, no proxy, no retrieval stage |
| llmslim | Semantic chunking + extractive ranking | No format-layer compression, no hosted layer |
| RAG frameworks | Retrieval | Not built for token accounting or format compression |

Three things nobody else has together:

1. **Unified pipeline.** Retrieval trimming, semantic compression, format encoding as configurable stages in one engine.
2. **Audit survivability.** Every stage tags what it removed. If the model's answer references something that got trimmed, Distillr flags it.
3. **Observability as the product.** A dashboard of token spend, savings percentage and accuracy-risk trends. The OSS engine drives adoption; the dashboard is what a team pays for.

Explicitly not doing: training or fine-tuning models, replacing RAG frameworks, competing with TOON on format innovation.

## 3. Product scope

**Open source:** core engine (retrieve, semantic, encode, audit stages), CLI (`distillr analyze`), Python and JS/TS SDKs, self-hosted proxy (Docker), format adapters (TOON, compact JSON, CSV).

**Hosted / paid:** hosted proxy (point `base_url` at Distillr), dashboard, audit-survivability monitoring, team accounts and API keys, usage-based billing, multi-provider routing, semantic caching.

## 4. Architecture

```
                 Distillr Core Engine (OSS, Python)
                 Stage 1 retrieve/trim  - keyword/structured, embedding-based (opt.)
                 Stage 2 semantic       - LLMLingua-2, configurable ratio
                 Stage 3 encode         - TOON / compact JSON / CSV, pluggable
                 Stage 4 audit          - tracks what was removed, flags risk per field
                        |
       SDK (Py/JS)   Proxy (OpenAI-compatible)   CLI (distillr analyze)
                        |
                 Token Ledger (local SQLite or hosted Postgres)
                 before/after, per-stage savings, audit flags
                        |
                 Hosted dashboard (paid tier)
```

**Key design principle:** the ledger is core from day one, even self-hosted, so the dashboard can exist later without re-architecting.

## 5. Tech stack

| Layer | Choice | Why |
|---|---|---|
| Core engine | Python | Where LLMLingua, tokenizers and the ML ecosystem live |
| SDK (secondary) | TypeScript | Most LLM app developers are in JS/TS |
| CLI | Python (Typer) | Ships fast, shares code with the engine |
| Proxy | Python (FastAPI) | Async, mirrors the OpenAI request shape, no serialization boundary |
| Token counting | tiktoken + provider tokenizers | Accuracy is the product's core value |
| Dashboard | Next.js + Tailwind + shadcn/ui | Fast to build, what technical buyers expect |
| Dashboard API | FastAPI (shared with proxy) | One less service early on |
| Ledger store | SQLite self-hosted, PostgreSQL hosted | Zero-config locally, multi-tenant hosted |
| Auth / billing | Clerk or Auth0, Stripe usage-based | Do not build these |
| Deployment | Fly.io or Railway, Kubernetes later | Avoid premature infra |
| Semantic model | LLMLingua-2 via `llmlingua` | Do not train our own |

## 6. Build order

**Phase 0, validate the core claim (1-2 weeks):** Stage 1 + Stage 3, CLI `distillr analyze`, benchmark on 3-5 realistic payload types. Success gate: a believable 50-70%+ reduction on real data without hurting a downstream task. If not, rethink the premise.

**Phase 1, OSS release (2-4 weeks):** Stage 2 (LLMLingua-2) and Stage 4 (audit), Python SDK, self-hosted proxy, README with benchmark table and positioning, ship on GitHub and community lists.

**Phase 2, hosted wedge (4-8 weeks, after real users):** ledger + minimal dashboard, hosted proxy, Stripe usage billing, 5-10 design partners before charging.

**Phase 3, expand (after PMF signal):** multi-provider routing, semantic caching, TS/JS SDK, enterprise features.

## 7. Repository structure

```
distillr/
  distillr/core/stages/{retrieve,semantic,encode,audit}.py
  distillr/core/{pipeline,ledger,tokenizers,payload,toon}.py
  distillr/cli.py
  benchmarks/            sample payloads + token/recall benchmarks
  docs/
  (later) proxy/, sdk-js/, dashboard/
```

## 8. Business model

Self-hosted / OSS free forever. Hosted proxy + dashboard priced per million tokens processed. Enterprise: SSO, on-prem, audit retention, SLA, flat annual pricing.

## 9. Immediate next step

Build Phase 0 first. Do not touch the dashboard, proxy or billing until the compression claim is validated on real, varied payloads with believable numbers.
