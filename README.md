# Token-Diet (ContextFlow): Intelligent LLM Context Optimization Middleware

## 🚀 Overview

**Token-Diet (ContextFlow)** is an intelligent context optimization middleware designed to reduce the number of tokens sent to Large Language Models (LLMs) while preserving the quality and relevance of their responses.

As LLM applications scale, large prompts and long conversation histories can become expensive and slow. A significant portion of the context sent to an LLM may be redundant, irrelevant, or unnecessarily verbose.

Token-Diet addresses this problem by intelligently analyzing, ranking, deduplicating, and compressing context before it reaches the LLM. The system dynamically decides how much optimization is required based on the size and characteristics of the input context.

## 🎯 Our Goal

> "Send only the context that the LLM actually needs — reducing token usage, cost, and latency without sacrificing answer quality."

---

## 💡 The Problem

Modern LLM applications frequently send large amounts of information with every request:
- Long conversation histories
- Repeated information
- Irrelevant documents & boilerplate
- Redundant passages
- Large retrieved knowledge bases

This creates three major problems:
- **💰 Higher Cost** — LLM APIs charge per token. More context → more tokens → higher cost.
- **⏱️ Higher Latency** — Larger prompts require more processing time from LLM providers.
- **🧠 Context Overload** — Excessive noise degrades reasoning and accuracy.

---

## 🧠 Our Solution

Token-Diet introduces a 6-stage cost-aware middleware proxy:
1. **Analyze Context & Cost Routing**: Decides dynamically whether to `SKIP`, run `LIGHT`, or execute `FULL` optimization.
2. **Semantic Ranking & Tagging**: Splits context into chunks and scores semantic similarity to the query.
3. **Deduplication & Fact Guarding**: Merges high-similarity duplicate chunks and preserves critical pinned constraints (negations, numbers, SLA terms).
4. **Contextual Compression**: Intelligently compresses non-critical chunks while protecting pinned items.
5. **Token Budget Enforcement & Coherence Assembly**: Fits surviving context into token limits and ensures prompt flow.
6. **Downstream LLM & Quality Evaluation**: Measures answer quality retention, token savings, and latency waterfall.

---

## 🏗️ System Architecture

### Pipeline Overview

```
    Query + Context
          │
          ▼
┌──────────────────────┐
│   Context Analyzer   │   Estimates cost vs savings
└──────────┬───────────┘
decides SKIP / LIGHT / FULL
           │
           ▼
┌──────────────────────┐
│  Optimization Layer  │   Ranks + compresses context
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│         LLM          │   Generates the final answer
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ Evaluation & Metrics │   Compares quality, cost, latency
└──────────────────────┘
```

### Routing Decision — The Cost-Aware Gate

```
                    Context Analyzer
                  Estimates cost vs savings
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
           SKIP            LIGHT           FULL
      Send as-is      Rank chunks only   Rank + compress
      no processing    no compression    + fit token budget
```

- **SKIP** — Context is small/cheap (< 120 tokens or within budget); sent as-is with zero overhead.
- **LIGHT** — Semantic ranking + deduplication only, no compression LLM call. Cheaper path for medium contexts.
- **FULL** — Full pipeline (ranking, deduplication, critical info protection, contextual compression, and budget packing).

---

## ⚙️ Modular Ownership & Team

| Person | Module / Role | Ownership |
|---|---|---|
| **Person 1 (Pratham)** | Semantic Relevance Engine | Chunking, embeddings, semantic scoring, deduplication (`semantic_relevance_engine/`, `person1_relevance.py`) |
| **Person 2 (Srujan)** | Critical Protection & Compression | Critical info protection, contextual compression, token budget enforcement (`person2_compression.py`) |
| **Person 3 (Vandya)** | Cost Routing & LLM Evaluation | Cost estimation, dynamic routing, LLM provider integration, answer quality evaluation (`person3_llm_eval.py`) |
| **Person 4 (Prathvik)** | Architecture, API & Orchestration | FastAPI middleware (3 endpoints), fallback handling, pipeline orchestration, dashboard (`app/`, `static/`) |

---

## 🚀 Quick Start

### 1. Install Dependencies
```powershell
pip install -r requirements.txt
pip install -e .
```

### 2. Environment Configuration
Copy `.env.example` to `.env` and configure your API keys (optional; fallback mock works out-of-the-box):
```powershell
cp .env.example .env
```

### 3. Launch Middleware & Dashboard
```powershell
python run.py
```
Open **http://127.0.0.1:8000** in your browser to interact with the **ContextFlow Optimization Dashboard**.

### 4. Run Test Suite
```powershell
pytest
```

---

## 🔌 API Endpoints

- `POST /analyze` — Fast cost estimation and routing decision (`SKIP` / `LIGHT` / `FULL`).
- `POST /optimize` — Core optimization pipeline returning token waterfall, trace, and compressed context.
- `POST /optimize-and-answer` — Full end-to-end endpoint with downstream LLM answering and quality evaluation.
- `GET /health` — Service health check.

---

## 📊 What We Measure

| Metric | Description |
|---|---|
| **Token Reduction** | Percentage of input tokens eliminated (typical: 60% – 75% savings) |
| **Cost Reduction** | Dollars saved on LLM input pricing |
| **Quality Retention** | Semantic accuracy of downstream answer compared to uncompressed context |
| **Latency Waterfall** | Stage-by-stage execution time (chunking, relevance, dedup, compression, assembly) |

---

## 👨‍💻 Team Harmony — Token-Diet

*"Optimize the context. Reduce the tokens. Keep the intelligence."*
