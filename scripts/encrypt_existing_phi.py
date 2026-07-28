"""One-time backfill: re-saves every Prescription and DentalRecord row so that any
legacy plaintext PHI fields (written before EncryptedText was applied to those columns)
get encrypted on write. Safe to run repeatedly - already-encrypted values decrypt and
re-encrypt to a new ciphertext, plaintext values encrypt for the first time.

Run from the project root with the same environment the app uses:
    python scripts/encrypt_existing_phi.py

This is NOT required for the app to keep working (EncryptedText already falls back to
returning legacy plaintext as-is on read - see app/core/encryption.py), but should be run
once after enabling FIELD_ENCRYPTION_KEY in production so existing rows aren't left
readable in plaintext in the database.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.core.database import SessionLocal  # noqa: E402
from app.models import DentalRecord, Prescription  # noqa: E402

PRESCRIPTION_FIELDS = ["diagnosis", "medicines", "dosage", "frequency", "duration", "instructions", "notes"]
DENTAL_RECORD_FIELDS = ["previous_problems", "diagnoses", "treatments", "surgeries", "allergies", "medications", "notes"]


def _touch(session, model, fields: list[str]) -> int:
    count = 0
    for row in session.query(model).all():
        for field in fields:
            setattr(row, field, getattr(row, field))
            # SQLAlchemy skips the UPDATE for a column re-assigned to an equal Python
            # value, but the equal-looking plaintext still needs re-encrypting - force it.
            flag_modified(row, field)
        count += 1
    session.commit()
    return count


def main() -> None:
    with SessionLocal() as session:
        prescriptions = _touch(session, Prescription, PRESCRIPTION_FIELDS)
        records = _touch(session, DentalRecord, DENTAL_RECORD_FIELDS)
    print(f"Re-saved {prescriptions} prescriptions and {records} dental records.")


if __name__ == "__main__":
    main()
