from __future__ import annotations

import time
from typing import Any

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class VisualPipeline:
    def __init__(self) -> None:
        self.settings = get_settings()

    def process_visual(self, image_path: str, question: str, context: str = "") -> dict[str, Any]:
        start = time.perf_counter()

        result = {
            "image_path": image_path,
            "confidence_score": 0.0,
            "ocr_text": "",
            "caption_match": False,
            "visual_type": "unknown",
            "description": "",
        }

        try:
            ocr_text = self._extract_ocr(image_path)
            result["ocr_text"] = ocr_text

            visual_type = self._classify_visual(image_path, ocr_text)
            result["visual_type"] = visual_type

            caption_match = self._check_caption_match(question, ocr_text, context)
            result["caption_match"] = caption_match

            confidence = self._calculate_confidence(ocr_text, question, caption_match, context)
            result["confidence_score"] = confidence

            description = self._generate_description(image_path, ocr_text, visual_type)
            result["description"] = description

        except Exception as exc:
            logger.warning(f"Visual pipeline error: {exc}")
            result["confidence_score"] = 0.0

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(f"Visual pipeline: confidence={result['confidence_score']:.2f} in {duration_ms:.1f}ms")
        return result

    def _extract_ocr(self, image_path: str) -> str:
        try:
            from PIL import Image
            import pytesseract

            if self.settings.tesseract_cmd:
                pytesseract.pytesseract.tesseract_cmd = self.settings.tesseract_cmd

            if image_path.lower().endswith('.pdf'):
                try:
                    from pdf2image import convert_from_path
                    images = convert_from_path(image_path, first_page=1, last_page=1, dpi=300)
                    if images:
                        image = images[0]
                    else:
                        return ""
                except Exception:
                    return ""
            else:
                image = Image.open(image_path)
            text = pytesseract.image_to_string(image, lang=self.settings.ocr_language)
            return text.strip()[:2000]
        except Exception:
            return ""

    def _classify_visual(self, image_path: str, ocr_text: str) -> str:
        lower = ocr_text.lower()

        table_indicators = ["table", "row", "column", "|", "\t"]
        if any(ind in lower for ind in table_indicators) or ocr_text.count("\t") > 3:
            return "table"

        chart_indicators = ["chart", "graph", "percentage", "%", "bar", "pie"]
        if any(ind in lower for ind in chart_indicators):
            return "chart"

        diagram_indicators = ["diagram", "flow", "arrow", "step", "process"]
        if any(ind in lower for ind in diagram_indicators):
            return "diagram"

        figure_indicators = ["figure", "fig", "image", "photo", "x-ray", "radiograph"]
        if any(ind in lower for ind in figure_indicators):
            return "figure"

        return "unknown"

    def _check_caption_match(self, question: str, ocr_text: str, context: str) -> bool:
        question_words = set(question.lower().split())
        ocr_words = set(ocr_text.lower().split())
        context_words = set(context.lower().split())

        all_text_words = ocr_words | context_words
        overlap = len(question_words & all_text_words)
        return overlap >= max(2, len(question_words) * 0.3)

    def _calculate_confidence(self, ocr_text: str, question: str, caption_match: bool, context: str) -> float:
        score = 0.0

        if ocr_text and len(ocr_text) > 20:
            score += 0.3

        if caption_match:
            score += 0.3

        if context and len(context) > 10:
            score += 0.2

        question_words = set(question.lower().split())
        ocr_words = set(ocr_text.lower().split())
        if question_words and ocr_words:
            overlap = len(question_words & ocr_words) / len(question_words)
            score += min(0.2, overlap * 0.2)

        return min(1.0, score)

    def _generate_description(self, image_path: str, ocr_text: str, visual_type: str) -> str:
        if ocr_text:
            return f"{visual_type.title()}: {ocr_text[:300]}"
        return f"Visual content ({visual_type})"


visual_pipeline = VisualPipeline()
