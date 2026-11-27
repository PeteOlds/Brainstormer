# OpenCode + GitHub workflow

How to work on brainstormer with local models without corrupting `main`. Project `AGENTS.md` rules override the global agent defaults; `main` is protected and PR-only.

## 1. Start from an issue

Every piece of work has a roadmap ID (`RM-xxx`, `BUG.xxx`, `REQ.xxx`) and a GitHub issue. Reference the issue in the read-only planning prompt:

```text
Read-only plan for issue #4 (RM-052). Map affected files, data flow and edge
cases. List the files you intend to change. Do not edit anything yet.
```

Approve the plan before switching to build mode.

## 2. Isolate the work in a worktree

Switching branches in one checkout breaks dev servers, migrations and the venv. Use a worktree instead. `git stash` is broken in this repo; move uncommitted work with a patch file if needed.

```bash
git worktree add ../brainstormer-rm052 -b feat/RM-052 main
cd ../brainstormer-rm052
```

In OpenCode, move the session into that directory with `session_move` so all edits stay inside the worktree. Activate the primary checkout's venv by absolute path — worktrees have no venv of their own:

```bash
source /mnt/General/OpenCode/brainstormer/venv/bin/activate
```

## 3. Build in thin, verified slices

One slice = one branch. Keep PR diffs under roughly 400–500 lines. Order work as: schema/contract → handler + happy-path test → UI/polish → hardening. Commit at each verified checkpoint with a semantic prefix (`feat:`, `fix:`, `docs:`), so a bad later stage can be discarded with `git reset --hard HEAD` without losing earlier work.

Before each checkpoint:

```bash
python scripts/check_no_external_calls.py
python scripts/check_no_credentials_in_config.py
python scripts/check_no_secrets.py
pytest <target tests> -q --no-cov
```

Before pushing, run the full suite (`pytest`) and re-run the guardrail scripts.

## 4. PR, checks, squash merge

```bash
git push -u origin feat/RM-052
gh pr create --base main --title "feat: typed design contract (RM-052)" \
  --body "Closes #4 ..."
gh pr checks <number> --watch
```

Required checks are `guardrails` and `drill`. Only squash-merge after they pass:

```bash
gh pr merge <number> --squash --delete-branch
```

Then clean up and, before any risky work, tag a known-good point:

```bash
git worktree remove ../brainstormer-rm052
git tag v0.102.0-stable && git push --tags
```

## 5. Release bookkeeping

Every build bumps `VERSION` (patch, minor or major), adds a `ReleaseNotes.md` section, and removes shipped items from `docs/ROADMAP.md`. The roadmap holds outstanding work only; the ID index in it maps shipped abbreviations back to full descriptions.

## Notes

- Ollama runs locally through `app/services/ollama_client.py`; agentic runs use the serial `opencode` queue via `enqueue_generation()`.
- Actions secret `CI_TEST_PAT` is exposed to tests as `GITHUB_TEST_PAT`; GitHub reserves the `GITHUB_` prefix for secret names.
- Broker topology, migrations and build roots are documented in the root `AGENTS.md`.
