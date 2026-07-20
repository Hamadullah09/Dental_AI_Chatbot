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
from app.models import Appointment, AppointmentStatus, Dentist, Prescription, User, UserRole
from app.schemas import (
    PrescriptionCreate,
    PrescriptionRead,
    PrescriptionSearchParams,
    PrescriptionSearchResult,
    PrescriptionUpdate,
)

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])

settings = get_settings()


def generate_prescription_pdf(prescription: Prescription, patient: User, dentist: Dentist) -> bytes:
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
        borderWidth=0,
        borderPadding=0,
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

    clinic_name = dentist.clinic_name or "Dental Clinic"
    elements.append(Paragraph(clinic_name.upper(), title_style))
    elements.append(Paragraph(f"Prescription", subtitle_style))
    elements.append(Spacer(1, 8))

    qr = qrcode.make(f"prescription:{prescription.id}:{prescription.patient_id}:{prescription.dentist_id}")
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
            Paragraph(f"<b>Dentist:</b> Dr. {dentist.full_name}<br/>"
                      f"<b>Specialization:</b> {dentist.specialization.value.replace('_', ' ').title()}<br/>"
                      f"<b>Clinic:</b> {dentist.clinic_name or 'N/A'}", normal_style),
            "",
        ],
        [
            Paragraph(f"<b>Date:</b> {prescription.created_at.strftime('%B %d, %Y')}<br/>"
                      f"<b>Prescription ID:</b> {prescription.id[:8].upper()}", normal_style),
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

    elements.append(Paragraph("Diagnosis", section_style))
    elements.append(Paragraph(prescription.diagnosis, normal_style))
    elements.append(Spacer(1, 6))

    elements.append(Paragraph("Medicines Prescribed", section_style))

    med_lines = prescription.medicines.strip().split("\n")
    dose_lines = prescription.dosage.strip().split("\n")
    freq_lines = prescription.frequency.strip().split("\n")
    dur_lines = prescription.duration.strip().split("\n")

    max_len = max(len(med_lines), len(dose_lines), len(freq_lines), len(dur_lines))

    med_data = [["#", "Medicine", "Dosage", "Frequency", "Duration"]]
    for i in range(max_len):
        med_data.append([
            str(i + 1),
            med_lines[i].strip() if i < len(med_lines) else "",
            dose_lines[i].strip() if i < len(dose_lines) else "",
            freq_lines[i].strip() if i < len(freq_lines) else "",
            dur_lines[i].strip() if i < len(dur_lines) else "",
        ])

    med_table = Table(med_data, colWidths=[10 * mm, 50 * mm, 30 * mm, 40 * mm, 40 * mm])
    med_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3c5e")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cccccc")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f5f5f5")]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(med_table)
    elements.append(Spacer(1, 10))

    if prescription.instructions:
        elements.append(Paragraph("Instructions", section_style))
        elements.append(Paragraph(prescription.instructions, normal_style))
        elements.append(Spacer(1, 6))

    if prescription.notes:
        elements.append(Paragraph("Additional Notes", section_style))
        elements.append(Paragraph(prescription.notes, normal_style))
        elements.append(Spacer(1, 6))

    if prescription.follow_up_date:
        elements.append(Paragraph("Follow-up", section_style))
        elements.append(Paragraph(
            f"Follow-up date: {prescription.follow_up_date.strftime('%B %d, %Y')}",
            normal_style
        ))
        elements.append(Spacer(1, 12))

    elements.append(Spacer(1, 20))

    sig_data = [
        ["_" * 40, "_" * 40],
        ["Dentist Signature", "Date"],
        [f"Dr. {dentist.full_name}", prescription.created_at.strftime("%B %d, %Y")],
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
        "<i>Disclaimer: This prescription is valid only with the dentist's signature and clinic stamp. "
        "Please consult your dentist before making any changes to the medication regimen.</i>",
        ParagraphStyle("Disclaimer", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#888888"))
    )
    elements.append(disclaimer)

    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


@router.get("", response_model=PrescriptionSearchResult)
def search_prescriptions(
    params: PrescriptionSearchParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PrescriptionSearchResult:
    query = db.query(Prescription)

    if current_user.role == UserRole.patient:
        query = query.filter(Prescription.patient_id == current_user.id)
    elif current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if dentist:
            query = query.filter(Prescription.dentist_id == dentist.id)
        else:
            return PrescriptionSearchResult(prescriptions=[], total=0, page=params.page, limit=params.limit, total_pages=0)

    if params.patient_id and current_user.role == UserRole.admin:
        query = query.filter(Prescription.patient_id == params.patient_id)
    if params.dentist_id and current_user.role == UserRole.admin:
        query = query.filter(Prescription.dentist_id == params.dentist_id)

    if params.date_from:
        query = query.filter(Prescription.created_at >= params.date_from)
    if params.date_to:
        query = query.filter(Prescription.created_at <= params.date_to)

    if params.query:
        search = f"%{params.query}%"
        query = query.join(Dentist).join(User).filter(
            or_(
                Prescription.diagnosis.ilike(search),
                Prescription.medicines.ilike(search),
                Dentist.full_name.ilike(search),
                User.full_name.ilike(search),
            )
        )

    total = query.count()
    total_pages = (total + params.limit - 1) // params.limit
    offset = (params.page - 1) * params.limit

    prescriptions = query.order_by(Prescription.created_at.desc()).offset(offset).limit(params.limit).all()

    return PrescriptionSearchResult(
        prescriptions=[PrescriptionRead.from_orm_model(p) for p in prescriptions],
        total=total,
        page=params.page,
        limit=params.limit,
        total_pages=total_pages,
    )


@router.get("/{prescription_id}", response_model=PrescriptionRead)
def get_prescription(
    prescription_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PrescriptionRead:
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if current_user.role == UserRole.patient and prescription.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or prescription.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    return PrescriptionRead.from_orm_model(prescription)


@router.post("", response_model=PrescriptionRead, status_code=status.HTTP_201_CREATED)
def create_prescription(
    payload: PrescriptionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PrescriptionRead:
    if current_user.role not in [UserRole.dentist, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only dentists can create prescriptions")

    appointment = db.get(Appointment, payload.appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    if appointment.status != AppointmentStatus.completed:
        raise HTTPException(status_code=400, detail="Appointment must be completed to create prescription")

    dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
    if not dentist:
        if current_user.role == UserRole.admin and payload.dentist_id:
            dentist = db.get(Dentist, payload.dentist_id)
        else:
            raise HTTPException(status_code=403, detail="Dentist profile not found")

    existing = db.query(Prescription).filter(Prescription.appointment_id == payload.appointment_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Prescription already exists for this appointment")

    prescription = Prescription(
        patient_id=appointment.patient_id,
        dentist_id=dentist.id,
        appointment_id=payload.appointment_id,
        diagnosis=payload.diagnosis,
        medicines=payload.medicines,
        dosage=payload.dosage,
        frequency=payload.frequency,
        duration=payload.duration,
        instructions=payload.instructions,
        notes=payload.notes,
        follow_up_date=payload.follow_up_date,
        attachment_path=",".join(payload.attachments) if payload.attachments else None,
    )
    db.add(prescription)
    db.commit()
    db.refresh(prescription)

    return PrescriptionRead.from_orm_model(prescription)


@router.patch("/{prescription_id}", response_model=PrescriptionRead)
def update_prescription(
    prescription_id: str,
    payload: PrescriptionUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PrescriptionRead:
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or prescription.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    update_data = payload.model_dump(exclude_unset=True)
    if "attachments" in update_data:
        att = update_data.pop("attachments")
        update_data["attachment_path"] = ",".join(att) if att else None
    for key, value in update_data.items():
        setattr(prescription, key, value)

    prescription.updated_at = datetime.now()
    db.commit()
    db.refresh(prescription)

    return PrescriptionRead.from_orm_model(prescription)


@router.delete("/{prescription_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prescription(
    prescription_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")
    db.delete(prescription)
    db.commit()


@router.get("/{prescription_id}/pdf")
def download_prescription_pdf(
    prescription_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    prescription = db.get(Prescription, prescription_id)
    if not prescription:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if current_user.role == UserRole.patient and prescription.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or prescription.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    patient = db.get(User, prescription.patient_id)
    dentist = db.get(Dentist, prescription.dentist_id)

    if not patient or not dentist:
        raise HTTPException(status_code=404, detail="Associated user/dentist not found")

    pdf_bytes = generate_prescription_pdf(prescription, patient, dentist)

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="prescription_{prescription_id[:8]}.pdf"'},
    )


@router.post("/{prescription_id}/reissue", response_model=PrescriptionRead)
def reissue_prescription(
    prescription_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PrescriptionRead:
    original = db.get(Prescription, prescription_id)
    if not original:
        raise HTTPException(status_code=404, detail="Prescription not found")

    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or original.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    new_prescription = Prescription(
        patient_id=original.patient_id,
        dentist_id=original.dentist_id,
        appointment_id=original.appointment_id,
        diagnosis=original.diagnosis,
        medicines=original.medicines,
        dosage=original.dosage,
        frequency=original.frequency,
        duration=original.duration,
        instructions=original.instructions,
        notes=original.notes,
        follow_up_date=original.follow_up_date,
    )
    db.add(new_prescription)
    db.commit()
    db.refresh(new_prescription)

    return PrescriptionRead.from_orm_model(new_prescription)