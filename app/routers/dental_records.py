import io
import os
import qrcode
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pypdf import PdfWriter, PdfReader
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch, mm
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.deps import get_current_user, require_admin
from app.models import DentalRecord, Dentist, User, UserRole
from app.schemas import (
    DentalRecordCreate,
    DentalRecordRead,
    DentalRecordSearchParams,
    DentalRecordSearchResult,
    DentalRecordUpdate,
)

router = APIRouter(prefix="/dental-records", tags=["dental-records"])

settings = get_settings()


def generate_dental_record_pdf(record: DentalRecord, patient: User, dentist: Dentist | None) -> bytes:
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=6,
        alignment=1,
        textColor=colors.HexColor("#1a3c5e"),
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=11,
        spaceAfter=4,
        alignment=1,
        textColor=colors.HexColor("#4a4a4a"),
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=13,
        spaceBefore=16,
        spaceAfter=8,
        textColor=colors.HexColor("#1a3c5e"),
    )
    normal_style = ParagraphStyle(
        "CustomNormal",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=4,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=10,
        leading=14,
        spaceAfter=4,
        textColor=colors.HexColor("#2c3e50"),
        fontName="Helvetica-Bold",
    )

    elements = []

    clinic_name = dentist.clinic_name if dentist else "Dental Clinic"
    elements.append(Paragraph(clinic_name.upper(), title_style))
    elements.append(Paragraph("Dental Records", subtitle_style))
    elements.append(Spacer(1, 8))

    qr = qrcode.make(f"dental_record:{record.id}:{record.patient_id}")
    qr_buffer = io.BytesIO()
    qr.save(qr_buffer, format="PNG")
    qr_buffer.seek(0)
    qr_img = Image(qr_buffer, width=40 * mm, height=40 * mm)
    qr_img.hAlign = "RIGHT"

    header_data = [
        [
            Paragraph(f"<b>Patient:</b> {patient.full_name or 'N/A'}<br/>"
                      f"<b>Email:</b> {patient.email}", normal_style),
            qr_img,
        ],
        [
            Paragraph(f"<b>Record ID:</b> {record.id[:8].upper()}<br/>"
                      f"<b>Date:</b> {record.created_at.strftime('%B %d, %Y')}<br/>"
                      f"<b>Dentist:</b> {dentist.full_name if dentist else 'N/A'}", normal_style),
            "",
        ],
    ]

    header_table = Table(header_data, colWidths=[130 * mm, 40 * mm])
    header_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    elements.append(header_table)
    elements.append(Spacer(1, 12))

    hr = Table([[""]], colWidths=[170 * mm])
    hr.setStyle(TableStyle([
        ("LINEBELOW", (0, 0), (-1, -1), 1, colors.HexColor("#1a3c5e")),
    ]))
    elements.append(hr)
    elements.append(Spacer(1, 8))

    sections = [
        ("Previous Dental Problems", record.previous_problems),
        ("Diagnoses", record.diagnoses),
        ("Treatments", record.treatments),
        ("Surgeries", record.surgeries),
        ("Allergies", record.allergies),
        ("Current Medications", record.medications),
    ]

    for title, content in sections:
        if content:
            elements.append(Paragraph(title, section_style))
            elements.append(Paragraph(content, normal_style))
            elements.append(Spacer(1, 6))

    if record.xrays:
        elements.append(Paragraph("X-Rays", section_style))
        for xray in record.xrays:
            elements.append(Paragraph(f"• {xray}", normal_style))
        elements.append(Spacer(1, 6))

    if record.reports:
        elements.append(Paragraph("Reports", section_style))
        for report in record.reports:
            elements.append(Paragraph(f"• {report}", normal_style))
        elements.append(Spacer(1, 6))

    if record.images:
        elements.append(Paragraph("Images", section_style))
        for img in record.images:
            elements.append(Paragraph(f"• {img}", normal_style))
        elements.append(Spacer(1, 6))

    if record.notes:
        elements.append(Paragraph("Clinical Notes", section_style))
        elements.append(Paragraph(record.notes, normal_style))
        elements.append(Spacer(1, 6))

    if record.follow_up_records:
        elements.append(Paragraph("Follow-up Records", section_style))
        elements.append(Paragraph(record.follow_up_records, normal_style))
        elements.append(Spacer(1, 6))

    if record.follow_up_date:
        elements.append(Paragraph("Next Follow-up", section_style))
        elements.append(Paragraph(
            f"Scheduled for: {record.follow_up_date.strftime('%B %d, %Y')}",
            normal_style
        ))
        elements.append(Spacer(1, 12))

    elements.append(Spacer(1, 20))

    if dentist:
        sig_data = [
            ["_" * 40, "_" * 40],
            ["Dentist Signature", "Date"],
            [f"Dr. {dentist.full_name}", record.created_at.strftime("%B %d, %Y")],
        ]
        sig_table = Table(sig_data, colWidths=[85 * mm, 85 * mm])
        sig_table.setStyle(TableStyle([
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("FONTSIZE", (0, 0), (-1, -1), 10),
            ("TEXTCOLOR", (0, 1), (-1, 1), colors.HexColor("#888888")),
            ("TEXTCOLOR", (0, 2), (-1, 2), colors.HexColor("#2c3e50")),
            ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))
        elements.append(sig_table)
        elements.append(Spacer(1, 12))

    disclaimer = Paragraph(
        "<i>Disclaimer: This dental record is a confidential medical document. "
        "Please keep it secure and share only with authorized healthcare providers.</i>",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#888888"))
    )
    elements.append(disclaimer)

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


@router.get("", response_model=DentalRecordSearchResult)
def search_dental_records(
    params: DentalRecordSearchParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DentalRecordSearchResult:
    query = db.query(DentalRecord)

    if current_user.role == UserRole.patient:
        query = query.filter(DentalRecord.patient_id == current_user.id)
    elif current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if dentist:
            query = query.filter(DentalRecord.dentist_id == dentist.id)
        else:
            return DentalRecordSearchResult(records=[], total=0, page=params.page, limit=params.limit, total_pages=0)

    if params.patient_id and current_user.role == UserRole.admin:
        query = query.filter(DentalRecord.patient_id == params.patient_id)
    if params.dentist_id and current_user.role == UserRole.admin:
        query = query.filter(DentalRecord.dentist_id == params.dentist_id)

    if params.query:
        search = f"%{params.query}%"
        query = query.join(Dentist, isouter=True).join(User, isouter=True).filter(
            or_(
                DentalRecord.previous_problems.ilike(search),
                DentalRecord.diagnoses.ilike(search),
                DentalRecord.treatments.ilike(search),
                Dentist.full_name.ilike(search),
                User.full_name.ilike(search),
            )
        )

    total = query.count()
    total_pages = (total + params.limit - 1) // params.limit
    offset = (params.page - 1) * params.limit

    records = query.order_by(DentalRecord.created_at.desc()).offset(offset).limit(params.limit).all()

    return DentalRecordSearchResult(
        records=[DentalRecordRead.model_validate(r) for r in records],
        total=total,
        page=params.page,
        limit=params.limit,
        total_pages=total_pages,
    )


@router.get("/{record_id}", response_model=DentalRecordRead)
def get_dental_record(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DentalRecordRead:
    record = db.get(DentalRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dental record not found")

    if current_user.role == UserRole.patient and record.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or record.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    return DentalRecordRead.model_validate(record)


@router.post("", response_model=DentalRecordRead, status_code=status.HTTP_201_CREATED)
def create_dental_record(
    payload: DentalRecordCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DentalRecordRead:
    if current_user.role not in [UserRole.dentist, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only dentists can create dental records")

    patient = db.get(User, payload.patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    if patient.role != UserRole.patient:
        raise HTTPException(status_code=400, detail="User is not a patient")

    dentist = None
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist:
            raise HTTPException(status_code=403, detail="Dentist profile not found")
    elif payload.dentist_id:
        dentist = db.get(Dentist, payload.dentist_id)

    record = DentalRecord(
        patient_id=payload.patient_id,
        dentist_id=dentist.id if dentist else None,
        previous_problems=payload.previous_problems,
        diagnoses=payload.diagnoses,
        treatments=payload.treatments,
        surgeries=payload.surgeries,
        allergies=payload.allergies,
        medications=payload.medications,
        xrays=payload.xrays,
        reports=payload.reports,
        images=payload.images,
        notes=payload.notes,
        follow_up_date=payload.follow_up_date,
        follow_up_records=payload.follow_up_records,
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return DentalRecordRead.model_validate(record)


@router.patch("/{record_id}", response_model=DentalRecordRead)
def update_dental_record(
    record_id: str,
    payload: DentalRecordUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DentalRecordRead:
    record = db.get(DentalRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dental record not found")

    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or record.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == UserRole.patient:
        raise HTTPException(status_code=403, detail="Patients cannot edit dental records")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(record, key, value)

    record.updated_at = datetime.now()
    db.commit()
    db.refresh(record)

    return DentalRecordRead.model_validate(record)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dental_record(
    record_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    record = db.get(DentalRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dental record not found")
    db.delete(record)
    db.commit()


@router.get("/{record_id}/pdf")
def download_dental_record_pdf(
    record_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    record = db.get(DentalRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dental record not found")

    if current_user.role == UserRole.patient and record.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or record.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    patient = db.get(User, record.patient_id)
    dentist = db.get(Dentist, record.dentist_id) if record.dentist_id else None

    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    pdf_bytes = generate_dental_record_pdf(record, patient, dentist)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="dental_record_{record_id[:8]}.pdf"'},
    )