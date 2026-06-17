from pathlib import Path

from reportlab.pdfgen import canvas

from app.services.ingestion import IngestionService, clean_pdf_text


def test_parse_pdf_keeps_page_and_chunk_metadata(tmp_path: Path, monkeypatch):
    pdf_path = tmp_path / "sample.pdf"
    pdf = canvas.Canvas(str(pdf_path))
    pdf.drawString(72, 720, "Fluoride toothpaste helps prevent dental caries.")
    pdf.showPage()
    pdf.drawString(72, 720, "Periodontal charting records probing depths.")
    pdf.save()

    service = object.__new__(IngestionService)
    from app.core.config import get_settings

    service.settings = get_settings()
    service.settings.chunk_size = 120
    service.settings.chunk_overlap = 10

    chunks = service.parse_pdf(pdf_path)

    assert len(chunks) >= 2
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert chunks[0].chunk_index == 0


def test_clean_pdf_text_removes_form_artifacts():
    cleaned = clean_pdf_text("/H17040\nPut a tick/cross\nHow often do you clean your teeth?\nDental caries is preventable.")

    assert "/H17040" not in cleaned
    assert "tick/cross" not in cleaned
    assert "How often do you clean your teeth" not in cleaned
    assert "Dental caries is preventable" in cleaned
