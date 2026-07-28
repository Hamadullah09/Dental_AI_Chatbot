# ADR-0005: JWT jti-based revocation blocklist, refresh token rotation, device binding

Date: 2026-07-28
Status: Accepted

## Context

The pre-existing JWT implementation (`app/core/security.py`, `app/routers/auth.py`) had
no way to revoke an issued access token before its expiry (originally 1440 minutes / 24
hours - a long window for a token that, once issued, was valid no matter what happened to
the account afterward: password change, admin-initiated session revocation, or a
suspected-compromised device all had no effect on already-issued tokens), and refresh
tokens were not rotated or bound to anything about the client that first obtained them.

## Decision

- Add a `jti` (JWT ID) and `iat` claim to every access token (`create_access_token()`),
  and a Redis-backed revocation blocklist (`app/core/token_blocklist.py`:
  `revoke_access_token()`, `is_access_token_revoked()`) checked on every authenticated
  request. `revoke_all_tokens_for_user()` supports an admin-initiated "sign this user out
  everywhere" action (`/admin` endpoint added this pass), implemented as a per-user
  revocation cutoff timestamp rather than tracking every individual token.
- Reduce `access_token_expire_minutes` from 1440 to 120 - a shorter-lived access token
  bounds the damage window of a leaked token without the blocklist even needing to fire.
- Bind refresh tokens to a device fingerprint at issuance (`bind_refresh_token_to_device()`)
  and check for a mismatch on `/refresh` (`refresh_token_device_mismatch()`) -
  **non-blocking**: a mismatch is audit-logged, not rejected, because the fingerprint
  (derived from User-Agent) is weak enough that false positives (browser update, etc.)
  are common; this is a detection signal for the audit log, not an enforcement mechanism.
- `/logout` now revokes the access token's `jti` in addition to the existing refresh
  token revocation, so logout actually invalidates the still-live access token instead of
  only preventing future refreshes.

## Consequences

- A compromised or leaked access token can now be revoked immediately (blocklist), and
  even without explicit revocation, the blast radius is capped at 2 hours instead of 24.
- Every authenticated request now does one additional Redis read (blocklist check) -
  this fails open (see ADR-0004): if Redis is unreachable, the request proceeds as if
  not revoked, rather than locking out every user during a Redis outage. This is a
  deliberate availability-over-strict-revocation tradeoff, worth knowing if a security
  review ever asks "can a revoked token still be used?" - answer: only during a Redis
  outage, and only until Redis recovers or the token's own (now much shorter) expiry.
- Device-fingerprint mismatch is intentionally not an enforcement gate. If a stricter
  policy (e.g. force re-login on device mismatch) is wanted, that's a product decision to
  make explicitly, not something this pass decided by default.

## Alternatives considered

- **Track every individual revoked/valid token instead of a per-user cutoff timestamp
  for "revoke all."** Rejected - unbounded storage growth proportional to tokens ever
  issued; a cutoff timestamp gives the same practical guarantee ("nothing issued before
  time X is valid") in O(1) storage per user.
- **Reject refresh requests outright on device-fingerprint mismatch.** Rejected for this
  pass given how weak a User-Agent-derived fingerprint is as a signal - flagged as a
  product/policy question (see the code comment in `app/routers/auth.py`) rather than
  silently making logins less reliable for users who change browsers/update software.
