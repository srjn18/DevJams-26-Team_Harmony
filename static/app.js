// ==========================================================================
// AI Engine Optimization Dashboard (v2) — Side-by-Side 2 Windows Controller
// ==========================================================================

let efficiencyTrendChart = null;
let reqCounter = 0;
const historyBefore = [0, 0, 0, 0, 0, 0];
const historyAfter = [0, 0, 0, 0, 0, 0];
let activeOutputTab = "context"; // "context" | "answer"

const PRESETS = {
  support: {
    query: "What is the refund window and eligibility criteria for Enterprise Tier annual subscriptions?",
    context: `System: You are a professional customer support assistant for CloudScale SaaS. Always provide exact policy guidelines and remain courteous.

Customer: Hello there! Hope you are having a wonderful day today. I am reaching out regarding invoice #INV-98231. We had some internal discussions with our finance team last week about our subscription.
Support Agent: Hello! Thank you so much for contacting CloudScale customer support. I would be more than happy to help you with your inquiry regarding your subscription and billing details today.

Policy Article 12: General Subscription Overview
CloudScale offers three tiers: Starter, Growth, and Enterprise. Starter plans are billed monthly at $49/mo. Growth plans are billed at $199/mo. Enterprise plans start at $999/mo with dedicated SLAs.

Policy Article 14: Refund Eligibility and Processing Window
For Enterprise Tier annual subscriptions, customers may request a full 100% refund within 30 calendar days of initial purchase or annual renewal date. Refund requests submitted between 31 and 60 days are eligible for a 50% pro-rated refund. Any cancellation request submitted after 60 days is non-refundable.

Customer: We purchased the Enterprise annual plan on August 15th, so we are currently on day 14 of our billing cycle.
Support Agent: Understood! Because you are within the 30-day window, you qualify for a full 100% refund.

Constraint: When calculating refund eligibility, DO NOT provide estimates for third-party add-on licenses, which are strictly non-refundable under Section 4.b.`,
    budget: 8000
  },

  spec: {
    query: "What are the mandatory authentication and rate limit requirements for the v2 API endpoints?",
    context: `System: You are an enterprise API architect and security officer. Follow all compliance mandates strictly.

Constraint: MUST NOT allow unauthenticated access to /v2/* endpoints under any circumstances.
Constraint: API keys MUST be passed via the 'X-API-Key' authorization header with Bearer token authentication.

Section 1: Architecture Overview
The CloudNexus platform is built on a distributed microservices architecture deployed across multiple AWS regions using Kubernetes clusters. The ingress layer handles TLS termination and initial rate limiting before routing requests to internal gateway nodes.

Section 2: API v2 Authentication Standards
All requests to the CloudNexus v2 API endpoints require valid OAuth2 Bearer tokens or verified enterprise API keys passed in the 'X-API-Key' header. Requests with missing or expired credentials will immediately receive a 401 Unauthorized response code.

Section 3: Rate Limiting Guardrails
To prevent DDoS attacks and ensure fair resource allocation, rate limits are enforced per API tenant:
- Starter Tier: 60 requests per minute (burst 100).
- Enterprise Tier: 5,000 requests per minute (burst 10,000).
When a client exceeds the allocated threshold, the gateway returns HTTP 429 Too Many Requests with a 'Retry-After' response header.`,
    budget: 6000
  },

  adversarial: {
    query: "Which database should we choose and what are the timeout guardrails?",
    context: `System: You are a senior database architect. Enforce all system requirements without exception.

Constraint: DO NOT use MongoDB for this project under any circumstances.
Constraint: NEVER store unencrypted credentials or plain-text tokens in configuration files.

Section 1: Database Technology Decision
We chose PostgreSQL multi-region replication for transactional consistency. The cluster runs Aurora PostgreSQL 15.4 with automated failover in us-east-1.

Section 2: Timeout and Connection Pool Configurations
Timeout is set to 30 seconds for read queries. Write transactions time out after 45 seconds.
Enterprise license rate is set to $999/mo per primary database instance.`,
    budget: 4000
  },

  logs: {
    query: "Identify the root cause and failing service for error code ERR_DB_POOL_EXHAUSTED",
    context: `[2026-08-29T10:15:22.102Z] INFO [AuthService] User session validated for uid=8921.
[2026-08-29T10:15:23.441Z] ERROR [PaymentService] Database connection timed out after 30000ms. Error: ERR_DB_POOL_EXHAUSTED. Maximum pool size (50 connections) reached while executing transaction commit.
[2026-08-29T10:15:23.442Z] ERROR [PaymentService] Database connection timed out after 30000ms. Error: ERR_DB_POOL_EXHAUSTED. Maximum pool size (50 connections) reached while executing transaction commit.
[2026-08-29T10:15:24.110Z] INFO [NotificationService] Queued email notification to user@domain.com.
[2026-08-29T10:15:25.889Z] ERROR [PaymentService] Database connection timed out after 30000ms. Error: ERR_DB_POOL_EXHAUSTED. Maximum pool size (50 connections) reached while executing transaction commit.
[2026-08-29T10:15:26.002Z] WARN [Gateway] Circuit breaker tripped for PaymentService due to elevated failure rate (45% error threshold exceeded).`,
    budget: 3000
  },

  skip: {
    query: "What is the capital of France?",
    context: "Paris is the capital and most populous city of France.",
    budget: 5000
  }
};

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    lucide.createIcons();
  }

  // Setup input live counters
  const contextInput = document.getElementById("contextInput");
  if (contextInput) {
    contextInput.addEventListener("input", updateContextStats);
  }

  // Initialize Trend Chart
  initEfficiencyChart();

  // Load initial support preset
  loadPreset("support");
});

function updateContextStats() {
  const contextInput = document.getElementById("contextInput");
  const liveCharCount = document.getElementById("liveCharCount");
  const liveTokenEstimate = document.getElementById("liveTokenEstimate");

  if (!contextInput) return;
  const text = contextInput.value || "";
  const chars = text.length;
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  const estTokens = Math.max(Math.ceil(chars / 4), Math.ceil(words * 1.3));

  if (liveCharCount) liveCharCount.textContent = `${chars} chars`;
  if (liveTokenEstimate) liveTokenEstimate.textContent = `~${chars > 0 ? estTokens : 0} tokens`;
}

function showToast(message) {
  const toast = document.getElementById("toastNotification");
  const msgEl = document.getElementById("toastMessage");
  if (!toast || !msgEl) return;
  
  msgEl.textContent = message;
  toast.classList.remove("opacity-0", "translate-y-12", "pointer-events-none");
  toast.classList.add("opacity-100", "translate-y-0");

  setTimeout(() => {
    toast.classList.remove("opacity-100", "translate-y-0");
    toast.classList.add("opacity-0", "translate-y-12", "pointer-events-none");
  }, 3000);
}

function loadPreset(name) {
  const p = PRESETS[name];
  if (!p) return;

  const queryInput = document.getElementById("queryInput");
  const contextInput = document.getElementById("contextInput");
  const budgetInput = document.getElementById("tokenBudgetInput");

  if (queryInput) queryInput.value = p.query;
  if (contextInput) contextInput.value = p.context;
  if (budgetInput) budgetInput.value = p.budget;

  updateContextStats();
  showToast(`Loaded benchmark preset "${name.toUpperCase()}".`);
}

function clearContextInput() {
  const contextInput = document.getElementById("contextInput");
  if (contextInput) {
    contextInput.value = "";
    updateContextStats();
  }
  showToast("Context cleared.");
}

function createNewProject() {
  const contextInput = document.getElementById("contextInput");
  const queryInput = document.getElementById("queryInput");
  const budgetInput = document.getElementById("tokenBudgetInput");
  const simToggle = document.getElementById("simulateFailureToggle");

  if (contextInput) contextInput.value = "";
  if (queryInput) queryInput.value = "";
  if (budgetInput) budgetInput.value = 8000;
  if (simToggle) simToggle.checked = false;

  updateContextStats();

  // Reset Output views
  const optView = document.getElementById("optimizedContextView");
  if (optView) optView.textContent = "Optimized context returned from backend API will appear here after clicking Optimize...";

  const ansView = document.getElementById("llmAnswerView");
  if (ansView) ansView.innerHTML = '<p class="text-[#6B7280] italic">No answer generated yet. Click "Opt + Answer" to run optimization and downstream LLM inference.</p>';

  // Reset Badges & Summary Footer
  const outputTokenBadge = document.getElementById("outputTokenBadge");
  if (outputTokenBadge) outputTokenBadge.textContent = "0 tokens";

  const win2Tokens = document.getElementById("win2TokensSummary");
  if (win2Tokens) win2Tokens.textContent = "-- \u2192 --";

  const win2Saved = document.getElementById("win2SavedSummary");
  if (win2Saved) win2Saved.textContent = "--%";

  const win2Route = document.getElementById("win2RouteSummary");
  if (win2Route) win2Route.textContent = "--";

  const win2Lat = document.getElementById("win2LatencySummary");
  if (win2Lat) win2Lat.textContent = "-- ms";

  // Reset Diagnostic Metrics
  const origTok = document.getElementById("metricOriginalTokens");
  if (origTok) origTok.textContent = "0";

  const optTok = document.getElementById("metricOptimizedTokens");
  if (optTok) optTok.textContent = "0";

  const redPct = document.getElementById("metricReductionPct");
  if (redPct) redPct.textContent = "0.0%";

  const totLat = document.getElementById("metricTotalLatency");
  if (totLat) totLat.textContent = "0.0 ms";

  // Reset Latency Bars
  ["latChunking", "latRelevance", "latDedup", "latCompression", "latAssembly"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = "0.0 ms";
  });

  ["barLatChunking", "barLatRelevance", "barLatDedup", "barLatCompression", "barLatAssembly"].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.width = "0%";
  });

  // Reset Route Badge & Quality Badge
  setRouteBadge("READY");
  const qualBadge = document.getElementById("qualityScoreBadge");
  if (qualBadge) qualBadge.classList.add("hidden");

  // Reset Financial Summary
  const finSaving = document.getElementById("finExpectedSaving");
  if (finSaving) finSaving.textContent = "$0.000";

  const finCost = document.getElementById("finOptimizerCost");
  if (finCost) finCost.textContent = "$0.000";

  const finMargin = document.getElementById("finMargin");
  if (finMargin) finMargin.textContent = "$0.000";

  // Reset Chunks Table
  const tbody = document.getElementById("chunksTableBody");
  if (tbody) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-[#6B7280]">No chunk details available. Run an optimization pipeline to inspect chunks.</td></tr>`;
  }

  switchOutputTab("context");
  showToast("New project created. Inputs cleared.");
}

// Window 2 Output Tab Switcher
function switchOutputTab(tab) {
  activeOutputTab = tab;
  const tabContext = document.getElementById("outTabContext");
  const tabAnswer = document.getElementById("outTabAnswer");
  const viewContext = document.getElementById("optimizedContextView");
  const viewAnswer = document.getElementById("llmAnswerView");
  const label = document.getElementById("outputViewLabel");

  if (tab === "context") {
    if (tabContext) tabContext.className = "px-3 py-1 rounded-md text-xs font-semibold bg-[#E7F8F1] text-[#0E9F6E] border border-[#0E9F6E]/30 flex items-center space-x-1.5";
    if (tabAnswer) tabAnswer.className = "px-3 py-1 rounded-md text-xs font-medium text-[#6B7280] hover:text-[#1A1D23] flex items-center space-x-1.5";
    if (viewContext) viewContext.classList.remove("hidden");
    if (viewAnswer) viewAnswer.classList.add("hidden");
    if (label) label.textContent = "OPTIMIZED CONTEXT PAYLOAD (COMPRESSED BY ENGINE)";
  } else {
    if (tabContext) tabContext.className = "px-3 py-1 rounded-md text-xs font-medium text-[#6B7280] hover:text-[#1A1D23] flex items-center space-x-1.5";
    if (tabAnswer) tabAnswer.className = "px-3 py-1 rounded-md text-xs font-semibold bg-[#E7F8F1] text-[#0E9F6E] border border-[#0E9F6E]/30 flex items-center space-x-1.5";
    if (viewContext) viewContext.classList.add("hidden");
    if (viewAnswer) viewAnswer.classList.remove("hidden");
    if (label) label.textContent = "LLM INFERENCE RESPONSE (GENERATED ANSWER)";
  }
}

// Chart.js Stack Setup
function initEfficiencyChart() {
  const ctx = document.getElementById("efficiencyTrendChart");
  if (!ctx) return;

  efficiencyTrendChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: ["Req 1", "Req 2", "Req 3", "Req 4", "Req 5", "Req 6"],
      datasets: [
        {
          label: "Before Optimization",
          data: [...historyBefore],
          borderColor: "#DC4C4C",
          backgroundColor: "rgba(220, 76, 76, 0.1)",
          borderWidth: 2,
          pointBackgroundColor: "#DC4C4C",
          pointRadius: 3.5,
          tension: 0.3
        },
        {
          label: "After Optimization",
          data: [...historyAfter],
          borderColor: "#0E9F6E",
          backgroundColor: "rgba(14, 159, 110, 0.1)",
          borderWidth: 2,
          pointBackgroundColor: "#0E9F6E",
          pointRadius: 3.5,
          tension: 0.3
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          mode: "index",
          intersect: false,
          callbacks: {
            label: (ctx) => ` ${ctx.dataset.label}: ${ctx.raw} tokens`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "#E5E7EA" },
          ticks: { color: "#6B7280", font: { family: "monospace", size: 10 } }
        },
        x: {
          grid: { display: false },
          ticks: { color: "#6B7280", font: { size: 10 } }
        }
      }
    }
  });
}

function recordTrendDataPoint(beforeTokens, afterTokens) {
  if (!efficiencyTrendChart) return;

  const idx = reqCounter % 6;
  historyBefore[idx] = beforeTokens;
  historyAfter[idx] = afterTokens;
  reqCounter++;

  efficiencyTrendChart.data.datasets[0].data = [...historyBefore];
  efficiencyTrendChart.data.datasets[1].data = [...historyAfter];
  efficiencyTrendChart.update();

  const emptyCaption = document.getElementById("chartEmptyCaption");
  if (emptyCaption) emptyCaption.style.display = "none";
}

// ==========================================================================
// API Handlers (Wired directly to backend endpoints)
// ==========================================================================

// Action 1: POST /analyze
async function executeAnalyze() {
  const query = document.getElementById("queryInput").value;
  const context = document.getElementById("contextInput").value;
  const budget = parseInt(document.getElementById("tokenBudgetInput").value, 10) || 8000;

  const btn = document.getElementById("btnAnalyze");
  btn.disabled = true;
  btn.classList.add("opacity-50");

  try {
    const res = await fetch("/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, context, token_budget: budget })
    });

    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    setRouteBadge(data.route);
    document.getElementById("win2RouteSummary").textContent = data.route;
    document.getElementById("win2TokensSummary").textContent = `${data.original_tokens} \u2192 Est`;
    document.getElementById("win2SavedSummary").textContent = "--%";
    document.getElementById("win2LatencySummary").textContent = "-- ms";

    document.getElementById("metricOriginalTokens").textContent = data.original_tokens;
    document.getElementById("metricOptimizedTokens").textContent = "--";
    document.getElementById("metricReductionPct").textContent = "--%";

    showToast(`Analyze Only: Route = ${data.route}, Est Cost = $${data.estimated_cost.toFixed(5)}`);
  } catch (err) {
    alert(`Analyze failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-50");
  }
}

// Action 2: POST /optimize
async function executeOptimize() {
  const query = document.getElementById("queryInput").value;
  const context = document.getElementById("contextInput").value;
  const budget = parseInt(document.getElementById("tokenBudgetInput").value, 10) || 8000;
  const model = document.getElementById("modelSelect").value;
  const simulateFailure = document.getElementById("simulateFailureToggle").checked;

  const btn = document.getElementById("btnOptimize");
  btn.disabled = true;
  btn.classList.add("opacity-50");

  try {
    const res = await fetch("/optimize", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        context,
        token_budget: budget,
        model: model,
        simulate_tier2_failure: simulateFailure
      })
    });

    if (!res.ok) {
      const errJson = await res.json();
      throw new Error(errJson.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    renderOptimizationResult(data);
    recordTrendDataPoint(data.original_tokens, data.optimized_tokens);
    switchOutputTab("context");
    showToast(`Optimized! Reduced context size by ${data.reduction_percentage}%`);
  } catch (err) {
    alert(`Optimize failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-50");
  }
}

// Action 3: POST /optimize-and-answer
async function executeOptimizeAndAnswer() {
  const query = document.getElementById("queryInput").value;
  const context = document.getElementById("contextInput").value;
  const budget = parseInt(document.getElementById("tokenBudgetInput").value, 10) || 8000;
  const model = document.getElementById("modelSelect").value;
  const simulateFailure = document.getElementById("simulateFailureToggle").checked;

  const btn = document.getElementById("btnOptimizeAndAnswer");
  btn.disabled = true;
  btn.classList.add("opacity-50");

  try {
    const res = await fetch("/optimize-and-answer", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        context,
        token_budget: budget,
        model: model,
        simulate_tier2_failure: simulateFailure
      })
    });

    if (!res.ok) {
      const errJson = await res.json();
      throw new Error(errJson.detail || `HTTP ${res.status}`);
    }

    const data = await res.json();
    renderOptimizationResult(data);
    recordTrendDataPoint(data.original_tokens, data.optimized_tokens);

    // Render Answer Text inside Window 2 Answer Tab
    const viewAns = document.getElementById("llmAnswerView");
    if (viewAns) {
      viewAns.innerHTML = `<div class="space-y-1 p-1 text-xs font-sans leading-relaxed text-[#1A1D23]">${formatMarkdownToHtml(data.answer)}</div>
        <div class="pt-2 border-t border-[#E5E7EA] text-[11px] text-[#6B7280] flex items-center justify-between font-mono mt-3">
          <span>Inference Latency: ${data.llm_latency_ms} ms</span>
          <span class="text-[#0E9F6E] font-bold">Faithfulness: ${data.quality_score ? Math.round(data.quality_score * 100) + '%' : '100% Pinned'}</span>
        </div>`;
    }

    switchOutputTab("answer");

    // Faithfulness Badge in diagnostic header
    const qualBadge = document.getElementById("qualityScoreBadge");
    if (qualBadge) {
      qualBadge.classList.remove("hidden");
      if (data.quality_score !== null && data.quality_score !== undefined) {
        qualBadge.textContent = `${Math.round(data.quality_score * 100)}% Faithfulness`;
      } else {
        qualBadge.textContent = "100% Pinned Verified";
      }
    }

    // Render Financial Summary Card updates
    if (data.cost_comparison) {
      const cc = data.cost_comparison;
      const expectedSaving = cc.baseline_cost - cc.total_optimized_cost;
      const margin = expectedSaving - cc.optimizer_cost;

      document.getElementById("finExpectedSaving").textContent = `$${Math.max(0, expectedSaving).toFixed(4)}`;
      document.getElementById("finOptimizerCost").textContent = `$${cc.optimizer_cost.toFixed(4)}`;
      document.getElementById("finMargin").textContent = `$${Math.max(0, margin).toFixed(4)}`;

      const statusBanner = document.getElementById("finStatusBanner");
      if (statusBanner) {
        if (margin >= 0) {
          statusBanner.textContent = "✓ WORTH OPTIMIZING";
          statusBanner.className = "p-2.5 rounded-md text-center font-bold text-xs bg-[#E7F8F1] text-[#0E9F6E] border border-[#0E9F6E]/20";
        } else {
          statusBanner.textContent = "DIRECT PASSTHROUGH (SKIP)";
          statusBanner.className = "p-2.5 rounded-md text-center font-bold text-xs bg-[#FEF3C7] text-[#D97706] border border-[#D97706]/20";
        }
      }
    }

    showToast("Optimization & LLM Inference complete!");
  } catch (err) {
    alert(`Optimize & Answer failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-50");
  }
}

// ==========================================================================
// Rendering Pipeline Audit Outputs
// ==========================================================================
function renderOptimizationResult(data) {
  setRouteBadge(data.route);

  // Window 2 Badges & Summary Footer
  const tokenBadge = document.getElementById("outputTokenBadge");
  if (tokenBadge) tokenBadge.textContent = `${data.optimized_tokens} tokens`;

  document.getElementById("win2TokensSummary").textContent = `${data.original_tokens} \u2192 ${data.optimized_tokens}`;
  document.getElementById("win2SavedSummary").textContent = `${data.reduction_percentage}%`;
  document.getElementById("win2RouteSummary").textContent = data.route;
  document.getElementById("win2LatencySummary").textContent = `${data.trace.stage_latency_ms.total.toFixed(1)} ms`;

  // Diagnostic Metrics
  document.getElementById("metricOriginalTokens").textContent = data.original_tokens;
  document.getElementById("metricOptimizedTokens").textContent = data.optimized_tokens;
  document.getElementById("metricReductionPct").textContent = `${data.reduction_percentage}%`;
  document.getElementById("metricTotalLatency").textContent = `${data.trace.stage_latency_ms.total.toFixed(1)} ms`;

  // Latency Bars
  const lat = data.trace.stage_latency_ms;
  const maxLat = Math.max(lat.chunking, lat.embedding_relevance, lat.dedup, lat.compression, lat.assembly, 0.1);

  document.getElementById("latChunking").textContent = `${lat.chunking.toFixed(2)} ms`;
  document.getElementById("latRelevance").textContent = `${lat.embedding_relevance.toFixed(2)} ms`;
  document.getElementById("latDedup").textContent = `${lat.dedup.toFixed(2)} ms`;
  document.getElementById("latCompression").textContent = `${lat.compression.toFixed(2)} ms`;
  document.getElementById("latAssembly").textContent = `${lat.assembly.toFixed(2)} ms`;

  document.getElementById("barLatChunking").style.width = `${(lat.chunking / maxLat) * 100}%`;
  document.getElementById("barLatRelevance").style.width = `${(lat.embedding_relevance / maxLat) * 100}%`;
  document.getElementById("barLatDedup").style.width = `${(lat.dedup / maxLat) * 100}%`;
  document.getElementById("barLatCompression").style.width = `${(lat.compression / maxLat) * 100}%`;
  document.getElementById("barLatAssembly").style.width = `${(lat.assembly / maxLat) * 100}%`;

  // Assembled Context Output View
  document.getElementById("optimizedContextView").textContent = data.optimized_context || "(Empty Context)";

  // Chunk Table
  renderChunksTable(data.chunks_detail || []);
}

function renderChunksTable(chunks) {
  const tbody = document.getElementById("chunksTableBody");
  if (!chunks || chunks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-[#6B7280]">No chunk metadata available.</td></tr>`;
    return;
  }

  const actionClasses = {
    pinned: "badge-pinned",
    kept: "badge-kept",
    filtered_irrelevant: "badge-filtered",
    merged_duplicate: "badge-merged",
    compressed: "badge-compressed"
  };

  const rowsHtml = chunks.map(c => {
    const actionBadgeClass = actionClasses[c.action_taken] || "badge-kept";
    const preview = (c.text || "").replace(/\n/g, " ");
    const previewTruncated = preview.length > 90 ? preview.substring(0, 90) + "..." : preview;

    return `
      <tr class="hover:bg-[#F9FAFB] transition border-b border-[#E5E7EA]">
        <td class="py-2.5 px-3 text-[#6B7280] font-mono">${c.id}</td>
        <td class="py-2.5 px-3 text-[#1A1D23] font-mono">#${c.position}</td>
        <td class="py-2.5 px-3">
          <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold badge-tag-generic">${c.tag}</span>
          ${c.is_critical ? '<span class="ml-1 text-[#0E9F6E] font-bold" title="Critical Pinned">★</span>' : ''}
        </td>
        <td class="py-2.5 px-3 text-[#1A1D23] font-mono">${c.token_count}</td>
        <td class="py-2.5 px-3 text-[#6B7280] font-mono">${(c.relevance_score * 100).toFixed(0)}%</td>
        <td class="py-2.5 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${actionBadgeClass}">
            ${c.action_taken.replace('_', ' ')}
          </span>
        </td>
        <td class="py-2.5 px-4 text-[#6B7280] font-sans text-xs truncate max-w-xs" title="${escapeHtml(c.text)}">
          ${escapeHtml(previewTruncated)}
        </td>
      </tr>
    `;
  }).join("");

  tbody.innerHTML = rowsHtml;
}

function setRouteBadge(route) {
  const badge = document.getElementById("routeBadge");
  if (!badge) return;

  badge.textContent = `ROUTE: ${route}`;
  let colorClasses = "bg-[#E5E7EA] text-[#6B7280]";
  if (route === "SKIP") {
    colorClasses = "bg-[#FEF3C7] text-[#D97706] border border-[#D97706]/30";
  } else if (route === "LIGHT") {
    colorClasses = "bg-[#E0F2FE] text-[#0284C7] border border-[#0284C7]/30";
  } else if (route === "FULL") {
    colorClasses = "bg-[#E7F8F1] text-[#0E9F6E] border border-[#0E9F6E]/30";
  }
  badge.className = `px-2.5 py-0.5 rounded text-xs font-mono font-bold ${colorClasses}`;
}

function switchDiagTab(tab) {
  const vOverview = document.getElementById("diagViewOverview");
  const vChunks = document.getElementById("diagViewChunks");

  const btnOverview = document.getElementById("diagTabBtnOverview");
  const btnChunks = document.getElementById("diagTabBtnChunks");

  [vOverview, vChunks].forEach(v => v && v.classList.add("hidden"));
  [btnOverview, btnChunks].forEach(b => {
    if (b) {
      b.className = "pb-2 text-[#6B7280] hover:text-[#1A1D23]";
    }
  });

  if (tab === 'overview') {
    if (vOverview) vOverview.classList.remove("hidden");
    if (btnOverview) btnOverview.className = "pb-2 text-[#0E9F6E] border-b-2 border-[#0E9F6E] font-semibold";
  } else if (tab === 'chunks') {
    if (vChunks) vChunks.classList.remove("hidden");
    if (btnChunks) btnChunks.className = "pb-2 text-[#0E9F6E] border-b-2 border-[#0E9F6E] font-semibold";
  }
}

function copyOptimizedContext() {
  let text = "";
  if (activeOutputTab === "context") {
    text = document.getElementById("optimizedContextView").textContent;
  } else {
    text = document.getElementById("llmAnswerView").textContent;
  }

  if (!text || text.startsWith("Optimized context returned") || text.startsWith("No answer generated")) return;
  navigator.clipboard.writeText(text);
  showToast("Output text copied to clipboard!");
}

function formatMarkdownToHtml(rawText) {
  if (!rawText) return "";

  // 1. Strip raw leading prompt completion artifacts like "**Answer:**" or "Answer:"
  let text = rawText.replace(/^\s*\*\*(?:Answer|Response|Summary):\*\*\s*/i, "").trim();

  // 2. Format inline header breaks if text was crammed without newlines (e.g. "guidelines. **Refund Window:** Enterprise")
  text = text.replace(/([^\n])\s*(\*\*[A-Z][^*]+:\*\*)/g, "$1\n\n$2");

  // 3. Split into blocks/paragraphs by double line breaks
  const blocks = text.split(/\n\s*\n+/);

  const htmlBlocks = blocks.map(block => {
    let trimmed = block.trim();
    if (!trimmed) return "";

    // If block is a list (numbered 1. 2. 3. or bullet points -, *, •)
    if (/^(\d+\.|\-|\*|\•)\s/.test(trimmed)) {
      const lines = trimmed.split(/\n+/);
      const isNumbered = /^\d+\.\s/.test(lines[0]);
      
      const listItemsHtml = lines.map(line => {
        let content = line.replace(/^(\d+\.|\-|\*|\•)\s*/, "").trim();
        content = escapeHtml(content);
        // Replace **bold** text with strong tag
        content = content.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-[#1A1D23]">$1</strong>');
        return `<li class="ml-4 py-0.5 text-xs text-[#1A1D23] font-sans">${content}</li>`;
      }).join("");

      const listTag = isNumbered ? "ol" : "ul";
      const listClass = isNumbered ? "list-decimal space-y-1 my-2" : "list-disc space-y-1 my-2";
      return `<${listTag} class="${listClass}">${listItemsHtml}</${listTag}>`;
    }

    // Standard paragraph
    let formatted = escapeHtml(trimmed);
    // Replace **bold text** with clean strong tags
    formatted = formatted.replace(/\*\*(.*?)\*\*/g, '<strong class="font-semibold text-[#1A1D23]">$1</strong>');
    formatted = formatted.replace(/\*(.*?)\*/g, '<em class="text-[#4B5563]">$1</em>');
    formatted = formatted.replace(/\n/g, '<br/>');

    return `<p class="mb-2.5 leading-relaxed text-xs text-[#1A1D23] font-sans">${formatted}</p>`;
  });

  return htmlBlocks.filter(Boolean).join("");
}

function escapeHtml(str) {
  if (!str) return "";
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
