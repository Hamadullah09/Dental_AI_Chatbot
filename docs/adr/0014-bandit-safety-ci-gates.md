# ADR-0014: bandit/safety made real, blocking CI gates via documented, time-boxed suppressions

Date: 2026-07-28
Status: Accepted

## Context

`docs/GAP_AUDIT_PHASE0.md` finding #16 confirmed the CI security jobs
(`safety check -r requirements.txt || true`, `bandit -r app/ ... || true`) could never
fail the build. A local run against the actual codebase found: bandit reported 40
findings, 35 of them `B110` (try/except/pass - see ADR-0004's fail-open caching pattern,
used deliberately and extensively) and the remaining 5 a mix of real, fixable issues and
false positives; `safety check -r requirements.txt` reported **zero** vulnerabilities,
which turned out to be misleading rather than reassuring - `requirements.txt` uses
floating version specs (`cryptography>=42.0.0`, this project's pinning style throughout),
and safety's default `ignore-unpinned-requirements: true` silently drops every finding
against an unpinned spec, so scanning `requirements.txt` as-is could never report a real
finding regardless of what was actually installed.

## Decision

- **bandit**: fix the real findings - `hashlib.md5(..., usedforsecurity=False)` in
  `app/scrapers/crawler.py` (non-cryptographic ID generation, not signature/auth use), and
  scheme validation before `urlopen()` in `app/services/dataset_generation.py`. Suppress
  the two false positives (`PASSWORD_ALGORITHM` string constant, `"pass_rate": 0.0` dict
  key - both flagged as "possible hardcoded password" on the substring "password"/"pass")
  with a per-line `# nosec <id>` plus a reason. Skip `B110` codebase-wide via
  `pyproject.toml`'s `[tool.bandit]`, with the fail-open-pattern rationale documented
  inline rather than suppressed silently or per-instance (35 individual `# nosec` comments
  would bury the actual pattern in noise). CI now runs bandit without `|| true`.
- **safety**: scan a `pip freeze` of the *resolved* install rather than
  `requirements.txt` directly, so the unpinned-requirements blind spot doesn't apply.
  Bump `pydantic-settings` past a real, fixed path-traversal issue (unused in this
  codebase - only `env_file` config is used, never `secrets_dir` - but a free patch
  bump). Document and time-box (`.safety-policy.yml`, `expires: 2027-01-28`) the two
  remaining findings, both in `ecdsa` (a transitive dependency of `python-jose`,
  unreachable here since JWTs are signed HS256/hmac - see ADR-0005 - never an EC
  algorithm - and with no upstream fix planned per the `ecdsa` maintainers' own
  documented position on side-channel resistance in pure Python). CI now runs safety
  without `|| true`.

## Consequences

- Both scanners are now real gates - a future dependency bump or code change introducing
  a genuine new finding fails the build, which was never possible before this pass.
- The `.safety-policy.yml` ignores have an explicit expiry date (roughly 6 months out),
  not an indefinite bypass - forcing a periodic re-look even though the underlying
  `ecdsa` issue is unlikely to change (no upstream fix exists) rather than letting a
  "temporary" suppression silently become permanent.
- `pyproject.toml`'s B110 skip is codebase-wide, meaning a *new*, genuinely-risky
  try/except/pass introduced elsewhere (not part of the deliberate fail-open pattern)
  would also not be flagged by bandit. This is a real tradeoff of choosing a policy-level
  skip over per-instance suppression - code review remains the actual safeguard against a
  new careless try/except/pass, not bandit.
- If `python-jose` is ever replaced (e.g. for the ecdsa transitive dependency itself, or
  for other reasons), the `.safety-policy.yml` ignores for `64396`/`64459` should be
  removed at that time rather than left stale referencing a dependency that's no longer
  present.

## Alternatives considered

- **Leave `safety check` scanning `requirements.txt` directly but set
  `ignore-unpinned-requirements: false`** instead of scanning a `pip freeze`. Rejected -
  this would report findings against the *range* of versions a floating spec permits
  (e.g. every version `cryptography>=42.0.0` has ever had a vulnerability in), not the
  actually-installed version - noisy and not actionable in the way a resolved-install
  scan is.
- **Pin every dependency in `requirements.txt` to exact versions** instead of scanning a
  frozen snapshot in CI only. Considered and deferred - this project's floating-spec
  style is an existing convention affecting how the whole team does upgrades, and
  changing it project-wide is a bigger, more contestable decision than fixing what CI
  scans; flagged as a reasonable future option rather than changed silently as a side
  effect of this security-gate work.
- **Replace `python-jose`** to remove the `ecdsa` transitive dependency entirely.
  Rejected for this pass - a JWT library swap is a tool-evaluation-requiring change in
  the same category this hardening pass's brief said needed explicit sign-off (Qdrant/
  Ollama/Qwen swaps specifically named, but the same caution applies to a security-critical
  library like the JWT implementation), and the underlying vulnerability is unreachable
  in this codebase's actual usage regardless.
