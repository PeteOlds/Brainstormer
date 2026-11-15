---
target: app/templates/home.html
total_score: 20
max_score: 40
na_heuristics: 
p0_count: 2
p1_count: 2
timestamp: 2026-10-17T23-06-08Z
slug: app-templates-home-html
---
# Assessment Report — Brainstormer UI for Casual, Non-Technical Users

**Scope:** `app/templates/home.html`, `app/templates/ideas/dashboard.html`, `app/templates/admin/ai_configs.html`, `app/templates/base.html`, `app/templates/partials/_navbar.html`
**Method:** dual-agent (A: assessment_A · B: assessment_B)
**Context:** idea pipeline for technically illiterate / casual users; V2 lifecycle SPARK→SCOPE→MAP→SHIP→SCALE→DROP/FREEZE/ARCHIVE; design tokens Inter/system-ui, primary blue, slate surfaces, 44px min touch targets; version 0.66.0; ~466 tests pass.

---

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Silent status changes; no confirmation toasts; build status hidden in modal |
| 2 | Match System / Real World | 1 | All-caps enum stages (`SPARK`, `SCOPE`…); unexplained jargon (PRD, PAT, instance, repo, branch, cutoff_behaviour); AI Settings = infra config in main nav |
| 3 | User Control and Freedom | 3 | Close buttons everywhere, but bare `confirm()`/`alert()`/`prompt()` with no undo |
| 4 | Consistency and Standards | 3 | Strong button/modal consistency; AI Settings inputs `min-h-[36px]` violate 44px standard; vote buttons `p-1.5` below standard |
| 5 | Error Prevention | 2 | Post-submit validation only; generic `alert()`; no protection against double-submit; `prompt()` for release name has no validation |
| 6 | Recognition Rather Than Recall | 3 | Filter options visible; status chips show state; but PAT never shown again, filter state not legible at a glance |
| 7 | Flexibility and Efficiency | 1 | No keyboard shortcuts, no bulk actions, Previous/Next pagination only, no page numbers |
| 8 | Aesthetic and Minimalist Design | 3 | Clean palette and whitespace; but 6 filters + table + pagination on dashboard, ~40 fields on AI Settings, 8+ tabs in detail modal |
| 9 | Error Recovery | 2 | Generic error strings ("Failed to load AI settings."), no suggested fix, `alert()` steals context |
| 10 | Help and Documentation | 0 | No onboarding, no tooltips for stages, no docs link, no empty-state guidance beyond "explore the ideas list" |
| **Total** | | **20** | **/40 — Acceptable (bottom of band)** |

---

## Design Specificity Verdict

**Category-interchangeable, not authored for Brainstormer.**

The UI reads like a generic admin dashboard shell (table + filters + pills + modals + bulk-action bar) with "Brainstormer" swapped in as the product name. Little ties the visual language to the product's purpose.

**Overall coherence:** coherent at component level, incoherent at product level. Every content block uses the identical card recipe: `border border-slate-200 dark:border-slate-700 rounded-lg p-4 bg-white dark:bg-slate-800` with `h2 text-lg font-semibold` + `p text-xs text-slate-500` subtitle. Home page tiles ("My ideas", "Most popular", "Most discussed", "Ideas not voted on", "Messages") are visually indistinguishable from each other and from dashboard cards.

**Structural sameness:** the dashboard is a straight admin-style data table — Ref / Timestamp / Prompt / Summary / Status / Comments / Votes / Actions. It could be a bug tracker, help-desk queue, or CMS post list with zero changes. The lifecycle — the product's core concept — is nowhere visualized; stages appear only as all-caps enum text (`SPARK`, `SCOPE`, …) in chips and as eight undifferentiated `<option>`s in a `<select>`.

**Missed opportunities for product character:**
- No pipeline/flow visualization of idea progression through the 8 stages.
- No "idea card" metaphor — ideas are table rows.
- No celebration or progress signalling (no "3 of 5 stages complete" cues).
- Logo (`_navbar.html` line 6-7, `base.html`) is an abstract geometric path with no idea/lightbulb/canvas association.
- Copy is functional/generic: "Ideas Dashboard", "Review, vote, and analyze generated business ideas", "AI Business Idea Generator".
- Empty states are generic: "No ideas found", "No votes yet", "No comments yet — start the discussion", with a stock outline icon.

**Bottom line:** a first-time casual user cannot tell from the UI alone what Brainstormer is for beyond "a list of things." Product character is buried under generic admin chrome.

---

## Overall Impression

The UI is competent at the component level (44px touch targets, dark mode, server-side pagination, per-stage color coding) but fails its primary audience — technically illiterate / casual users — at the product level. The system speaks in implementation concepts (enums, PAT, instance, repo, branch, cutoff_behaviour) rather than real-world concepts. A new user lands on an empty dashboard with no clear first step, encounters a wall of jargon, and faces dense information with no progressive disclosure. The single biggest opportunity: redesign around the lifecycle as the product's organizing metaphor, with plain language throughout and a guided first-time path.

---

## What's Working

1. **Accessible foundation** — 44px min touch targets on primary controls, consistent `min-h-[44px]` buttons, working dark mode, `sr-only` labels on all filter selects/inputs. This is the one area the UI genuinely serves casual and mobile users.

2. **Honest list state** — server-side pagination with `total`/`pages` means the UI never shows a stale or sliced list; the header shows "X matching / Y total ideas" so users always know the real count.

3. **Clear per-stage color coding** — status chips use distinct hues per lifecycle stage (slate SPARK, blue SCOPE, violet MAP, indigo SHIP, emerald SCALE, red DROP, amber FREEZE, gray ARCHIVE via `statusClass`/`getStatusClass`), giving fast recognition of where an idea sits.

---

## Priority Issues (P0 → P3)

### P0 — Jargon leaks directly to the user (Match with real world — score 1/4)

**What:** lifecycle stages render as all-caps enum text (`SPARK`, `SCOPE`, `MAP`, `SHIP`, `SCALE`, `DROP`, `FREEZE`, `ARCHIVE`) in status chips (home.html line 21; dashboard line 133). Infrastructure terms appear unexplained: PRD, PAT, instance, repo, branch, build target, embedding model, cutoff_behaviour, allowlist, sandbox/repo workspace. AI Settings is pure ops configuration in the main nav.

**Why it matters:** for a technically illiterate/casual user this is a wall of meaningless vocabulary. They cannot answer "what does SPARK mean?" or "what's a PAT?" from the UI. This is the single biggest barrier to adoption.

**Fix:** replace enum display with plain-language stage labels everywhere (e.g. "Spark", "Scope", "Map", "Ship", "Scale", "Dropped", "Frozen", "Archived"); add one-line plain descriptions of each stage in the UI; move AI Settings out of the casual user's path (admin-only or behind an explicit "Advanced" mode); explain PAT/instance in plain terms where they must appear.

**Suggested command:** `$impeccable clarify` — rewrite all user-facing stage/infrastructure copy into plain language, with a stage glossary in the UI.

---

### P0 — Low-contrast gray text on tinted backgrounds (Visibility of System Status — score 2/4)

**What:** detector found 24 `gray-on-color` warnings across home.html (6), dashboard.html (18), ai_configs.html (4). Examples: `text-slate-500` on `bg-indigo-100` (home.html line 128), `text-slate-400/500/700` on `bg-indigo-50` (dashboard lines 378-391), `text-slate-600/300` on `bg-green-100` (ai_configs lines 39, 144). These are status-badge and message-tint pairs where light gray text sits on light tinted backgrounds.

**Why it matters:** washed-out contrast is hard for casual users and anyone with low vision to read. Status badges are the primary way users understand where an idea sits in the lifecycle — if they can't read them, the product's core signal is lost.

**Fix:** darken the light-gray text on tinted backgrounds (or switch to near-white text on colored backgrounds, darker shades of the background color per detector guidance). Consolidate status colors into real Tailwind tokens rather than hand-picked strings.

**Suggested command:** `$impeccable layout` — audit contrast and consolidate status colors into tokens.

---

### P1 — No onboarding or first-time path (Help & Documentation — score 0/4)

**What:** a new user lands on home and sees empty tiles ("Nothing yet — explore the ideas list", "No votes yet", "No messages") plus an "All ideas" link. The dashboard's most important action — "Create Idea" — is a small header button gated behind `canCreateIdeas`. No "create your first idea" cue, no tour, no empty-state illustration.

**Why it matters:** casual users need a single obvious first step. Without it they bounce. The UI assumes the user already knows what to do.

**Fix:** on an empty home/dashboard, show a primary "Create your first idea" call-to-action with a one-sentence explanation of what an idea is and what happens next (it starts at Spark).

**Suggested command:** `$impeccable onboard` — design an empty-state onboarding pattern with a clear first action.

---

### P1 — Information overload (Aesthetic & Minimalist — score 3/4; Cognitive Load — 8 fails)

**What:** the dashboard shows six filter controls, a full table, pagination, and a bulk bar at once. The detail modal stacks eight tabs, releases, per-release AI settings (provider/model/temperature/top-p/max-tokens/skills/guidelines), build run info, and discussion. AI Settings presents ~40 infra fields on one page. Filter row presents 6 controls at once; status select has 8 options; release row has ~8 controls.

**Why it matters:** far more than 4 items per decision point; casual users freeze. The Scale tab is especially dense — release cards carry ~8 controls each. Cognitive load assessment: 8 items failed (single focus, chunking, visual hierarchy, one thing at a time, minimal choices, working memory all fail).

**Fix:** progressive disclosure — collapse filters behind a "Filter" button on small screens; split the detail modal tabs into focused views; hide per-release AI settings behind an "Advanced" toggle; move AI Settings to admin-only.

**Suggested command:** `$impeccable distill` — reduce each screen to one primary decision and no more than 4 visible choices at a time.

---

### P2 — Inconsistent touch targets (Consistency and Standards — score 3/4)

**What:** AI Settings inputs use `min-h-[36px]` (ai_configs.html lines 51, 158-194); release AI settings use `px-2 py-1.5 text-xs` (lines 640-676); detail-modal vote buttons use `p-1.5` with no minimum size (lines 431, 435); sidebar links use `py-2.5` (~40px). The project standard is 44px min.

**Why it matters:** directly violates the stated design standard and makes the app harder to use one-handed or with limited motor control — exactly the users this product targets.

**Fix:** apply `min-h-[44px]` and ≥44px touch targets to every interactive element, including AI Settings and the release micro-controls.

**Suggested command:** `$impeccable layout` — audit and normalize all touch targets to 44px.

---

### P2 — No design system tokens; ad-hoc color strings (Aesthetic & Minimalist)

**What:** no `tailwind.config.js` — theme lives in an inline `<script>` in base.html. Status colors are duplicated as magic strings in `statusClass()` (home.html line 202) and hand-picked elsewhere. Detector flags this indirectly via contrast warnings (root cause: no token system).

**Why it matters:** without tokens, every new screen re-invents color, spacing, and sizing — leading to the inconsistency and overload problems above.

**Fix:** extract Tailwind config to a real file; define status/severity/role tokens; replace ad-hoc strings with token classes.

**Suggested command:** `$impeccable extract` — pull reusable tokens and components into a design system.

---

## Persona Red Flags

### Jordan — Confused First-Timer (reads all instructions, hesitates before unfamiliar clicks, misunderstands jargon)

- Lands on home: "Ideas in each phase" shows bars with raw stage names — Jordan doesn't know what a phase is or why clicking matters.
- Sees status chips `SPARK`/`SCOPE`/… with no definition; has to guess what moving an idea between them does.
- "All ideas" leads to a dashboard with six filters and an admin-only bulk bar — Jordan can't tell which controls apply to them.
- Wants to create an idea: the "Create Idea" button is small, gated, and not visually primary; no empty-state tells Jordan this is the first step.
- Reference codes (`IDEA-9603`) look important but are never explained.
- **Red flag:** Jordan will likely abandon, believing the app is "for other people."

### Casey — Distracted Mobile User (one-handed thumb, interrupted mid-flow, limited attention)

- Desktop table is replaced by stacked mobile cards (good), but the six-filter row still crowds the top; opening a filter requires precise taps on small selects.
- Modals (`max-w-md` run dialog, `max-w-2xl` detail modal) cover the screen; click-outside dismiss means an accidental tap loses an in-progress run setup.
- Auto-refresh every 30s can replace the list while Casey is reading — loss of place, no "you were here" marker.
- Two-stage interactions (open 3-dot menu → select status → confirm) require sustained attention; an interruption forces restart.
- **Red flag:** Casey will abandon mid-flow and may not return.

### Sam — Accessibility-Dependent (keyboard-only, screen reader)

- `alert()`/`confirm()`/`prompt()` are inaccessible interruptions that screen readers announce inconsistently and cannot be dismissed gracefully by keyboard.
- Status-chip color is a strong state signal, but raw enum text may be spelled out letter-by-letter ("S-P-A-R-K") by screen readers.
- `sr-only` labels on filters are good, but modals show no visible focus trap; keyboard tab order through the dense detail modal is long and unclear.
- `min-h-[36px]` AI Settings inputs fail the 44px target Sam depends on.
- **Red flag:** Sam cannot complete high-stakes actions (Drop, GitHub push) confidently because browser dialogs give no accessible confirmation flow.

---

## Minor Observations

- Home "Messages" tile mixes an inbox (latest-first list) and a compose form in one card — two purposes, no visual separation.
- Home phase filter opens an overlay modal that duplicates the phase list already shown above it.
- Date format "16-Oct-26" (dashboard `releaseDate`) is locale-ambiguous.
- Model size badges use emoji (`🚀` <3GB, `🐇` 3-7GB, `🐢` >7GB) — cute but unexplained; casual users won't know what they mean.
- `style="display: none;"` overrides in _navbar.html duplicate the JS auth UI — a fragile double-render pattern.
- "Builds go straight into the app's own repo… open the Build tab, press Stop, then Start" (dashboard line 622) is an instruction buried in prose — high friction for a casual user.
- Cost column renders "5.00 $" (`cost_cents / 100 + ' $'`) — awkward currency formatting.
- Auto-refresh cannot be disabled; no user control.
- No "mark all messages read" despite per-message "Mark read" buttons.

---

## Questions to Consider

**1. Should casual users see AI Settings / instance infrastructure at all?** The AI Settings page (~40 infra fields: API keys, budgets in cents, cutoff behaviour, proxy routing) sits in the main nav but is meaningless to a casual user. 
- **Option A:** Move AI Settings behind an explicit "Admin / Advanced" mode so the main product stays focused on ideas (recommended)
- **Option B:** Keep AI Settings but hide it behind a user role toggle with clear "Advanced settings" labeling
- **Option C:** Leave as-is and accept that casual users will ignore it

**2. Could the lifecycle be presented as a visual pipeline?** Currently stages are all-caps enum text in table chips. 
- **Option A:** Replace table with a pipeline/kanban view where idea cards move through Spark → Scope → Map → Ship → Scale (recommended)
- **Option B:** Keep the table but replace enum text with plain-language labels + one-line stage descriptions
- **Option C:** Add a small pipeline indicator above the table without changing the table itself

**3. Should the first-time experience be guided?** Currently a new user sees empty tiles with no path forward.
- **Option A:** Guided "create your first idea" flow on first empty visit (recommended)
- **Option B:** Empty-state card with a prominent "Create your first idea" button and one-sentence explanation
- **Option C:** Leave as-is; users who can't figure it out aren't the target audience

**4. How much scope should we take on?** There are 6 priority issues (2 P0, 2 P1, 2 P2).
- **Option A:** Address P0 issues first (jargon + contrast) — highest impact for casual users
- **Option B:** Address all P0 + P1 issues (jargon, contrast, onboarding, overload)
- **Option C:** Address everything including touch targets and design system tokens

---
