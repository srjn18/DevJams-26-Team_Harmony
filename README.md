<<<<<<< HEAD
# LLM Context Optimization Middleware

Middleware that sits between an app and an LLM. It cuts irrelevant/redundant
context, compresses what's useful, fits it into a token budget, and proves —
with measured numbers — that this saves tokens/cost/latency without wrecking
answer quality.

30-second pitch: *"LLM apps send huge, mostly-unnecessary contexts with every
request. We built middleware that analyzes token usage, filters context by
semantic relevance to the current query, scores importance, removes
redundancy, protects critical facts (constraints, numbers, negations),
compresses the rest, and fits it into a token budget — then measures the
before/after token savings, cost savings, latency, and answer quality."*

See `design.md` for the full technical spec. This file is the quickstart +
team map.

---

## Architecture (one paragraph)

Request → deterministic chunking + tagging (no paid calls) → cost-aware
routing decision (SKIP / LIGHT / FULL) → semantic relevance + dedup →
critical-info pinning + compression + token-budget knapsack → coherence
reassembly → LLM → evaluation (deterministic safety checks + LLM-judge
quality). Full detail: `design.md`.

---

## API

```
POST /analyze              → routing decision + cost estimate only
POST /optimize              → optimized context + trace, no LLM call
POST /optimize-and-answer   → /optimize then calls the LLM (demo endpoint)
```

Full request/response shapes are in `design.md` §11.

---

## Team map

| Person | Owns | Hardest part? |
|---|---|---|
| **Person 1** | Chunking, tagging, embeddings, relevance, dedup | No — but blocks everyone, ships stub first |
| **Person 2 (you)** | Critical-info detection, pinning, compression, coherence assembly, token budget | **Yes — see `HARDEST_PART.md`** |
| **Person 3** | LLM integration, cost model, routing decision, evaluation (both tracks), benchmark set | No |
| **Person 4** | Backend (3 endpoints), orchestration, fallback logic, dashboard | No |

Copy-paste briefs for each teammate's AI coding agent (Claude Code, etc.) are
in `AGENT_PROMPTS.md` — each includes the locked interface contract so nobody
is blocked waiting on someone else's real implementation.

---

## Hour 0–2: everyone does this together, no exceptions

1. Agree on the chunk schema in `design.md` §3 — do not modify without telling
   everyone.
2. Agree on the API contract in `design.md` §11.
3. Person 1 ships a **stub** module (hardcoded fake chunks + fake scores in
   the right shape) so Persons 2–4 can build against it immediately.
4. Everyone picks their `AGENT_PROMPTS.md` section and hands it to their AI
   agent as a starting brief.

---

## MVP scope

**Must have:** token counting, chunking, embeddings, relevance filtering,
compression, LLM integration, before/after token comparison, cost
calculation, basic evaluation.

**Should have:** semantic dedup, importance scoring, critical-info
protection, token budgets, cost-aware routing, latency measurement.

**Only if time remains:** long-term memory, advanced RAG, multiple LLM
providers, caching, persistent vector DB, advanced visualization.

**Explicitly not building:** a new LLM, a new embedding model, a tokenizer,
fine-tuning, a full RAG platform, a multi-agent architecture, a distributed
system, a vector DB unless genuinely required, multi-provider support,
production-grade infra.

---

## Timeline (48h)

- **0–2h**: architecture + contract lock, Person 1 ships stub
- **2–10h**: parallel build against stubs; Person 3 writes the adversarial
  test set *now*, in parallel with Person 2's detector (not after)
- **10–12h**: first integration, LIGHT path only (no compression) — smaller
  surface area to debug
- **12–18h**: add FULL path (compression + budget + coherence assembly); run
  adversarial suite continuously
- **18–26h**: real benchmark run (20–30 cases), cost-model routing tuned,
  per-stage latency wired into dashboard
- **26–32h**: fix whatever the adversarial suite still catches
- **32–38h**: freeze features; test fallback path (kill compression API
  mid-request, confirm graceful degradation)
- **38–44h**: demo script, dashboard polish, rehearsal
- **44–48h**: buffer only

---

## Core engineering principle

Do not optimize for maximum token reduction. Optimize for maximum useful
information retained per token. 90% reduction that breaks the answer is a
failure; 70% reduction that preserves quality is the win condition.

## Files in this repo

- `README.md` — this file
- `design.md` — full technical design
- `AGENT_PROMPTS.md` — ready-to-paste AI-agent briefs per teammate, with
  locked interface contracts
- `HARDEST_PART.md` — Person 2's spec, checklist, and starter code
  (critical-info protection + compression + budget engine)
- `tests/adversarial_cases.md` — the adversarial test set (negations,
  numbers, constraints, paraphrases) used to validate the hardest module
=======
# DevJams-26-Team_Harmony
>>>>>>> origin
