---
name: ContextFlow Design System
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#434655'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#737686'
  outline-variant: '#c3c6d7'
  surface-tint: '#0053db'
  primary: '#004ac6'
  on-primary: '#ffffff'
  primary-container: '#2563eb'
  on-primary-container: '#eeefff'
  inverse-primary: '#b4c5ff'
  secondary: '#006c49'
  on-secondary: '#ffffff'
  secondary-container: '#6cf8bb'
  on-secondary-container: '#00714d'
  tertiary: '#784b00'
  on-tertiary: '#ffffff'
  tertiary-container: '#996100'
  on-tertiary-container: '#ffeedd'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dbe1ff'
  primary-fixed-dim: '#b4c5ff'
  on-primary-fixed: '#00174b'
  on-primary-fixed-variant: '#003ea8'
  secondary-fixed: '#6ffbbe'
  secondary-fixed-dim: '#4edea3'
  on-secondary-fixed: '#002113'
  on-secondary-fixed-variant: '#005236'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-lg:
    fontFamily: Geist
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Geist
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  metric-xl:
    fontFamily: Geist
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.05em
  caption:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  headline-md-mobile:
    fontFamily: Geist
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  sidebar_width: 240px
  container_padding: 24px
  gutter: 16px
  card_padding: 20px
  stack_sm: 8px
  stack_md: 16px
  stack_lg: 24px
---

## Brand & Style

The design system for this context optimization engine is built on the principles of **Modern Corporate Minimalism**. It aims to evoke a sense of clarity, efficiency, and data-driven intelligence. The target audience consists of technical operators and business analysts who require a high "signal-to-noise" ratio in their workflows.

The visual language utilizes heavy whitespace, a refined light-mode palette, and high-quality typography to ensure that complex data visualizations remain legible. By using soft shadows and subtle tonal layering rather than harsh borders, the interface feels light and approachable while maintaining a professional, analytical rigour.

## Colors

This design system employs a professional palette designed for data density and status communication:

*   **Primary (Indigo/Blue):** Used for primary actions, active navigation states, and focus indicators.
*   **Success/Savings (Mint Green):** Reserved for positive growth metrics, "cost savings" indicators, and successful system statuses.
*   **Warning/Cost (Amber/Orange):** Used for cost-intensive alerts or metrics requiring attention without the urgency of a critical error.
*   **Neutrals:** A sophisticated range of cool grays. The background (#F8F9FA) provides a soft canvas that allows white cards (#FFFFFF) to pop through elevation rather than contrast.

## Typography

The typography strategy prioritizes legibility at various scales. **Geist** is used for headlines and high-impact metrics due to its precise, technical character and excellent kerning in bold weights. **Inter** handles the bulk of the body copy and UI labels, providing a neutral and highly readable foundation.

For dashboard metrics, use the `metric-xl` role. Ensure that labels paired with metrics use `label-sm` with increased letter spacing to create a clear visual hierarchy between the data point and its description.

## Layout & Spacing

The layout utilizes a **Fixed-Fluid Hybrid** model. The sidebar remains at a fixed width of 240px for desktop, while the main content area occupies the remaining width with a 12-column fluid grid.

*   **Margins & Gutters:** A consistent 24px margin is applied to the main viewport. Gutters between dashboard widgets are fixed at 16px to maintain high data density without feeling cluttered.
*   **Sidebar:** A "slim" profile sidebar on the left containing navigation links. On tablet/mobile, this collapses into a drawer.
*   **Rhythm:** Vertical spacing between elements within cards follows an 8px base grid (8, 16, 24).

## Elevation & Depth

Hierarchy is established through **Tonal Layering and Soft Shadows**. 

1.  **Level 0 (Background):** The base layer (#F8F9FA) is flat and non-interactive.
2.  **Level 1 (Cards/Sidebar):** White surfaces (#FFFFFF) that sit slightly above the background. These use a very soft, diffused shadow: `box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.03)`.
3.  **Level 2 (Popovers/Modals):** Elements that float above the primary UI. These use a more pronounced shadow with a wider blur radius to indicate temporary priority.

Avoid using borders for cards; use the contrast between the background and the white surface to define boundaries.

## Shapes

The design system uses a **Rounded** shape language to soften the "industrial" feel of data-heavy dashboards.

*   **Cards & Containers:** Use a 12px to 16px radius (`rounded-lg` or `rounded-xl` per variables) to create a modern, friendly frame for data.
*   **Buttons & Inputs:** Use the standard 8px (`rounded`) radius.
*   **Status Badges/Chips:** Use pill-shaped (full radius) rounding to distinguish them from interactive buttons.

## Components

### Metrics & Charts
*   **Metric Cards:** Feature a large `metric-xl` number. Trend indicators (arrows and percentages) should be placed immediately adjacent or below, colored with primary success or warning tones.
*   **Trend Indicators:** Use a background tint of the status color (e.g., 10% opacity Mint Green) with a dark green text for high legibility.

### Buttons & Inputs
*   **Primary Button:** Solid Indigo background with white text. High contrast, 8px corner radius.
*   **Ghost/Secondary Button:** Transparent background with an Indigo or Slate-400 outline.
*   **Inputs:** White background with a 1px Slate-200 border. On focus, the border transitions to Primary Indigo with a soft 2px glow.

### Navigation
*   **Sidebar Items:** Icons should be 20px, stroke-based. The active state is indicated by a subtle background shift (Slate-100) and a primary-colored vertical "pill" indicator on the left edge.

### Feedback
*   **Chips/Tags:** Use for status or categories. Small text (label-sm), pill-shaped, using low-saturation background tints.