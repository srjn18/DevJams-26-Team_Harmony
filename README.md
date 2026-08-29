# Token-Diet: Intelligent LLM Context Optimization

## 🚀 Overview

Token-Diet is an intelligent context optimization system designed to reduce the number of tokens sent to Large Language Models (LLMs) while preserving the quality and relevance of their responses.

As LLM applications scale, large prompts and long conversation histories can become expensive and slow. A significant portion of the context sent to an LLM may be redundant, irrelevant, or unnecessarily verbose.

Token-Diet addresses this problem by intelligently analyzing, ranking, and compressing context before it reaches the LLM.

The system dynamically decides how much optimization is required based on the size and characteristics of the input context.

## 🎯 Our Goal

> "Send only the context that the LLM actually needs — reducing token usage, cost, and latency without significantly affecting answer quality."

---

## 💡 The Problem

Modern LLM applications frequently send large amounts of information with every request:

- Long conversation histories
- Repeated information
- Irrelevant documents
- Redundant passages
- Large retrieved knowledge bases
- Previously answered information

This creates three major problems:

**💰 Higher Cost** — LLM APIs generally charge based on the number of input and output tokens. More context → more tokens → higher cost.

**⏱️ Higher Latency** — Larger prompts require more processing, which can increase response time.

**🧠 Context Overload** — Providing too much irrelevant information can make it harder for an LLM to identify the information that actually matters.

---

## 🧠 Our Solution

Token-Diet introduces an optimization layer between the application and the LLM. Instead of sending the query and raw context straight to the LLM, they first pass through the Token-Diet layer, which:

1. Analyzes the context
2. Ranks relevant content
3. Compresses the context
4. Evaluates the optimization

Only then does the optimized context reach the LLM, which returns the answer.

The optimization layer attempts to remove unnecessary tokens while retaining the information required to answer the user's query correctly.

---

## 🏗️ System Architecture

### Pipeline overview

```
Query + Context
      │
      ▼
┌─────────────────────┐
│  Context Analyzer    │   Estimates cost vs savings
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

### Routing decision — the cost-aware gate

Before doing any expensive work, the Context Analyzer decides how much optimization is actually worth running:

```
                    Context Analyzer
                  Estimates cost vs savings
                            │
              ┌─────────────┼─────────────┐
              ▼              ▼              ▼
           SKIP            LIGHT           FULL
      Send as-is      Rank chunks only   Rank + compress
      no processing    no compression    + fit token budget
```

- **SKIP** — context is already small/cheap enough; sent unchanged, no pipeline stages run.
- **LIGHT** — semantic ranking runs (relevance scoring + deduplication), but no compression LLM call. Cheaper path for medium-sized contexts.
- **FULL** — everything in LIGHT, plus compression, critical-info protection, and token-budget packing. Reserved for cases where the savings clearly outweigh the optimizer's own cost.

---

## ⚙️ How It Works

Token-Diet consists of multiple stages.

### 1. Context Analysis

The system first analyzes the incoming context and determines its size and characteristics. Based on this analysis, it decides whether optimization is necessary — and if so, how much (SKIP / LIGHT / FULL, as shown above). This prevents unnecessary processing for small inputs.

### 2. Semantic Relevance

The context is divided into meaningful chunks. Each chunk is evaluated based on how relevant it is to the user's query.

For example:

```
User Query:
"How does authentication work in our application?"

Context:
[1] Database schema
[2] Authentication middleware
[3] Login API
[4] CSS styling
[5] Authentication configuration
[6] Event registration system
```

The system prioritizes:
- Authentication middleware
- Login API
- Authentication configuration

while reducing the importance of unrelated information.

### 3. Context Compression

After identifying the most relevant information, the system compresses the context.

```
Original Context
      ↓
Remove redundancy
      ↓
Remove irrelevant information
      ↓
Preserve important information
      ↓
Optimized Context
```

The optimized context is then passed to the LLM instead of the original context.

### 4. LLM Response

The LLM receives the user query plus the optimized context, and generates the final response. This allows the application to potentially achieve lower token consumption, lower API costs, lower latency, smaller prompts, and better context utilization — while maintaining response quality.

### 5. Quality Evaluation

Optimization should not come at the cost of answer quality. Token-Diet compares the baseline response with the optimized response, measuring token reduction, cost reduction, response quality, quality retention, latency, and optimization overhead.

The objective is not simply to minimize tokens. It is to find the best balance between:

> "Token efficiency + Cost + Speed + Answer quality"

---

## 👥 Team

### Person 1 — Pratham
**Semantic Context Optimization**

Responsible for identifying the most relevant pieces of context for a given user query.

Responsibilities:
- Context chunking
- Semantic relevance analysis
- Ranking context
- Identifying important information
- Selecting relevant chunks for optimization

**Main Contribution:** "Find what information actually matters."

### Person 2 — Srujan
**Context Compression & Optimization**

Responsible for reducing the size of the selected context while preserving the important information.

Responsibilities:
- Context compression
- Removing redundant information
- Reducing unnecessary tokens
- Maintaining important semantic information
- Producing the optimized context

**Main Contribution:** "Make the relevant context smaller without losing its meaning."

### Person 3 — Vandya
**LLM Integration & Optimization Evaluation**

Responsible for connecting the optimization pipeline with the LLM and evaluating the impact of optimization.

Responsibilities:
- LLM integration
- Model interaction
- Baseline vs optimized execution
- Cost estimation
- Routing decisions
- Response quality evaluation
- Optimization metrics

**Main Contribution:** "Connect the optimized context to the LLM and measure whether the optimization actually helps."

### Person 4 — Prathvik
**Application Integration & API**

Responsible for integrating all the individual components into a complete application.

Responsibilities:
- API development
- Connecting all optimization modules
- User request handling
- Sending optimized context to the LLM
- Returning the final response
- Connecting the backend with the frontend
- End-to-end workflow

**Main Contribution:** "Bring all components together into a working application."

---

## 🔄 Complete Team Workflow

The four components work together as a single pipeline:

```

```

---

## 📊 What We Measure

| Metric | Description |
|---|---|
| Token Reduction | How many tokens were removed |
| Cost Reduction | Reduction in LLM API cost |
| Quality Retention | How much answer quality is preserved |
| Latency | Time taken to process the request |
| Optimization Overhead | Time/cost introduced by the optimization layer |

The ideal result is:

```
↓ Tokens
↓ Cost
↓ Latency
↑ Efficiency
≈ Answer Quality
```

---

## 🧪 Example

Suppose an application sends:

**Original Context:** 10,000 tokens

After semantic ranking: **Relevant Context:** 6,000 tokens

After compression: **Optimized Context:** 3,500 tokens

Instead of sending 10,000 tokens to the LLM, the application sends 3,500 tokens — while attempting to preserve the information necessary to answer the user's question. This can significantly reduce the amount of context processed by the model.

---

## 🛠️ Technology Stack

**Backend**
- Python
- FastAPI
- REST APIs

**AI / LLM**
- OpenAI API
- Anthropic API
- LLM-based evaluation

**Context Optimization**
- Semantic relevance ranking
- Token counting
- Context compression
- Dynamic routing

**Development**
- Git
- GitHub
- Pytest
- Environment-based configuration

---

## 📁 Project Structure

```
DevJams-26-Team_Harmony/
│
├── person1/
│   └── Semantic Optimization
│
├── person2/
│   └── Context Compression
│
├── person3/
│   ├── cost_model.py
│   ├── router.py
│   ├── llm_client.py
│   └── evaluator.py
│
├── person4/
│   └── Application / API Integration
│
├── benchmark/
│   └── dataset.json
│
├── tests/
│   └── test_person3.py
│
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

---

## 🔌 Integration Flow

The project is designed as modular components so that each part can be developed independently and then connected into a single pipeline.

```
Person 1  — Semantic Ranking
      │
      ▼
Person 2 — Compression
      │
      ▼
Person 3 — LLM + Evaluation
      │
      ▼
Person 4 — API / Application
```

Each module communicates through well-defined interfaces, making it easier to develop, test, and replace individual components.

---

## 🎯 Why Token-Diet?

LLMs are becoming a core part of modern applications, but context is becoming one of their biggest costs.

Token-Diet introduces an intelligent optimization layer that asks:

> "Do we really need to send all of this information to the LLM?"

Instead of blindly forwarding large contexts, the system attempts to intelligently determine:

1. What is relevant?
2. What can be removed?
3. What can be compressed?
4. How much optimization is worthwhile?
5. Did the optimization preserve answer quality?

---

## 🌟 Key Features

- 🧠 Semantic Context Ranking
- ✂️ Intelligent Context Compression
- 🚦 Dynamic Optimization Routing
- 🤖 LLM Integration
- 💰 Token & Cost Optimization
- ⚡ Latency Analysis
- 📊 Quality Evaluation
- 🔌 Modular Architecture
- 🔄 Baseline vs Optimized Comparison

---

## 🚀 Future Scope

Token-Diet can be extended with:

- Adaptive optimization based on model pricing
- Support for additional LLM providers
- Long-term conversation memory optimization
- Multimodal context optimization
- Real-time optimization dashboards
- Model-specific compression strategies
- Adaptive token budgets
- Learning-based routing
- Enterprise-scale optimization

---

## 👨‍💻 Team Harmony

| Member | Role |
|---|---|
| Pratham | Semantic Context Optimization |
| Srujan | Context Compression |
| Vandya | LLM Integration & Evaluation |
| Prathvik | Application & API Integration |

---

**🏆 Team Harmony — Token-Diet**

*"Optimize the context. Reduce the tokens. Keep the intelligence."*
