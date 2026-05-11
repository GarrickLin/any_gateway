# Any Gateway Stitch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the confirmed Stitch/Nexus visual design to `apps/react` while preserving all existing behavior.

**Architecture:** Add a scoped CSS design system in `apps/react/src/index.css`, then apply lightweight class-based structure changes to the Shell, Login, Dashboard, and Logs pages. Remaining pages inherit global Arco component styling and receive only minimal wrapper class cleanup when needed.

**Tech Stack:** React 19, TypeScript, Vite, Arco Design, React Router, Zustand, CSS.

---

## Reference Documents

- Spec: `docs/superpowers/specs/2026-05-11-any-gateway-stitch-design.md`
- Stitch references:
  - `docs/web_designs/stitch/any_gateway/code.html`
  - `docs/web_designs/stitch/dashboard/code.html`
  - `docs/web_designs/stitch/request_logs/code.html`
  - `docs/web_designs/stitch/nexus_dashboard_advanced/code.html`

## File Map

- Modify `apps/react/src/index.css`: global design tokens, scoped Arco overrides, reusable `ag-*` classes, log rendering polish.
- Modify `apps/react/src/components/Layout/index.tsx`: Nexus shell, sidebar, topbar, current page title, role badge, content canvas.
- Modify `apps/react/src/pages/Login/index.tsx`: secure login visual treatment while keeping login behavior.
- Modify `apps/react/src/pages/Dashboard/index.tsx`: add page/header/panel classes and refine card/table layout without changing data flow.
- Modify `apps/react/src/pages/Logs/index.tsx`: add page/header/filter/table/expand classes without changing parsing or fetch logic.
- Optionally modify page wrappers in:
  - `apps/react/src/pages/ApiKeys/index.tsx`
  - `apps/react/src/pages/Chat/index.tsx`
  - `apps/react/src/pages/Channels/index.tsx`
  - `apps/react/src/pages/Groups/index.tsx`
  - `apps/react/src/pages/Prices/index.tsx`
  - `apps/react/src/pages/Vouchers/index.tsx`
  - `apps/react/src/pages/Users/index.tsx`

## Task 1: Establish Global Design System

**Files:**
- Modify: `apps/react/src/index.css`
- Inspect: `docs/web_designs/stitch/dashboard/code.html`
- Inspect: `docs/web_designs/stitch/request_logs/code.html`
- Inspect: `docs/web_designs/stitch/any_gateway/code.html`

- [ ] **Step 1: Inspect current CSS and Stitch color usage**

Run:

```bash
sed -n '1,260p' apps/react/src/index.css
sed -n '1,140p' docs/web_designs/stitch/dashboard/code.html
```

Expected: identify the existing Vite default styles and Stitch colors such as `#f8f9fb`, `#003d9b`, `#0052cc`, `#e7e8ea`, `#737685`.

- [ ] **Step 2: Replace Vite defaults with Any Gateway design tokens**

In `apps/react/src/index.css`, define root variables:

```css
:root {
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  color: var(--ag-on-surface);
  background: var(--ag-surface);
  font-synthesis: none;
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;

  --ag-surface: #f8f9fb;
  --ag-surface-lowest: #ffffff;
  --ag-surface-low: #f3f4f6;
  --ag-surface-container: #edeef0;
  --ag-surface-high: #e7e8ea;
  --ag-on-surface: #191c1e;
  --ag-on-surface-variant: #434654;
  --ag-outline: #737685;
  --ag-outline-variant: #c3c6d6;
  --ag-primary: #003d9b;
  --ag-primary-container: #0052cc;
  --ag-primary-soft: #dae2ff;
  --ag-secondary-soft: #bfd1ff;
  --ag-tertiary: #7b2600;
  --ag-tertiary-soft: #ffdbcf;
  --ag-error: #ba1a1a;
  --ag-error-soft: #ffdad6;
  --ag-radius: 8px;
  --ag-radius-lg: 12px;
  --ag-shadow-soft: 0 18px 44px rgba(25, 28, 30, 0.08);
}
```

Remove the default dark `color-scheme` and default button styling that conflicts with Arco.

- [ ] **Step 3: Add reusable layout and panel classes**

Add classes for:

```css
.ag-page
.ag-page-header
.ag-page-eyebrow
.ag-page-title
.ag-page-description
.ag-filter-panel
.ag-data-panel
.ag-stat-grid
.ag-stat-card
.ag-stat-label
.ag-stat-value
.ag-role-badge
.ag-icon-button
```

Expected behavior: classes provide spacing, borders, backgrounds, shadows, and typography only. Do not hide or reposition Arco internals in a way that changes behavior.

- [ ] **Step 4: Add scoped Arco component visual overrides**

Add overrides under either `body` or `.ag-shell` for:

```css
.arco-card
.arco-table-container
.arco-table-th
.arco-table-td
.arco-btn-primary
.arco-input-inner-wrapper
.arco-select-view
.arco-picker
.arco-tag
.arco-pagination-item
.arco-modal
```

Expected: Arco controls look closer to the Stitch UI but remain fully clickable and accessible.

- [ ] **Step 5: Preserve Markdown rendering styles**

Keep existing `.md-p` behavior and add light styling for `pre`, `code`, and log expansion classes. Do not change `apps/react/src/pages/Logs/logParsing.ts`.

- [ ] **Step 6: Build after CSS-only change**

Run:

```bash
cd apps/react
npm run build
```

Expected: build succeeds.

- [ ] **Step 7: Commit design system**

```bash
git add apps/react/src/index.css
git commit -m "style: add Any Gateway design system"
```

## Task 2: Update Shell Layout

**Files:**
- Modify: `apps/react/src/components/Layout/index.tsx`
- Inspect: `apps/react/src/router/index.tsx`

- [ ] **Step 1: Map page titles**

Add a local title map near the menu definitions:

```ts
const pageTitles: Record<string, string> = {
  dashboard: 'Dashboard',
  apikeys: 'API Keys',
  chat: 'Conversations',
  logs: 'Request Logs',
  groups: 'Groups',
  channels: 'Channels',
  prices: 'Pricing',
  vouchers: 'Vouchers',
  users: 'User Management',
}
```

Expected: current route key maps to a topbar subtitle.

- [ ] **Step 2: Replace inline shell styling with `ag-*` classes**

Use:

```tsx
<ArcoLayout className="ag-shell">
<Sider className="ag-sidebar" ...>
<Header className="ag-topbar">
<Content className="ag-content">
```

Keep existing `collapsed`, `navigate`, `logout`, `isAdmin`, and `isSuperAdmin` logic.

- [ ] **Step 3: Update brand block**

Use existing `/icon.png` or `/icon_big.png` with text:

```tsx
<div className="ag-brand">
  <div className="ag-brand-mark"><img src="/icon.png" alt="" /></div>
  {!collapsed && (
    <div>
      <div className="ag-brand-title">Gateway</div>
      <div className="ag-brand-subtitle">AI Infrastructure</div>
    </div>
  )}
</div>
```

Expected: collapsed state stays readable.

- [ ] **Step 4: Update topbar content**

Add left system title and page title. Keep right username, role, and logout action. Use an icon-only logout button from existing Arco icons.

- [ ] **Step 5: Verify typecheck/build**

Run:

```bash
cd apps/react
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit shell**

```bash
git add apps/react/src/components/Layout/index.tsx apps/react/src/index.css
git commit -m "style: update app shell"
```

## Task 3: Restyle Login Page

**Files:**
- Modify: `apps/react/src/pages/Login/index.tsx`
- Inspect: `docs/web_designs/stitch/any_gateway/code.html`

- [ ] **Step 1: Preserve login behavior before editing**

Confirm `handleSubmit`, `useEffect` redirect, `setAuth`, and `Message.error` remain unchanged.

- [ ] **Step 2: Replace card layout with login classes**

Use class structure:

```tsx
<div className="ag-login-page">
  <div className="ag-login-pattern" />
  <main className="ag-login-shell">
    <section className="ag-login-brand">...</section>
    <Card className="ag-login-card">...</Card>
  </main>
</div>
```

Expected: the form still uses Arco `Form`, `Input`, `Input.Password`, and `Button`.

- [ ] **Step 3: Add field icons without changing fields**

Use Arco icons inside the input prefix where possible:

```tsx
<Input prefix={<IconUser />} ... />
<Input.Password prefix={<IconLock />} ... />
```

Expected: field names remain `username` and `password`.

- [ ] **Step 4: Add supporting CSS**

In `index.css`, add:

```css
.ag-login-page
.ag-login-page::before
.ag-login-pattern
.ag-login-shell
.ag-login-brand
.ag-login-logo
.ag-login-card
```

Use existing `/background.png` as a subtle image layer.

- [ ] **Step 5: Build**

Run:

```bash
cd apps/react
npm run build
```

Expected: build succeeds.

- [ ] **Step 6: Commit login**

```bash
git add apps/react/src/pages/Login/index.tsx apps/react/src/index.css
git commit -m "style: refresh login page"
```

## Task 4: Restyle Dashboard Page

**Files:**
- Modify: `apps/react/src/pages/Dashboard/index.tsx`
- Modify: `apps/react/src/index.css`
- Inspect: `docs/web_designs/stitch/dashboard/code.html`

- [ ] **Step 1: Identify JSX return blocks**

Locate:

- page title and refresh button
- filter panel
- statistic cards
- status/voucher/rate-limit sections
- usage table
- model table

Expected: only render structure and class names change.

- [ ] **Step 2: Replace page root and header**

Wrap return content with:

```tsx
<div className="ag-page ag-dashboard-page">
  <div className="ag-page-header">...</div>
  ...
</div>
```

Use `System Overview` eyebrow and `Dashboard` title.

- [ ] **Step 3: Convert filter block to `ag-filter-panel`**

Keep `RangePicker`, admin `Select`, `查询`, and `下载 CSV`. Preserve `handleSearch` and `handleExport`.

- [ ] **Step 4: Convert Statistic cards to `ag-stat-card`**

Keep all existing values:

- `overview?.request_count`
- `overview?.total_cost_usd`
- `overview?.actual_cost_usd`
- `overview?.input_tokens + output/cache fields` as currently implemented

Do not alter calculations.

- [ ] **Step 5: Convert table wrappers to `ag-data-panel`**

Usage and model tables remain Arco `Table` with the same columns, sorters, pagination, and handlers.

- [ ] **Step 6: Style voucher/status/rate-limit panels**

Only adjust classes and surrounding layout. Keep `handleRedeem`, `voucherError`, `myStatus`, and `Progress` behavior.

- [ ] **Step 7: Build**

Run:

```bash
cd apps/react
npm run build
```

Expected: build succeeds.

- [ ] **Step 8: Commit dashboard**

```bash
git add apps/react/src/pages/Dashboard/index.tsx apps/react/src/index.css
git commit -m "style: refresh dashboard page"
```

## Task 5: Restyle Logs Page

**Files:**
- Modify: `apps/react/src/pages/Logs/index.tsx`
- Modify: `apps/react/src/index.css`
- Do not modify: `apps/react/src/pages/Logs/logParsing.ts`

- [ ] **Step 1: Confirm no parsing logic changes**

Before editing, note that these imports and functions must remain semantically unchanged:

- `formatOpenAIToolCalls`
- `parseMessages`
- `parseRequestMaxTokens`
- `parseResponseParts`
- `RenderBlock`
- `RenderMessage`
- `RenderReasoning`
- `RenderWarnings`

- [ ] **Step 2: Replace page root and header**

Wrap the returned page with:

```tsx
<div className="ag-page ag-logs-page">
  <div className="ag-page-header">...</div>
  ...
</div>
```

Use title `Request Logs` and a short audit/traffic description.

- [ ] **Step 3: Convert filters to `ag-filter-panel`**

Keep every existing filter field and `handleSearch` behavior.

- [ ] **Step 4: Convert table wrapper to `ag-data-panel`**

Keep `columns`, `fetchLogs`, pagination, `handleExpand`, and lazy loading behavior.

- [ ] **Step 5: Polish expanded log rendering classes**

Change only class names and wrapper styles for:

- request body
- response body
- parsed messages
- reasoning
- warnings
- tool use/result blocks

Expected: rendering looks like a structured audit panel, but message parsing output is identical.

- [ ] **Step 6: Run existing log parsing test**

Run:

```bash
cd apps/react
node src/pages/Logs/logParsing.test.mjs
```

Expected: test script exits successfully.

- [ ] **Step 7: Build**

Run:

```bash
cd apps/react
npm run build
```

Expected: build succeeds.

- [ ] **Step 8: Commit logs**

```bash
git add apps/react/src/pages/Logs/index.tsx apps/react/src/index.css
git commit -m "style: refresh request logs"
```

## Task 6: Apply Minimal Global Wrappers to Remaining Pages

**Files:**
- Inspect and optionally modify:
  - `apps/react/src/pages/ApiKeys/index.tsx`
  - `apps/react/src/pages/Chat/index.tsx`
  - `apps/react/src/pages/Channels/index.tsx`
  - `apps/react/src/pages/Groups/index.tsx`
  - `apps/react/src/pages/Prices/index.tsx`
  - `apps/react/src/pages/Vouchers/index.tsx`
  - `apps/react/src/pages/Users/index.tsx`

- [ ] **Step 1: Inspect page roots**

Run:

```bash
cd apps/react
for f in src/pages/{ApiKeys,Chat,Channels,Groups,Prices,Vouchers,Users}/index.tsx; do sed -n '1,220p' "$f"; done
```

Expected: identify root wrappers, cards, tables, and inline white panels.

- [ ] **Step 2: Add page wrapper classes only where useful**

For pages with plain `<div>` roots, use:

```tsx
<div className="ag-page">
```

For obvious card/table sections, use `ag-data-panel` only if it does not require restructuring.

- [ ] **Step 3: Remove only conflicting inline visuals**

Allowed edits:

- remove hardcoded `background: '#fff'` if replaced by `ag-data-panel`
- remove hardcoded border radius if replaced by global class
- keep all dimensions needed by tables/forms

Disallowed edits:

- changing fields
- changing API calls
- changing handlers
- changing pagination/sorting/filtering logic

- [ ] **Step 4: Build**

Run:

```bash
cd apps/react
npm run build
```

Expected: build succeeds.

- [ ] **Step 5: Commit global page wrappers**

```bash
git add apps/react/src/pages
git commit -m "style: align remaining pages"
```

## Task 7: Final Verification and Browser QA

**Files:**
- Verify only unless fixes are needed.

- [ ] **Step 1: Run lint**

Run:

```bash
cd apps/react
npm run lint
```

Expected: lint succeeds. If lint reveals pre-existing unrelated issues, document them and only fix issues introduced by this work.

- [ ] **Step 2: Run build**

Run:

```bash
cd apps/react
npm run build
```

Expected: TypeScript and Vite build succeed.

- [ ] **Step 3: Start dev server**

Run:

```bash
cd apps/react
npm run dev
```

Expected: Vite serves the app, usually at `http://localhost:5173`.

- [ ] **Step 4: Browser-check priority pages**

Use the in-app browser or browser-use plugin to inspect:

- `/login`
- `/dashboard`
- `/logs`
- `/apikeys`
- `/channels`

Expected:

- no blank screen
- no major text overlap
- sidebar and topbar are usable
- tables remain scrollable
- forms remain clickable
- visual style matches the Stitch/Nexus direction

- [ ] **Step 5: Fix verification issues**

If visual or build issues appear, make the smallest scoped fix and rerun the failed verification command.

- [ ] **Step 6: Final commit**

If fixes were made after Task 6:

```bash
git add apps/react
git commit -m "fix: polish Stitch visual QA"
```

## Completion Notes

At completion, report:

- commits created
- commands run and results
- browser pages checked
- any residual risk or skipped verification
