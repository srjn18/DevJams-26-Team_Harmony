# FRONTEND_DESIGN.md — AI Engine Optimization Dashboard (v2)

This supersedes the earlier ContextFlow layout with this updated reference.
Core visual language (palette, card style, typography) carries over
unchanged — what's different is the top navigation, sidebar structure, and
the input panel, which now exposes three distinct actions instead of one.
That three-action structure is worth calling out immediately:

> **The "Analyze Only / Optimize Context / Opt + Answer" buttons map
> directly, one-to-one, to your three already-built API endpoints:
> `/analyze`, `/optimize`, and `/optimize-and-answer`.** This is a good
> sign — it means the UI is a faithful surface for the architecture you
> already have, not a new shape you'd need to bend the backend to fit. Wire
> each button to its matching endpoint directly; don't build new backend
> logic to support this screen.

One more thing to flag before the token system: the reference image has a
black rounded outer frame with a small dot at the bottom center. That's a
device/browser chrome mockup wrapper around the design, not part of the
actual page — do not build a fake browser frame into the real site.

---

## 1. Design tokens

Unchanged from the previous spec — reuse these exactly:

| Token | Hex (approx) | Usage |
|---|---|---|
| `--bg-app` | `#F7F8FA` | Page background |
| `--bg-sidebar` | `#FFFFFF` | Sidebar background |
| `--bg-card` | `#FFFFFF` | Card surfaces |
| `--border-subtle` | `#E5E7EA` | Card borders, dividers, input borders |
| `--accent-primary` | `#0E9F6E` | Primary green — active nav, primary button, checkmarks, positive states |
| `--accent-primary-soft` | `#E7F8F1` | Light green backgrounds (active nav pill, "Worth Optimizing" banner, active sidebar item) |
| `--text-primary` | `#1A1D23` | Headings, primary values |
| `--text-secondary` | `#6B7280` | Labels, section eyebrows, muted text |
| `--text-placeholder` | `#9CA3AF` | Textarea/input placeholder copy |
| `--chart-line-before` | `#DC4C4C` | "Before Optimization" series |
| `--chart-line-after` | `#0E9F6E` | "After Optimization" series |

Typography, spacing, and border-radius rules from the previous spec also
carry over unchanged (Inter or similar neutral grotesque, 8px card radius,
tabular numerals for live-updating figures).

---

## 2. Layout structure

```
┌───────────────┬──────────────────────────────────────────────────────────┐
│ ⬢ AI Engine   │ Dashboard  Experiments  Models  Settings   🔔 ❓ Support [Deploy] ⚙│
│  V2.4.0-stable│──────────────────────────────────────────────────────────│
│───────────────│ Optimization Engine                                      │
│ [+ New Project]│                                                          │
│               │ ┌───────────────────────────┐ ┌────────────────────────┐│
│ ▦ Overview    │ │ RAW CONTEXT PAYLOAD         │ │ OPTIMIZATION SETTINGS  ││
│ ⚡ Optimization│ │ [ textarea ]                │ │ Model: GPT-4 Turbo  ▾  ││
│ ▤ Training Logs││                             │ │ [8000] Max Target Tokens││
│ ▥ Dataset Mgr │ │                             │ │                        ││
│ 🔑 API Keys    │ │                             │ │ [📊 Analyze Only]      ││
│               │ │ TARGET QUERY / USER INSTR.  │ │ [⚡ Optimize Context]  ││ <- primary filled
│               │ │ [ input field ]              │ │ [🔒 Opt + Answer]      ││
│               │ └───────────────────────────┘ └────────────────────────┘│
│               │──────────────────────────────────────────────────────────│
│               │ ┌───────────────────────────┐ ┌────────────────────────┐│
│               │ │ Token Efficiency Trend      │ │ Financial Summary      ││
│               │ │ ● Before  ● After            │ │ Expected saving  $0.41││
│               │ │  (chart area)                │ │ Optimizer cost   $0.003││
│               │ │  Req1 Req2 Req3 Req4 Req5 Req6│ │ Margin          $0.407││
│               │ │                              │ │ [✓ WORTH OPTIMIZING]  ││
│ 📖 Docs       │ │                              │ ├────────────────────────┤│
│ ⏻ Logout      │ │                              │ │ Compression Safety     ││
│               │ └───────────────────────────┘ └────────────────────────┘│
└───────────────┴──────────────────────────────────────────────────────────┘
```

Two-column layout below the top-level header: left column wider (~65%,
raw payload / trend chart), right column narrower (~35%, settings /
financial summary / compression safety) — same proportions as the previous
spec, just restructured content in the top section.

---

## 3. Component inventory

### 3.1 Top navigation bar (new — replaces the previous single-page top bar)
- Left: logo mark + "AI Engine" wordmark + version subtitle ("V2.4.0-stable"
  in `text-secondary`, small).
- Center-left: horizontal nav links — Dashboard, Experiments, Models,
  Settings. Plain text, `text-secondary`, no visible active-state
  underline in the reference (page identity is carried by the sidebar's
  active state instead — keep it that way, don't duplicate active-state
  logic in two places).
- Right: notification bell icon, help icon, "Support" text link, "Deploy"
  button (filled `accent-primary`, white text — this is a bigger, more
  prominent action than anything on the previous spec, since this looks
  like a broader ML-ops product surface, not just the optimization screen),
  and a circular avatar/settings icon at the far right.

### 3.2 Sidebar (revised)
- Logo block at top (can duplicate or omit vs. the top bar's logo — the
  reference shows it in both places, which is slightly redundant; your
  call whether to keep both or trim to one).
- **"+ New Project"** button — filled `accent-primary`, full sidebar width,
  rounded, sits above the nav list as the primary sidebar CTA.
- Nav list: Overview, Optimization (active — light green pill background,
  `accent-primary` text, small left accent bar visible in reference),
  Training Logs, Dataset Manager, API Keys. Each with a small line icon.
- Bottom-pinned: Docs, Logout — visually separated from the main nav list
  by a divider or just spacing, smaller/muted styling since these are
  secondary actions.

### 3.3 Raw Context Payload panel (was "context input textarea" in v1)
- Section label "RAW CONTEXT PAYLOAD" (small, uppercase, `text-secondary`,
  letter-spaced).
- Large textarea, placeholder: "Paste your massive JSON, document, or raw
  context here..." — this placeholder copy is good, plain-language,
  specific to what the field actually accepts (JSON, document, raw text) —
  keep it close to verbatim, it follows the writing guidance well
  (describes what the field does, not how the system works internally).
- Below it: "TARGET QUERY / USER INSTRUCTION" label + single-line input,
  placeholder "Enter query for context relevance filtering..." (same as
  v1 — keep unchanged).

### 3.4 Optimization Settings panel (new)
- Section label "OPTIMIZATION SETTINGS".
- Model selector dropdown, showing current model ("Model: GPT-4 Turbo").
  **Wire this to your actual `llm_provider.py` factory** — this dropdown
  is the natural UI surface for `LLM_PROVIDER` selection (Groq / Rakha,
  and whatever answer-generation model is active), not just decorative
  copy. Populate options from whatever providers are actually configured
  and available, not a hardcoded list that includes models you haven't
  wired up.
- "Max Target Tokens" numeric input (default shown: 8000) — this is your
  `token_budget` parameter, direct and literal. No translation needed.
- **Three action buttons, stacked vertically**, each mapped to a real
  endpoint:
  1. **"📊 Analyze Only"** — outlined/secondary button style (light border,
     no fill) → calls `/analyze`. Returns routing decision + cost estimate
     only, no pipeline execution. This should be visually the "lightest"
     action since it's the cheapest, fastest call.
  2. **"⚡ Optimize Context"** — filled `accent-primary`, the visually
     primary action of the three → calls `/optimize`. Runs the full
     pipeline, returns optimized context + trace, no LLM answer.
  3. **"🔒 Opt + Answer"** — outlined/secondary button style (same
     treatment as Analyze Only, i.e. NOT the primary visual weight even
     though it's arguably the "full" demo action) → calls
     `/optimize-and-answer`.

  On button-style choice: the reference makes "Optimize Context" the sole
  filled/primary button, with both "Analyze Only" and "Opt + Answer" as
  secondary outlined buttons. This is a deliberate hierarchy worth keeping
  — it signals "this is the core action, the other two are variants of it"
  rather than presenting three equally-weighted options, which would make
  the screen harder to scan quickly during a live demo.

### 3.5 Token Efficiency Trend chart
Same as v1's spec (§3.7 there) — line chart, red "Before Optimization" /
green "After Optimization" legend, x-axis labeled Req 1 through Req 6.

**Note on the reference image specifically**: the chart area here appears
to show an EMPTY/no-data state — flat baseline marks under each Req label
with no actual line series rendered. Treat this explicitly as the empty
state for this component (see §5) rather than assuming it's a rendering
error in the mockup — a dashboard that's just been opened with no
optimization history yet should look exactly like this, not show a fake
flat line pretending to be data.

### 3.6 Financial Summary card
Unchanged from v1 spec §3.8 — three line items (Expected saving, Optimizer
cost, Margin) + "WORTH OPTIMIZING" status banner.

### 3.7 Compression Safety card
Cut off in this reference image but present (visible card header at the
bottom) — carry over v1 spec §3.9 unchanged: 5-item checklist mapped to
`negation`/`number`/`constraint`/`error`/`decision`, plus "SAFE TO SEND"
banner.

---

## 4. Empty / loading states — now directly visible in this reference, design them deliberately

This version of the mockup actually shows you an empty state (the
data-less trend chart) rather than only the "everything succeeded" view
from v1. Use this as license to design the full state set properly:

- **Empty dashboard, no requests yet**: Token Efficiency Trend shows the
  flat baseline exactly as in this reference, x-axis labels present, no
  line drawn, no data points. Consider a small muted caption like "No
  optimization runs yet — results will appear here" rather than leaving it
  ambiguous whether it's broken or genuinely empty.
- **Analyze Only clicked**: this should update the Optimization Settings
  panel or a small inline result area with the routing decision
  (SKIP/LIGHT/FULL) and reasoning — decide where this result surfaces,
  since the reference doesn't show it. Simplest option: a small result
  banner appearing directly below the three buttons, not a separate page.
- **Optimize Context / Opt + Answer clicked, in progress**: the three
  buttons should show a loading state (spinner replacing the icon, text
  changes to "Optimizing…" or "Answering…"), and ideally the pipeline
  stage indicators from v1's spec (§3.6 there — CHUNK/RELEVANCE/DEDUP/
  COMPRESS/SAFETY) should appear somewhere on this screen to show real
  progress, since this reference doesn't include that component but your
  actual system has real per-stage timing to show. Consider adding it back
  in as a thin progress strip above or below the Financial Summary card.
- **Result populated**: Financial Summary, Compression Safety, and the
  trend chart's newest data point all update together from one completed
  request — don't update them independently/asynchronously in a way that
  could show inconsistent numbers mid-update.

All other failure/edge states (SKIP route, a critical flag not preserved,
`fallback_triggered`) carry over unchanged from v1 spec §7 — that reasoning
still applies regardless of which layout variant you build.

---

## 5. Data binding

Identical mapping to v1 spec §6 — every number still traces back to the
same real fields (`trace`, `RoutingDecision`, `AnswerQualityResult`). The
only new binding introduced by this layout:

| UI element | Source |
|---|---|
| Model dropdown selection | `llm_provider.get_active_provider()` / available configured providers |
| Max Target Tokens input | `token_budget` parameter passed into `/optimize` and `/optimize-and-answer` |
| Analyze Only result | `RoutingDecision` object (route, reasoning, estimated cost/savings) from `/analyze` |

---

## 6. Build notes

Same stack recommendation as v1: React, `recharts` for the trend chart,
`lucide-react` for icons (this version needs a few more: `LayoutGrid`,
`Zap`, `FileText`, `Database`, `Key`, `Book`, `LogOut`, `Bell`,
`HelpCircle`, `BarChart2`, `Lock`, `Plus`).

Do not build the outer black rounded device-frame from the reference image
— that's a presentation mockup border, not part of the actual site chrome.

Responsive note carries over from v1: sidebar collapses below ~768px; with
this version's added top nav, decide whether the top nav links (Dashboard/
Experiments/Models/Settings) collapse into a hamburger menu or get dropped
in favor of the sidebar nav on narrow viewports, since having both a
full top nav and a full sidebar nav on mobile would be redundant and
cramped.
