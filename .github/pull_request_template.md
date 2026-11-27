Closes #<issue number>

## What changed

<!-- One or two sentences. Name the feature or fix, not the file list. -->

## Scope

- [ ] One slice only; diff is under ~400–500 lines
- [ ] No unrelated refactors, renames or formatting churn
- [ ] Files touched are listed in the read-only plan

## Verification

- [ ] `pytest` (full suite, coverage gate met)
- [ ] `python scripts/check_no_external_calls.py`
- [ ] `python scripts/check_no_credentials_in_config.py`
- [ ] `python scripts/check_no_secrets.py`
- [ ] `python scripts/check_api_contract.py` (when API payloads changed)

## Release bookkeeping

- [ ] `VERSION` bumped (patch / minor / major)
- [ ] `ReleaseNotes.md` updated with the version and date
- [ ] Shipped items removed from `docs/ROADMAP.md`

Merge with squash once `guardrails` and `drill` are green.
