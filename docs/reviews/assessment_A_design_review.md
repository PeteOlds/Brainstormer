# Assessment A — Design Review: Brainstormer UI for Casual, Non-Technical Users (v0.70.1, post-fix)

**Scope:** `app/templates/home.html`, `app/templates/ideas/dashboard.html`, `app/templates/admin/ai_configs.html`, `app/templates/base.html`, `app/templates/partials/_navbar.html`
**Context:** idea pipeline for technically illiterate / casual users; V2 lifecycle SPARK → SCOPE → MAP → SHIP → SCALE → DROP/FREEZE/ARCHIVE (plain-language labels); Inter/system-ui, primary blue, slate surfaces, 44px min touch targets.

Fixes verified as applied: home hero CTA ("Create your first idea"), plain-language stage labels everywhere (`stageLabels`/`stageLabel`), dashboard card-first layout (`article` cards), run-dialog simple mode + admin-gated advanced, auto-refresh pauses on interaction + "✓ Just updated," alert/confirm/prompt → in-app modals, Prompt/Model filters behind "Show more filters," status-chip consistency via `getStatusClass`.

AI Settings plain-language labels: only partially — labels are friendlier ("Monthly spending cap" vs `budget_cents`) but the page is still pure infrastructure.

---

## 1. DESIGN SPECIFICITY VERDICT

**Verdict: still category-interchangeable, now with a product-facing front door.**

The home page finally reads like Brainstormer: hero CTA "Create your first idea" (`home.html` line 23), plain-language explanation ("An idea is a suggestion for something to build — an app, a feature, a tool, anything. It starts as a 'Spark' and moves through stages as it takes shape." lines 19-20). Good.

Beyond home, the product character thins out. The dashboard is a card list that could still be any review queue; the lifecycle — the product's core concept — is not visualized, only shown as plain-label chips with no definition on the dashboard. Copy is split: home is plain-language, but the dashboard leaks infra concepts ("PRD", "Design", "Built" chips at lines 538-541; "Recreate" buttons at lines 680/752; reference codes `IDEA-9603` prominent and unexplained) and `ai_configs.html` is an infrastructure wall ("API key," "Custom endpoint," "Workspace mode: sandbox/repo," cutoff_behaviour refuse/queue/degrade).

**Bottom line:** a first-time casual user can now tell what to do on home, but once inside the app they're met with admin-density and unexplained concepts. Product character is not carried through.

---

## 2. NIELSEN'S 10 HEURISTICS (scored 0-4)

### 1. Visibility of System Status — 3/4
Positives: "✓ Just updated" emerald indicator (dashboard line 14), "Updated `<time>` · auto-refreshes" (line 15), refresh spinner + "Refreshing…" (lines 21-24), inline `saveMsg`/`saveErr` (ai_configs lines 31-32), "You upvoted / You downvoted" (dashboard line 148).
Negatives: no page-initial loading state; status changes reload with only an inline message, no toast; auto-refresh still fires every 30s (now pauses on interaction — improvement); inline errors vanish on next load.

### 2. Match Between System and Real World — 2/4 (improved, still weak)
Positives: stage labels now plain everywhere — `stageLabels` dashboard lines 3634-3643 (Spark/Scope/Map/Ship/Scale/Dropped/Frozen/Archived) and `home.html` lines 97-106. Home copy explains Spark as the start. Run dialog: "Run with recommended settings. The idea's own stage and AI defaults will be used." (line 929).
Negatives: filter `<option>` values still raw enums (`value="SPARK"` etc., lines 36-43) though labels are plain; action chips say "PRD"/"Design"/"Built" (lines 538-541); reference codes `IDEA-9603` displayed in `font-mono` but never explained; `ai_configs.html` still infra: "API key (hidden after saving — blank keeps current)" (line 56), "Allowed models (one per line or comma-separated; empty = any model)" (line 60), "Custom endpoint" (line 64), "Monthly spending cap" + `budget_cents` (line 69), cutoff_behaviour refuse/queue/degrade (lines 75-77), "embedding model"/"degrade_model" (lines 82-85), Workspace sandbox/repo (lines 88-93), GitHub "personal access token with repo scope" (line 114), per-stage provider/model/temperature/top_p/max tokens (lines 158-183).

### 3. User Control and Freedom — 3/4
Positives: every modal has Close + click-outside dismissal; Cancel buttons everywhere; status re-changeable; discard confirmed via in-app modal; browser `alert()`/`confirm()`/`prompt()` removed. Negatives: no undo after Drop/Archive; logout immediate, no confirmation; "Push to GitHub" is effectively one-way (further updates need a new release — line 511 title); Dropped/Archived ideas hidden by default filter with no visible restore path on casual views.

### 4. Consistency and Standards — 3/4
Positives: main pages consistent — `min-h-[44px]` buttons, same border/rounded/slate tokens, identical modal header/close/footer, working dark mode, status chips consistent via `getStatusClass` (dashboard line 3656).
Negatives: 44px standard still violated in the detail modal and AI Settings — detail-modal vote buttons `p-2 rounded-lg` with no min height (lines 373, 379); comment Reply/Edit/Hide/Delete `min-h-[32px]` (lines 473-477); release Mark done/Push/Delete `min-h-[32px]` (lines 509-512); release Move buttons `min-h-[36px]` (lines 557, 564); "Recreate" `min-h-[36px]` (lines 680, 752); AI Settings Edit provider/stage `min-h-[36px]` (lines 51, 147); Delete target `min-h-[36px]` (line 210). Navbar still runs two parallel auth UIs with inline `style="display: none;"` overrides (lines 46-54).

### 5. Error Prevention — 3/4
Positives: required-field asterisks, disabled-during-loading, in-app confirm modals for destructive acts, inline validation ("Budget must be a non-negative integer." ai_configs line 486), Apply disabled until status chosen.
Negatives: validation still mostly after-submit (`createIdeaError` red box); network failures generic; no double-submit protection beyond loading flag; PAT can never be verified after save ("saved ✓ — leave blank to keep it" line 125).

### 6. Recognition Rather Than Recall — 3/4
Positives: all filter options visible in dropdowns; status chips show current state; action chips show available docs; "You upvoted" indicator; "✓ Just updated" indicator. Negatives: model IDs raw strings with no descriptions; default filter "Active ideas only" hides DROP/ARCHIVE but the user must recall this; no active-filter badges (six+ controls, no at-a-glance active state); PAT never shown again; no keyboard shortcuts.

### 7. Flexibility and Efficiency — 1/4
No keyboard shortcuts; pagination Previous/Next only (no page numbers, no jump-to-page); search only on dashboard; repeated run-dialog entry partially addressed via "Recreate" prefill from last run, but no persistent preferences; no "recent ideas" quick access; no favorites beyond voting.

### 8. Aesthetic and Minimalist Design — 3/4
Positives: clean slate/indigo palette, whitespace, dark mode, consistent component scale. Negatives: high information density — dashboard shows 3 visible filters + "Show more filters" toggle + cards + bulk bar + pagination at once; detail modal stacks tabs + releases + per-release AI settings + build controls + discussion; AI Settings presents ~40 infra fields on one page; empty states are bare text ("No ideas found" dashboard line 193); no product personality (abstract geometric logo, generic dashboard subtitle "Review, vote, and analyze generated business ideas" line 10).

### 9. Help Users Recognize, Diagnose, and Recover from Errors — 3/4
Positives: errors rendered inline (`saveErr`, `createIdeaError`); required fields marked; confirm modals explain consequence ("Remove GitHub settings? Finished releases can no longer be pushed." ai_configs line 416). Negatives: messages still generic ("Failed to load AI settings.", "Failed to save.", "Failed to start.") with no suggested fix; no inline pre-submit validation; no distinction "network down" vs "typed wrong."

### 10. Help and Documentation — 1/4
Positives: home page explains what an idea is and the Spark start (lines 19-20); run dialog explains defaults (line 929). Negatives: still no onboarding tour, no tooltips explaining stage meanings on the dashboard (`stageDescriptions` exists only on `home.html`, not the dashboard), no docs link in the UI, no getting-started cue beyond the hero CTA, no explanation of "instance" scoping despite the scope chip (`_navbar.html` line 52 title: "Login scope — data is filtered to this workspace. Log in via /login?instance=N").

---

## 3. COGNITIVE LOAD ASSESSMENT (8 items)

| Item | Assessment |
|---|---|
| Single focus | Partial. Home has a clear primary CTA ("Create your first idea") but still shows 4 idea tiles + unread banner. Dashboard: filters + cards + bulk bar + pagination compete; nothing says "start here." |
| Chunking (≤4 per group) | Fail. Filter row: 3 visible + 2 hidden controls; status select has 8 options; each idea card packs ~12 elements (ref, status chip, prompt chip, title, summary, read link, action chips, comments, votes, up/down buttons, user-vote chip, admin dropdown); release row ~8 controls; AI provider edit form ~12 fields. |
| Grouping | Pass. Related items in bordered cards; but the Scale tab dumps child ideas, releases, per-release AI settings, and build controls into one tab separated only by borders. |
| Visual hierarchy | Partial. Home hero CTA is primary; dashboard "Create Idea" is a header button, not dominant. All other cards/buttons carry equal weight. |
| One thing at a time | Partial. Run-dialog simple mode is one thing ("Run with recommended settings") — good. But advanced mode dumps engine/model/target repo/skills/guidelines/new-repo form on one screen (lines 938-1014); detail modal does everything at once. |
| Minimal choices (≤4 at decision point) | Fail. 8 lifecycle statuses, 5 AI providers, model pickers, 8 filter combos, admin bulk actions. |
| Working memory | Fail. User must remember stage meanings (no dashboard glossary); filter settings persist silently; PAT "saved ✓" cannot be verified; moving home→dashboard loses phase context. |
| Progressive disclosure | Partial. Modals hide secondary complexity; simple run mode good; but admin UI leaks into all views, AI Settings shows every infra field at once, detail modal stacks 8+ sections. |

---

## 4. EMOTIONAL JOURNEY

**Peak-end rule:** memorable peaks are creating an idea (hero CTA) and seeing a build succeed ("✓ Built" emerald chip). Likely end-states: empty lists ("No ideas found"), silent status changes, stark confirm modals — forgettable-to-frustrating close.

**Emotional valleys:**
- First visit: hero CTA helps, but empty tiles + no explanation of what happens after Spark → mild abandonment anxiety.
- AI Settings: infrastructure wall → intimidation, "this isn't for me" (for any non-technical admin).
- Drop/Archive/GitHub push: in-app confirm modals are better than `alert()`/`confirm()`, but still cold and final — no undo language, no success toast, no before/after contrast.
- Auto-refresh every 30s: now pauses on interaction (good), but the list can still shift mid-read when idle → startling for the mobile reader.

**Reassurance at high-stakes moments — partial.** Confirm modals explain the consequence but offer no undo, no success toast, and no before/after contrast. High-stakes moments feel final rather than supported.

---

## 5. STRENGTHS (3)

1. **Accessible foundation** — 44px min touch targets on primary controls, working dark mode, `sr-only` labels on all filter selects/inputs. (Caveat: detail modal and AI Settings still violate this — see P3.)
2. **Honest list state** — server-side pagination with `total`/`pages`; header shows "X matching / Y total ideas" (dashboard line 11), so the UI never shows a stale or sliced list.
3. **Clear per-stage color coding + plain-language labels** — distinct hues per stage plus plain "Spark/Scope/Map/Ship/Scale/Dropped/Frozen/Archived" labels give fast recognition of where an idea sits (dashboard lines 3634-3668; home.html lines 97-106).

Honorable mentions: "✓ Just updated" + pause-on-interaction auto-refresh; in-app modals replacing browser dialogs.

---

## 6. PRIORITY ISSUES (P0-P3)

### P0 — No stage glossary / pipeline visualization (Match with real world / Recognition)
**What:** stages render as plain labels via `stageLabel` (dashboard line 3644) and `stageLabels` (lines 3634-3643), but there is no one-line definition anywhere on the dashboard — `stageDescriptions` exists only on `home.html` (lines 107-116). The lifecycle, the product's core concept, is not visualized; no pipeline flow, no "3 of 5 stages complete" cue. Reference codes (`IDEA-9603`) are prominent in `font-mono` but never explained.
**Why it matters:** a casual user cannot answer "what does Spark mean?" or "what happens next?" and cannot progress an idea with confidence. This is the main barrier to moving past the first idea.
**Fix:** add a one-line stage description as a tooltip/caption beside stage chips on the dashboard, plus a short "What the stages mean" line on home; never show raw enum values to users.
**Suggested command:** `$impeccable clarify` — write plain-language stage definitions + a stage glossary component; apply to dashboard chips and home.

### P1 — Detail modal / Scale tab information overload (Aesthetic & minimalist / Cognitive load)
**What:** the detail modal stacks 8+ sections (Idea content, Voting, Admin Actions, Comments, plus action tabs, Scale releases). The Scale tab releases carry ~8 controls each: Mark done, Push to GitHub, Delete, Move-to dropdown, PRD/Design/Build doc dropdowns, per-child status select (dashboard lines 492-584). Action tabs still reference infra keys (PRD_DOC, BUILD_CODE).
**Why it matters:** far more than 4 choices per decision point; casual users freeze. The Scale tab is the densest — release cards with 8+ micro-controls, most below 44px.
**Fix:** progressive disclosure — collapse per-release controls behind an "Actions" menu; hide per-release AI settings behind "Advanced"; limit the detail modal to Idea + Comments + one primary action; move admin infra out of the casual path.
**Suggested command:** `$impeccable distill` — reduce each screen to one primary decision, no more than 4 visible choices at a time.

### P2 — AI Settings still an infra wall (Match with real world / Help)
**What:** `ai_configs.html` remains infrastructure configuration: "API key" (line 56), "Allowed models" (line 60), "Custom endpoint" (line 64), "Monthly spending cap" + `budget_cents` rendered "¢ / 30d" (line 46), cutoff_behaviour refuse/queue/degrade (lines 75-77), embedding/degrade models (lines 82-85), Workspace sandbox/repo (lines 88-93), GitHub PAT "with repo scope" (line 114), per-stage temperature/top_p/max tokens (lines 158-183), Spend table (lines 219-235). Page title is still "AI Settings."
**Why it matters:** meaningless to a casual user and intimidating even for a non-technical admin, who is forced to reason about providers, budgets in cents, and proxy routing.
**Fix:** relegate AI Settings to an explicit "Advanced"/admin-infrastructure mode; surface only plain-language toggles (e.g. "Use AI for this stage: on/off") in the casual path; explain PAT/instance in plain terms where unavoidable.
**Suggested command:** `$impeccable clarify` — rewrite AI Settings copy into plain language and gate the page behind Advanced.

### P3 — Sub-44px touch targets persist in detail modal, Scale tab, AI Settings (Consistency / Accessibility)
**What:** detail-modal vote buttons `p-2 rounded-lg` with no min height (lines 373, 379); comment Reply/Edit/Hide/Delete `min-h-[32px]` (lines 473-477); release Mark done/Push/Delete `min-h-[32px]` (lines 509-512); release Move buttons `min-h-[36px]` (lines 557, 564); "Recreate" buttons `min-h-[36px]` (lines 680, 752); AI Settings Edit provider/stage `min-h-[36px]` (lines 51, 147); Delete target `min-h-[36px]` (line 210). Project standard is 44px min.
**Why it matters:** directly violates the stated design standard and makes the app harder to use one-handed or with limited motor control — exactly the users this product targets.
**Fix:** apply `min-h-[44px]` (or ≥44px touch target) to every interactive element, including detail modal, release micro-controls, and AI Settings.
**Suggested command:** `$impeccable layout` — audit and normalize all touch targets to 44px.

---

## 7. PERSONA RED FLAGS

### Jordan — Confused First-Timer (reads all instructions, hesitates before unfamiliar clicks, misunderstands jargon)
- Lands on home: hero CTA "Create your first idea" is good, but after creating, lands in a dashboard with 8 stage chips and no definition of Spark vs Scope vs Map.
- Sees status chips "Spark"/"Scope"/… with no definition; must guess what moving an idea between them does.
- Reference codes (`IDEA-9603`) look important but are never explained.
- "All ideas" → dashboard with filters + an admin-only bulk bar; Jordan can't tell which controls apply to them.
- Red flag: Jordan abandons, believing the app is "for other people."

### Casey — Distracted Mobile User (one-handed thumb, interrupted mid-flow, limited attention)
- Desktop table is now stacked cards (good), but 3-5 filter controls still crowd the top; opening filters needs precise taps on small selects.
- Modals (`max-w-md` run dialog, `max-w-4xl` detail modal) cover the screen; click-outside dismiss means an accidental tap loses an in-progress run setup.
- Auto-refresh every 30s now pauses on interaction (good), but the list can still shift mid-read when idle — loss of place.
- Two-stage interactions (open 3-dot menu → select status → confirm) require sustained attention; an interruption forces restart.
- Red flag: Casey abandons mid-flow and may not return.

### Sam — Accessibility-Dependent (keyboard-only, screen reader)
- In-app modals are an accessibility improvement over `alert()`/`confirm()`/`prompt()`.
- Sub-44px targets in the detail modal, Scale tab, and AI Settings fail the 44px target Sam depends on (P3).
- Status-chip color is a strong state signal, but plain labels now screen-read as words ("Spark") — fixed.
- `sr-only` labels on filters are good, but modals show no visible focus trap; keyboard tab order through the dense detail modal is long and unclear.
- `min-h-[36px]`/`min-h-[32px]` AI Settings and release controls fail the 44px target.
- Red flag: Sam cannot complete high-stakes actions (Drop, GitHub push) confidently because there is no undo and no accessible confirmation flow beyond the modal.

---

## 8. MINOR OBSERVATIONS

- Date format uses `toLocaleDateString()` + time (dashboard line 3673) — locale-dependent, may read inconsistently.
- Cost column renders "5.00 $" (`ai_configs.html` line 229: `(row.cost_cents / 100).toFixed(2) + ' $'`) — awkward currency formatting.
- "Builds go straight into the app's own repo… open the Build tab, press Stop, then Start" (dashboard line 572) — an instruction buried in prose; high friction for a casual user.
- No "mark all messages read" despite per-message Mark read buttons.
- Auto-refresh cannot be disabled; no user control.
- Navbar dual auth UI + inline `style="display: none;"` overrides (fragile double-render pattern).
- Release micro-control labels mix plain and jargon ("Mark done", "Push to GitHub", "Write PRDs/Designs/Builds").

---

## 9. QUESTIONS TO CONSIDER

1. Should casual users see AI Settings / instance infrastructure at all, or should that entire page live behind an explicit "Admin / Advanced" mode so the main product stays focused on ideas?
2. Could the lifecycle be presented as a visual pipeline (Spark → Scope → Map → Ship → Scale) with the idea as a card moving through it, rather than a plain-label chip in a dense card?
3. Should the first-time experience be a guided "create your first idea" flow (with what-happens-next) instead of exposing a dashboard with filters on visit one?
4. Should every stage chip on the dashboard carry a one-line definition, or a "What the stages mean" help entry?
5. Should the detail modal be split into focused views (Idea / Comments / one primary action) rather than one modal doing everything?

---

### Build-standard note (per AGENTS.md)
This is a design-only review — no template `.py`/model changes, so no migration or `VERSION` bump is required by this assessment itself. If any P0-P2 fix above is implemented as a UI-only template change, verify live in headless Chromium (no E2E suite exists; `tests/ui/` is API-only). This `*.md` assessment stays in the working tree only (not committed), per the repo's no-markdown-in-commits rule.
