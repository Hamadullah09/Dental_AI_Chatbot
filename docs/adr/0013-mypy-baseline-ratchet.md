# ADR-0013: mypy baseline ratchet instead of requiring full strict-mode compliance immediately

Date: 2026-07-28
Status: Accepted

## Context

`pyproject.toml` already declared `[tool.mypy] strict = true`, but CI ran
`mypy app/ --ignore-missing-imports || true` - the `|| true` meant this step could never
fail the build regardless of how many errors existed or how many a given change
introduced. A full run at the time this was discovered showed roughly 206 errors across
43 files, concentrated in legacy modules this hardening pass's brief didn't otherwise
touch (`app/services/rag.py` alone accounted for 44; `dashboard.py`, `settings.py`,
`dental_records.py` made up most of the rest). Fixing all of them blind, under this
pass's time budget and without the deeper context needed to safely retype a 2400+ line
module like `rag.py`, risked introducing real behavior bugs for the sake of a type
checker - a worse outcome than the status quo for a medical-adjacent product.

## Decision

Fix every mypy error in every module this pass created or heavily modified
(`app/core/resilience.py`, `concurrency.py`, `encryption.py`, `token_blocklist.py`,
`audit.py`, `app/services/degradation.py`, `retrieval_cache.py`, `embeddings.py`,
`memory.py`, `app/workers/tasks.py`, and the new/modified portions of
`app/agent/graph.py`) down to zero, verified individually per file, not just netted
against the total. For the remaining pre-existing legacy debt (166 errors after those
fixes), add `scripts/mypy_baseline_gate.py`: it runs mypy, compares the error count
against a committed `mypy_baseline.txt` (166), and fails the build only if the count goes
**up** - a new change introducing new type errors fails CI; the pre-existing 166 do not
block anything, but can no longer silently grow either. `.github/workflows/ci-cd.yml`'s
mypy step now runs this gate instead of `mypy ... || true`.

## Consequences

- mypy is now a real, blocking CI gate for the first time - any future change that adds a
  new type error (in a file this pass touched, or would otherwise touch) fails the build.
- The 166-error legacy baseline is explicitly tracked debt, not silently ignored debt -
  its exact size is visible in a committed file, and the gate prints a reminder to lower
  the baseline (`--update` flag) whenever a fix brings the count down, so incremental
  cleanup is rewarded rather than invisible.
- This means a contributor fixing an unrelated bug in, say, `rag.py` is not blocked by
  that file's pre-existing type debt, but also isn't required to fix any of it - the gate
  is silent on pre-existing errors either way. Deliberately: forcing unrelated type fixes
  into every PR that touches a legacy file would create exactly the kind of "fix
  everything nearby while you're in there" scope creep this pass's own brief warns
  against.

## Alternatives considered

- **Fix all 206 (166 remaining) errors now, regardless of module ownership/context.**
  Rejected - explicitly evaluated and rejected per the Context above; the risk of
  introducing subtle behavior bugs in modules outside this pass's actual scope of
  understanding outweighed the type-safety benefit, especially for a product where a
  citation-verification or retrieval-filtering regression has real consequences.
- **Per-module `[[tool.mypy.overrides]]` marking legacy files as permanently
  looser-checked**, instead of a global count-based ratchet. Considered - rejected in
  favor of the ratchet because per-module overrides would need every legacy file
  enumerated and kept in sync as files are added/renamed/cleaned up, whereas a single
  count comparison needs no such list and naturally reflects progress as files improve.
- **Leave `|| true` in place and just document the debt in a markdown file.** Rejected -
  this was explicitly the fallback option offered by this pass's own brief ("either get
  the codebase to a state where type errors actually fail the build, or explicitly
  document why it's advisory only") and a real gate was achievable without the
  fix-everything risk, so the stronger option was taken.
