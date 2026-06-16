import shutil
import uuid
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Document, DocumentStatus, User


def save_upload(db: Session, upload: UploadFile, current_user: User) -> Document:
    settings = get_settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "document.pdf").suffix.lower()
    if suffix != ".pdf":
        raise ValueError("Only PDF uploads are supported.")

    stored_name = f"{uuid.uuid4()}{suffix}"
    storage_path = settings.upload_dir / stored_name
    with storage_path.open("wb") as output:
        shutil.copyfileobj(upload.file, output)

    document = Document(
        filename=stored_name,
        original_filename=upload.filename or stored_name,
        content_type=upload.content_type,
        storage_path=str(storage_path),
        status=DocumentStatus.uploaded,
        uploaded_by=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)
    return document
