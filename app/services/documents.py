import hashlib
import uuid
from pathlib import Path

from fastapi import UploadFile
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
    suffix = Path(upload.filename or "document.pdf").suffix.lower()
    if suffix != ".pdf":
        raise ValueError("Only PDF uploads are supported.")

    stored_name = f"{uuid.uuid4()}{suffix}"
    storage_path = settings.upload_dir / stored_name
    sha256 = hashlib.sha256()
    with storage_path.open("wb") as output:
        while True:
            chunk = upload.file.read(1024 * 1024)
            if not chunk:
                break
            sha256.update(chunk)
            output.write(chunk)

    file_hash = sha256.hexdigest()
    duplicate = db.query(Document).filter(Document.file_hash == file_hash).first()
    if duplicate:
        storage_path.unlink(missing_ok=True)
        raise ValueError(f"This PDF was already uploaded as {duplicate.title or duplicate.original_filename}.")

    clean_title = (book_title or "").strip() or Path(upload.filename or stored_name).stem

    document = Document(
        filename=stored_name,
        original_filename=upload.filename or stored_name,
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
