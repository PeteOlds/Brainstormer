# Flutter ↔ Jinja parity matrix

Gate for RM-013 (delete legacy Jinja). Every row must be `done` with a
Playwright test in `tests/ui/` before Jinja removal.

| Area | Jinja control (`app/templates/ideas/dashboard.html`) | Flutter location | Status |
|---|---|---|---|
| Voting | up/down + score (`dashboard.js:1861`) | `widgets/vote_control.dart` | done |
| Tabs | lifecycleTabs / analysisTabs | `idea_detail_page.dart` `_buildTabs` | done |
| Overview | archive/restore, edit title, status dropdown | `_overviewTab` | done |
| Comments | post/list | `_commentsList` | done |
| Analysis | rerun/edit/discussion | `_analysisTab` (read-only) | partial |
| Build | preview + confirm write | `_buildTab` | done |
| Build | runbook (setup/run/copy) | `_buildTab` | done |
| Build | one-click run start/stop/open/logs | `_managedAppSection` | done |
| Build | tests checklist | `_testsTab` | done |
| Scale | suggest improvement / report problem | `_scaleTab` | done |
| Scale | releases CRUD + pipeline | `_scaleTab` | partial |
| Scale | bulk actions | (pending) | todo |
| Activity | labelled refresh | `activity_page.dart` | done |
PY