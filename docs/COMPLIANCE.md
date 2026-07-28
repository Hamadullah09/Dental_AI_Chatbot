# Compliance Posture (Phase 2 — working notes, not a legal opinion)

This documents what the product currently does, and what a HIPAA/GDPR compliance program
would require, so decisions aren't made silently. **This is not legal advice** — treat it
as an engineering-facing starting point for counsel/compliance review, per Phase 0 finding
#6: the product now stores real clinical scheduling and prescription data, not just chat
transcripts, which raises the bar considerably.

## What counts as PHI/PII here

- **PHI**: `Prescription` (diagnosis, medicines, dosage, frequency, duration, instructions),
  `DentalRecord` (previous_problems, diagnoses, treatments, surgeries, allergies,
  medications, notes), and any chat `Message` content discussing a user's own symptoms.
- **PII**: `User` (email, full_name), `Appointment` (scheduling data tied to a named
  patient), `AuditLog` (ip_address, user_agent — itself useful for compliance, but is PII).

## What's implemented as of this phase

- Field-level encryption at rest for the PHI text columns above (`app/core/encryption.py`,
  `EncryptedText`). Key sourced from `FIELD_ENCRYPTION_KEY`; falls back to deriving from
  `JWT_SECRET_KEY` if unset (logs a warning) — production should set a dedicated key from a
  real secrets manager/KMS, not reuse the JWT signing key.
- Field-level audit logging on read/write/export of `DentalRecord` and `Prescription`
  (`app/core/audit.py`, wired into `app/routers/dental_records.py` and
  `app/routers/prescriptions.py`). Not yet extended to `appointments.py` (lower
  sensitivity — scheduling metadata, not clinical content — but same pattern applies if
  required).
- RBAC enforced server-side on every clinical endpoint (pre-existing, verified in Phase 0).
- JWT access-token blocklist + admin "revoke all sessions" endpoint
  (`POST /admin/users/{user_id}/revoke-sessions`) for incident response.

## What's NOT implemented (explicitly out of scope for this phase)

- **BAAs (Business Associate Agreements)**: required under HIPAA with every subprocessor
  that touches PHI — this includes whatever hosts the Ollama/Qdrant/Postgres/Redis
  infrastructure if not self-hosted, and any web-search or third-party API used in
  `app/services/web_search.py`. Legal/ops decision, not an engineering one.
- **Data residency**: no controls exist over where backups, Qdrant vectors, or DB replicas
  physically live. Relevant for both HIPAA (varies by state/BAA terms) and GDPR (EU data
  must generally stay in-region absent a valid transfer mechanism).
- **Right-to-erasure (GDPR Article 17)**: `ON DELETE CASCADE` exists at the DB level for
  most PHI foreign keys, so deleting a `User` does cascade-delete their records - but there
  is no user-facing "delete my account and all data" flow, no defined retention period
  after which data is auto-purged, and Qdrant/vector-store data referencing a deleted
  user's uploaded documents is not covered by the cascade at all (separate store).
- **Consent management**: no explicit consent capture for PHI processing, no distinction
  between "required for treatment" processing and optional processing (e.g. using chat
  history to improve the product).
- **Breach notification workflow**: audit logging now exists to *support* an investigation,
  but there's no defined incident-response runbook wiring it to a notification process
  (see `docs/RUNBOOK.md` from Phase 7 for the operational side of this).
- **Encryption in transit**: assumed handled by the deployment's TLS termination
  (Cloudflare/Nginx per the architecture diagram) — not verified as part of this phase.
- **Backup encryption**: `app/services/security.py::SecurityManager.encrypt_backup()`
  exists but nothing in the ingestion/backup scripts calls it — backups are not
  confirmed encrypted at rest.

## Policy decisions flagged for the product owner (not decided unilaterally here)

1. Can the AI suggest/confirm medication dosages at all, or must that always route to a
   human dentist? (See Phase 5b prescriptions policy question.) The current
   implementation lets the *dentist* role see full dosage detail and blocks/redirects the
   *patient*/*student* roles — a specific choice made in `contains_prescribing_language()`
   that should be confirmed, not assumed correct.
2. Retention period for chat transcripts and clinical records — none is currently defined;
   data persists indefinitely.
3. Whether scraped dentist-directory data (`app/services/scraper/`) is subject to the same
   consent/retention rules as directly-entered patient data (see Phase 5b).
