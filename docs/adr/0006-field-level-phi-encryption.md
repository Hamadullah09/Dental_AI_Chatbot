# ADR-0006: Field-level encryption for PHI-adjacent columns via a SQLAlchemy TypeDecorator

Date: 2026-07-28
Status: Accepted

## Context

`docs/GAP_AUDIT_PHASE0.md` finding #6 confirmed this product's scope had grown to include
real clinical-data-adjacent tables (`Prescription`, `DentalRecord`) storing patient-specific
information, stored as plain `Text` columns. `docs/COMPLIANCE.md` (also produced this
pass) establishes this puts the product in scope for handling PHI-adjacent data even
though it isn't a covered entity outright. Plaintext storage of that data in Postgres
means a database backup, a misconfigured read replica, or direct DB access by anyone with
infra credentials (not just application-layer access) exposes it directly.

## Decision

Add `app/core/encryption.py`: an `EncryptedText(TypeDecorator[str])` using Fernet
symmetric encryption, transparent at the ORM layer (`process_bind_param` encrypts on
write, `process_result_value` decrypts on read - application code reading
`Prescription.medication_notes` etc. sees plaintext, encryption is invisible above the
model layer). `Prescription` and `DentalRecord`'s sensitive text columns
(`app/models.py`) were changed from `Text` to `EncryptedText`. A one-time backfill script
(`scripts/encrypt_existing_phi.py`) encrypts pre-existing plaintext rows. Decryption
falls back to returning the raw value on failure rather than raising, specifically so
rows written before this migration (or during a rollout window) don't 500 the request -
the tradeoff is that a row that's genuinely corrupted ciphertext would also silently
return garbage rather than erroring; this is documented risk, not an oversight.

## Consequences

- Data at rest in Postgres (including backups, replicas, and direct psql access) is now
  encrypted for the specific columns holding prescription/dental-record content -
  encryption key compromise (`field_encryption_key` setting) is now the operative threat
  model for that data, not "anyone with DB access."
- This is field-level, not whole-database, encryption - column names, table structure,
  row counts, and any *non*-sensitive columns on those same tables remain visible to
  anyone with DB access. If broader at-rest encryption is wanted (e.g. transparent data
  encryption at the Postgres/volume level), that's complementary, not a replacement -
  and is an infra-level decision (managed Postgres offerings often provide this
  natively - see `k8s/README.md`'s Postgres section) outside this pass's scope.
- Every encrypted column read now costs a Fernet decrypt operation - negligible for
  per-request row counts here, but worth knowing if this pattern gets applied to a
  bulk-export or reporting query path later.
- The encryption key (`field_encryption_key`) is now a piece of secret material whose
  loss means the encrypted data is permanently unrecoverable, and whose compromise means
  every encrypted row is compromised. Key rotation is not implemented in this pass -
  flagged as a follow-up rather than silently assumed to be "handled."

## Alternatives considered

- **Database-level (Postgres pgcrypto / TDE) encryption instead of application-level.**
  Rejected for this specific case: pgcrypto requires either raw SQL (bypassing the ORM
  layer entirely, a larger refactor) or key material passed per-query; TDE is typically a
  managed-Postgres feature (RDS, Cloud SQL) not universally available, and this pass
  needed something that works identically self-hosted or managed. Application-level
  encryption via a TypeDecorator is portable across both.
- **Encrypt at the API boundary (before the request reaches the ORM) instead of at the
  column type.** Rejected - would require every call site that reads/writes these fields
  to remember to encrypt/decrypt manually, exactly the kind of "one call site forgets"
  bug this hardening pass is trying to close elsewhere (see ADR-0001's motivating
  finding #1 about silent, un-noticed drift).
