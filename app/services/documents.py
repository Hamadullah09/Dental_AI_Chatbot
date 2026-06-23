import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
from pypdf import PdfReader
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentStatus, DocumentType, ReviewStatus, TrustLevel, User


def save_upload(
    db: Session,
    upload: UploadFile,
    current_user: User,
    *,
    book_title: str | None = None,
    author_or_source: str | None = None,
    year: int | None = None,
    edition: str | None = None,
    document_type: DocumentType = DocumentType.textbook,
    trust_level: TrustLevel = TrustLevel.high,
    specialty: str | None = None,
    language: str | None = "English",
    review_status: ReviewStatus = ReviewStatus.approved,
) -> Document:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    original_filename = upload.filename or "document.pdf"
    suffix = Path(original_filename).suffix.lower()
    if suffix != ".pdf":
        raise ValueError("Only PDF uploads are supported.")
    if upload.content_type and upload.content_type not in {"application/pdf", "application/x-pdf", "application/octet-stream"}:
        raise ValueError("Uploaded file must be a PDF.")

    stored_name = f"{uuid.uuid4()}{suffix}"
    storage_path = settings.upload_dir / stored_name
    sha256 = hashlib.sha256()
    total_bytes = 0
    max_bytes = settings.max_upload_mb * 1024 * 1024
    first_bytes = b""
    with storage_path.open("wb") as output:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            if not first_bytes:
                first_bytes = chunk[:8]
            total_bytes += len(chunk)
            if total_bytes > max_bytes:
                storage_path.unlink(missing_ok=True)
                raise ValueError(f"PDF is too large. Maximum allowed size is {settings.max_upload_mb} MB.")
            sha256.update(chunk)
            output.write(chunk)

    if total_bytes == 0:
        storage_path.unlink(missing_ok=True)
        raise ValueError("Uploaded PDF is empty.")
    if not first_bytes.startswith(b"%PDF-"):
        storage_path.unlink(missing_ok=True)
        raise ValueError("Uploaded file is not a valid PDF.")

    try:
        reader = PdfReader(str(storage_path))
        if reader.is_encrypted:
            storage_path.unlink(missing_ok=True)
            raise ValueError("Encrypted PDFs are not supported. Please upload an unlocked PDF.")
        if len(reader.pages) == 0:
            storage_path.unlink(missing_ok=True)
            raise ValueError("PDF has no readable pages.")
    except ValueError:
        raise
    except Exception as exc:
        storage_path.unlink(missing_ok=True)
        raise ValueError(f"PDF validation failed: {exc}")

    file_hash = sha256.hexdigest()
    duplicate = db.query(Document).filter(Document.file_hash == file_hash).first()
    if duplicate:
        storage_path.unlink(missing_ok=True)
        raise ValueError(f"This PDF was already uploaded as {duplicate.title or duplicate.original_filename}.")

    clean_title = (book_title or "").strip() or Path(original_filename).stem

    document = Document(
        filename=stored_name,
        original_filename=original_filename,
        title=clean_title,
        author_or_source=(author_or_source or "").strip() or None,
        edition=(edition or "").strip() or None,
        publication_year=year,
        document_type=document_type,
        trust_level=trust_level,
        review_status=review_status,
        specialty=(specialty or "").strip() or None,
        language=(language or "").strip() or None,
        file_hash=file_hash,
        content_type=upload.content_type,
        storage_path=str(storage_path),
        status=DocumentStatus.uploaded,
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document
