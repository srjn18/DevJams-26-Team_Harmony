// ContextFlow — Context Optimization Engine Frontend Logic

let waterfallChartInstance = null;

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

Policy Article 14: Refund Eligibility and Processing Window
For Enterprise Tier annual subscriptions, customers may request a full 100% refund within 30 calendar days of initial purchase or annual renewal date. Refund requests submitted between 31 and 60 days are eligible for a 50% pro-rated refund. Any cancellation request submitted after 60 days is non-refundable.

Policy Article 22: Payment Gateway Processing Times
Please note that once an authorized refund is approved by our billing department, it typically takes between 3 to 5 business days for Stripe or the merchant bank to credit the funds back to your original payment method.

Constraint: When calculating refund eligibility, DO NOT provide estimates for third-party add-on licenses, which are strictly non-refundable under Section 4.b.`,
    budget: 250
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
When a client exceeds the allocated threshold, the gateway returns HTTP 429 Too Many Requests with a 'Retry-After' response header.

Section 4: Legacy Deprecation Schedule
The v1 API endpoints will reach end-of-life on December 31, 2026. All legacy clients should transition to v2 schemas prior to Q4 maintenance windows.`,
    budget: 220
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
Enterprise license rate is set to $999/mo per primary database instance.

Section 3: Historical Migration Notes
It is important to note that during Q2 we evaluated various document stores. Please be aware that historical benchmarks from 2021 are archived in cold storage. In order to maintain SOC2 compliance, all audit logs are retained for 365 days.`,
    budget: 180
  },

  logs: {
    query: "Identify the root cause and failing service for error code ERR_DB_POOL_EXHAUSTED",
    context: `[2026-08-29T10:15:22.102Z] INFO [AuthService] User session validated for uid=8921.
[2026-08-29T10:15:23.441Z] ERROR [PaymentService] Database connection timed out after 30000ms. Error: ERR_DB_POOL_EXHAUSTED. Maximum pool size (50 connections) reached while executing transaction commit.
[2026-08-29T10:15:23.442Z] ERROR [PaymentService] Database connection timed out after 30000ms. Error: ERR_DB_POOL_EXHAUSTED. Maximum pool size (50 connections) reached while executing transaction commit.
[2026-08-29T10:15:24.110Z] INFO [NotificationService] Queued email notification to user@domain.com.
[2026-08-29T10:15:25.889Z] ERROR [PaymentService] Database connection timed out after 30000ms. Error: ERR_DB_POOL_EXHAUSTED. Maximum pool size (50 connections) reached while executing transaction commit.
[2026-08-29T10:15:26.002Z] WARN [Gateway] Circuit breaker tripped for PaymentService due to elevated failure rate (45% error threshold exceeded).`,
    budget: 130
  },

  skip: {
    query: "What is the capital of France?",
    context: "Paris is the capital and most populous city of France.",
    budget: 150
  }
};

document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    lucide.createIcons();
  }

  // Setup Budget Controls sync
  const budgetRange = document.getElementById("budgetRange");
  const budgetNumber = document.getElementById("budgetNumber");
  const budgetDisplay = document.getElementById("budgetDisplay");

  const syncBudget = (val) => {
    const num = parseInt(val, 10) || 50;
    budgetRange.value = num;
    budgetNumber.value = num;
    budgetDisplay.textContent = `${num} tokens`;
  };

  budgetRange.addEventListener("input", (e) => syncBudget(e.target.value));
  budgetNumber.addEventListener("input", (e) => syncBudget(e.target.value));

  // Context text change counter
  const contextInput = document.getElementById("contextInput");
  const liveTokenCounter = document.getElementById("liveTokenCounter");
  const contextCharCount = document.getElementById("contextCharCount");

  const updateContextStats = () => {
    const text = contextInput.value || "";
    if (contextCharCount) contextCharCount.textContent = `${text.length} chars`;
    const words = text.trim().split(/\s+/).filter(Boolean).length;
    const estTokens = Math.max(Math.ceil(text.length / 4), Math.ceil(words * 1.3));
    liveTokenCounter.textContent = `~${text.length > 0 ? estTokens : 0} tokens`;
  };

  contextInput.addEventListener("input", updateContextStats);

  // Initialize Waterfall Chart
  initWaterfallChart([0, 0, 0, 0, 0]);

  // Load default preset
  loadPreset("support");
});

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
  }, 2500);
}

function switchViewTab(tabId) {
  const views = {
    engine: document.getElementById("viewEngine"),
    adversarial: document.getElementById("viewAdversarial"),
    architecture: document.getElementById("viewArchitecture"),
    figma: document.getElementById("viewFigma"),
    docs: document.getElementById("viewDocs")
  };

  const buttons = {
    engine: document.getElementById("tabBtnEngine"),
    adversarial: document.getElementById("tabBtnAdversarial"),
    architecture: document.getElementById("tabBtnArchitecture"),
    figma: document.getElementById("tabBtnFigma"),
    docs: document.getElementById("tabBtnDocs")
  };

  // Hide all views & reset button styles
  Object.keys(views).forEach(k => {
    if (views[k]) views[k].classList.add("hidden");
    if (buttons[k]) {
      buttons[k].className = "px-3 py-1.5 rounded-lg font-medium transition text-slate-400 hover:text-slate-200 flex items-center space-x-1.5";
    }
  });

  // Activate selected tab
  if (views[tabId]) views[tabId].classList.remove("hidden");
  if (buttons[tabId]) {
    const activeColor = tabId === 'figma' ? 'bg-pink-500/20 text-pink-300 border-pink-500/30' :
                        tabId === 'adversarial' ? 'bg-amber-500/20 text-amber-300 border-amber-500/30' :
                        tabId === 'architecture' ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30' :
                        tabId === 'docs' ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30' :
                        'bg-emerald-500/20 text-emerald-300 border-emerald-500/30';
    buttons[tabId].className = `px-3 py-1.5 rounded-lg font-medium transition border ${activeColor} flex items-center space-x-1.5`;
  }

  if (window.lucide) {
    lucide.createIcons();
  }
}

function loadPreset(name) {
  const p = PRESETS[name];
  if (!p) return;

  document.getElementById("queryInput").value = p.query;
  document.getElementById("contextInput").value = p.context;
  
  const budgetRange = document.getElementById("budgetRange");
  const budgetNumber = document.getElementById("budgetNumber");
  const budgetDisplay = document.getElementById("budgetDisplay");
  
  budgetRange.value = p.budget;
  budgetNumber.value = p.budget;
  budgetDisplay.textContent = `${p.budget} tokens`;

  const event = new Event('input', { bubbles: true });
  document.getElementById("contextInput").dispatchEvent(event);
  showToast(`Loaded "${name}" benchmark preset.`);
}

function clearContextInput() {
  document.getElementById("contextInput").value = "";
  const event = new Event('input', { bubbles: true });
  document.getElementById("contextInput").dispatchEvent(event);
  showToast("Context cleared.");
}

function runAdversarialCase(caseNum) {
  if (caseNum === 1) {
    document.getElementById("queryInput").value = "Which database should we use for this project?";
    document.getElementById("contextInput").value = `System: You are an enterprise backend architect.

Constraint: DO NOT use MongoDB for this project under any circumstances.
Constraint: All API keys MUST be rotated every 90 days.

Section 1: Database Strategy
We decided to use PostgreSQL for relational transactional workloads.
The team historically discussed MongoDB, but it is explicitly off the table.`;
    document.getElementById("budgetNumber").value = 120;
    document.getElementById("budgetRange").value = 120;
    document.getElementById("budgetDisplay").textContent = "120 tokens";
  } else if (caseNum === 2) {
    document.getElementById("queryInput").value = "What is the timeout duration and license cost?";
    document.getElementById("contextInput").value = `System: Cloud compliance officer.

Constraint: Timeout is set to 30s.
Rule: Enterprise license SLA is $999/mo with 30 calendar days refund window.

Section 1: General Notes
Various historical notes from 2021 are archived in cold storage.`;
    document.getElementById("budgetNumber").value = 100;
    document.getElementById("budgetRange").value = 100;
    document.getElementById("budgetDisplay").textContent = "100 tokens";
  } else if (caseNum === 3) {
    document.getElementById("queryInput").value = "Is the API stateless?";
    document.getElementById("contextInput").value = `System: API Architect.

Constraint: The API must remain stateless even under load.
Note: Ideally the API would support offline mode in future quarters.

Section 1: Architecture
Ingress gateways terminate TLS and route requests to microservices.`;
    document.getElementById("budgetNumber").value = 110;
    document.getElementById("budgetRange").value = 110;
    document.getElementById("budgetDisplay").textContent = "110 tokens";
  } else if (caseNum === 4) {
    document.getElementById("queryInput").value = "What is the database roadmap?";
    document.getElementById("contextInput").value = `System: Infrastructure Lead.

Fact A: We use Postgres today.
Fact B: We're migrating off Postgres next quarter to Spanner.

Historical Info: Legacy Oracle migration was completed in 2022.`;
    document.getElementById("budgetNumber").value = 90;
    document.getElementById("budgetRange").value = 90;
    document.getElementById("budgetDisplay").textContent = "90 tokens";
  }

  const event = new Event('input', { bubbles: true });
  document.getElementById("contextInput").dispatchEvent(event);

  switchViewTab('engine');
  executeOptimize();
  showToast(`Running Adversarial Case ${caseNum}...`);
}

function initWaterfallChart(dataPoints) {
  const ctx = document.getElementById("waterfallChart").getContext("2d");
  
  if (waterfallChartInstance) {
    waterfallChartInstance.destroy();
  }

  waterfallChartInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: [
        "1. Original",
        "2. Relevance",
        "3. Dedup",
        "4. Compressed",
        "5. Final Budget"
      ],
      datasets: [{
        label: "Tokens",
        data: dataPoints,
        backgroundColor: [
          "rgba(148, 163, 184, 0.35)",
          "rgba(59, 130, 246, 0.45)",
          "rgba(6, 182, 212, 0.55)",
          "rgba(168, 85, 247, 0.65)",
          "rgba(16, 185, 129, 0.85)"
        ],
        borderColor: [
          "#94a3b8",
          "#3b82f6",
          "#06b6d4",
          "#a855f7",
          "#10b981"
        ],
        borderWidth: 1.5,
        borderRadius: 8,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (context) => ` ${context.raw} tokens`
          }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          grid: { color: "rgba(255, 255, 255, 0.05)" },
          ticks: { color: "#94a3b8", font: { family: "monospace" } }
        },
        x: {
          grid: { display: false },
          ticks: { color: "#cbd5e1", font: { size: 11 } }
        }
      }
    }
  });
}

function updateWaterfallChart(stageTokens) {
  if (!waterfallChartInstance || !stageTokens) return;
  const values = [
    stageTokens.original || 0,
    stageTokens.after_relevance || 0,
    stageTokens.after_dedup || 0,
    stageTokens.after_compression || 0,
    stageTokens.after_budget || 0,
  ];
  waterfallChartInstance.data.datasets[0].data = values;
  waterfallChartInstance.update();
}

function setRouteBadge(route) {
  const badge = document.getElementById("routeBadge");
  const headerBadge = document.getElementById("routeHeaderBadge");
  const headerVal = document.getElementById("routeHeaderValue");

  badge.textContent = `ROUTE: ${route}`;
  headerVal.textContent = route;
  headerBadge.classList.remove("hidden");

  let colorClasses = "bg-slate-900 text-slate-400 border-slate-700";
  if (route === "SKIP") {
    colorClasses = "bg-amber-500/10 text-amber-400 border-amber-500/30";
  } else if (route === "LIGHT") {
    colorClasses = "bg-cyan-500/10 text-cyan-400 border-cyan-500/30";
  } else if (route === "FULL") {
    colorClasses = "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
  }

  badge.className = `px-2.5 py-0.5 rounded text-[11px] font-mono font-bold border ${colorClasses}`;
  headerBadge.className = `px-2.5 py-1 rounded-lg text-xs font-mono font-semibold border ${colorClasses}`;
}

function handleFallbackUI(fallbackTriggered, fallbackReason) {
  const banner = document.getElementById("fallbackBanner");
  const reasonText = document.getElementById("fallbackReasonText");

  if (fallbackTriggered) {
    reasonText.textContent = fallbackReason || "Tier-2 compression failed. Gracefully fell back to Tier-1 output.";
    banner.classList.remove("hidden");
  } else {
    banner.classList.add("hidden");
  }
}

// ----------------------------------------------------------------------
// Action 1: POST /analyze
// ----------------------------------------------------------------------
async function executeAnalyze() {
  const query = document.getElementById("queryInput").value;
  const context = document.getElementById("contextInput").value;
  const budget = parseInt(document.getElementById("budgetNumber").value, 10);

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
    document.getElementById("metricOriginalTokens").textContent = data.original_tokens;
    document.getElementById("metricOptimizedTokens").textContent = "--";
    document.getElementById("metricReductionPct").textContent = "--%";
    document.getElementById("costBaseline").textContent = `$${data.estimated_cost.toFixed(5)}`;
    document.getElementById("reductionProgressBar").style.width = "0%";

    showToast(`Dry-Run Analyze: Route = ${data.route}`);
  } catch (err) {
    alert(`Analyze failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-50");
  }
}

// ----------------------------------------------------------------------
// Action 2: POST /optimize
// ----------------------------------------------------------------------
async function executeOptimize() {
  const query = document.getElementById("queryInput").value;
  const context = document.getElementById("contextInput").value;
  const budget = parseInt(document.getElementById("budgetNumber").value, 10);
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
        simulate_tier2_failure: simulateFailure
      })
    });

    if (!res.ok) {
      const errJson = await res.json();
      throw new Error(errJson.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderOptimizationResult(data);
    showToast(`Optimized! Reduced tokens by ${data.reduction_percentage}%`);
  } catch (err) {
    alert(`Optimize failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-50");
  }
}

// ----------------------------------------------------------------------
// Action 3: POST /optimize-and-answer
// ----------------------------------------------------------------------
async function executeOptimizeAndAnswer() {
  const query = document.getElementById("queryInput").value;
  const context = document.getElementById("contextInput").value;
  const budget = parseInt(document.getElementById("budgetNumber").value, 10);
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
        simulate_tier2_failure: simulateFailure
      })
    });

    if (!res.ok) {
      const errJson = await res.json();
      throw new Error(errJson.detail || `HTTP ${res.status}`);
    }
    const data = await res.json();
    renderOptimizationResult(data);

    // Render Answer and Quality
    document.getElementById("llmAnswerText").textContent = data.answer;
    document.getElementById("llmAnswerText").className = "text-slate-100 font-sans leading-relaxed";
    
    if (data.quality_score !== null && data.quality_score !== undefined) {
      document.getElementById("metricQualityScore").textContent = `${Math.round(data.quality_score * 100)}%`;
      document.getElementById("ansQualityBadge").textContent = `${Math.round(data.quality_score * 100)}% Faithfulness`;
    } else {
      document.getElementById("metricQualityScore").textContent = "100%";
      document.getElementById("ansQualityBadge").textContent = "100% Pinned Verified";
    }
    document.getElementById("llmLatencySub").textContent = `LLM: ${data.llm_latency_ms} ms`;
    document.getElementById("ansLatencyBadge").textContent = `Latency: ${data.llm_latency_ms} ms`;

    // Render Cost Comparison
    if (data.cost_comparison) {
      const cc = data.cost_comparison;
      document.getElementById("costBaseline").textContent = `$${cc.baseline_cost.toFixed(5)}`;
      document.getElementById("costOptimizer").textContent = `$${cc.optimizer_cost.toFixed(5)}`;
      document.getElementById("costOptimizedLLM").textContent = `$${cc.optimized_llm_cost.toFixed(5)}`;
      document.getElementById("costTotalOptimized").textContent = `$${cc.total_optimized_cost.toFixed(5)}`;
      document.getElementById("savingsPctBadge").textContent = `${cc.savings_percentage}% Saved`;
    }

    showToast("Optimization & LLM Inference complete!");
  } catch (err) {
    alert(`Optimize & Answer failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.classList.remove("opacity-50");
  }
}

// ----------------------------------------------------------------------
// Rendering Pipeline Output
// ----------------------------------------------------------------------
function renderOptimizationResult(data) {
  setRouteBadge(data.route);
  handleFallbackUI(data.trace.fallback_triggered, data.trace.fallback_reason);

  // Metrics
  document.getElementById("metricOriginalTokens").textContent = data.original_tokens;
  document.getElementById("metricOptimizedTokens").textContent = data.optimized_tokens;
  document.getElementById("metricReductionPct").textContent = `${data.reduction_percentage}%`;
  document.getElementById("reductionPctText").textContent = `${data.reduction_percentage}%`;
  document.getElementById("reductionProgressBar").style.width = `${Math.min(100, data.reduction_percentage)}%`;

  // Waterfall Chart
  updateWaterfallChart(data.trace.stage_tokens);

  // Latencies
  const lat = data.trace.stage_latency_ms;
  document.getElementById("metricTotalLatency").textContent = lat.total.toFixed(1);
  document.getElementById("latencySumDisplay").textContent = `Total: ${lat.total.toFixed(1)} ms`;
  document.getElementById("latChunking").textContent = `${lat.chunking.toFixed(2)} ms`;
  document.getElementById("latRelevance").textContent = `${lat.embedding_relevance.toFixed(2)} ms`;
  document.getElementById("latDedup").textContent = `${lat.dedup.toFixed(2)} ms`;
  document.getElementById("latCompression").textContent = `${lat.compression.toFixed(2)} ms`;
  document.getElementById("latAssembly").textContent = `${lat.assembly.toFixed(2)} ms`;

  const maxLat = Math.max(lat.chunking, lat.embedding_relevance, lat.dedup, lat.compression, lat.assembly, 0.1);
  document.getElementById("barLatChunking").style.width = `${(lat.chunking / maxLat) * 100}%`;
  document.getElementById("barLatRelevance").style.width = `${(lat.embedding_relevance / maxLat) * 100}%`;
  document.getElementById("barLatDedup").style.width = `${(lat.dedup / maxLat) * 100}%`;
  document.getElementById("barLatCompression").style.width = `${(lat.compression / maxLat) * 100}%`;
  document.getElementById("barLatAssembly").style.width = `${(lat.assembly / maxLat) * 100}%`;

  // Assembled Context
  document.getElementById("optimizedContextView").textContent = data.optimized_context || "(Empty Context)";

  // Chunk Counters
  document.getElementById("cntTotal").textContent = data.trace.chunks_total;
  document.getElementById("cntRemoved").textContent = data.trace.chunks_removed_irrelevant;
  document.getElementById("cntMerged").textContent = data.trace.chunks_merged_duplicate;
  document.getElementById("cntCompressed").textContent = data.trace.chunks_compressed;
  document.getElementById("cntPinned").textContent = data.trace.chunks_pinned_critical;

  // Chunk Table
  renderChunksTable(data.chunks_detail || []);
}

function renderChunksTable(chunks) {
  const tbody = document.getElementById("chunksTableBody");
  if (!chunks || chunks.length === 0) {
    tbody.innerHTML = `<tr><td colspan="7" class="py-6 text-center text-slate-500">No chunk metadata available.</td></tr>`;
    return;
  }

  const actionClasses = {
    pinned: "badge-pinned",
    kept: "badge-kept",
    filtered_irrelevant: "badge-filtered",
    merged_duplicate: "badge-merged",
    compressed: "badge-compressed"
  };

  const tagClasses = {
    system: "badge-tag-system",
    constraint: "badge-tag-constraint",
    generic: "badge-tag-generic",
    code: "badge-tag-generic",
    fact: "badge-tag-generic",
    dialogue: "badge-tag-generic"
  };

  const rowsHtml = chunks.map(c => {
    const actionBadgeClass = actionClasses[c.action_taken] || "badge-kept";
    const tagBadgeClass = tagClasses[c.tag] || "badge-tag-generic";
    const preview = (c.text || "").replace(/\n/g, " ");
    const previewTruncated = preview.length > 90 ? preview.substring(0, 90) + "..." : preview;

    return `
      <tr class="hover:bg-slate-900/60 transition border-b border-slate-800/40">
        <td class="py-2.5 px-3 text-slate-400 font-mono">${c.id}</td>
        <td class="py-2.5 px-3 text-slate-300 font-mono">#${c.position}</td>
        <td class="py-2.5 px-3">
          <span class="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold ${tagBadgeClass}">${c.tag}</span>
          ${c.is_critical ? '<span class="ml-1 text-emerald-400 font-bold" title="Critical Pinned">★</span>' : ''}
        </td>
        <td class="py-2.5 px-3 text-slate-200 font-mono">${c.token_count}</td>
        <td class="py-2.5 px-3 text-slate-300 font-mono">${(c.relevance_score * 100).toFixed(0)}%</td>
        <td class="py-2.5 px-3">
          <span class="px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${actionBadgeClass}">
            ${c.action_taken.replace('_', ' ')}
          </span>
        </td>
        <td class="py-2.5 px-4 text-slate-400 font-sans text-xs truncate max-w-xs" title="${escapeHtml(c.text)}">
          ${escapeHtml(previewTruncated)}
        </td>
      </tr>
    `;
  }).join("");

  tbody.innerHTML = rowsHtml;
}

function copyOptimizedContext() {
  const text = document.getElementById("optimizedContextView").textContent;
  if (!text || text.startsWith("No optimization")) return;
  navigator.clipboard.writeText(text);
  showToast("Optimized context copied to clipboard!");
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
