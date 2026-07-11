# Multimodal RAG

Dental AI supports a multimodal RAG layer that indexes visual evidence from uploaded PDFs alongside text chunks.

## What Is Extracted

During PDF ingestion, the backend can extract:

- Full page snapshots
- Embedded PDF images
- Caption-adjacent figure regions
- Tables detected by `pdfplumber`

Visual assets are saved under:

```text
uploads/extracted_visuals/{document_id}/
```

The FastAPI app serves these files from:

```text
/uploads/extracted_visuals/{document_id}/...
```

## Metadata

Each visual record is stored in `document_visuals` with:

- `visual_id`
- `document_id`
- `document_name`
- `page_number`
- `visual_type`
- `image_path`
- `caption_text`
- `nearby_text`
- `generated_description`
- `related_chunk_ids`
- `quality_score`
- `review_status`
- `qdrant_point_id`

Visuals are embedded using:

```text
caption_text + nearby_text + generated_description
```

Text chunk payloads use:

```text
payload_type="text"
```

Visual payloads use:

```text
payload_type="visual"
```

## Config

```bash
ENABLE_MULTIMODAL_RAG=true
EXTRACTED_VISUALS_DIR=uploads/extracted_visuals
VISUAL_PAGE_SNAPSHOT_ZOOM=1.6
VISUAL_MIN_RELEVANCE_SCORE=0.95
```

Optional dependencies:

```bash
pip install PyMuPDF pdfplumber
```

They are included in `requirements.txt`.

## Retrieval Flow

1. User asks a question.
2. Text RAG retrieves and reranks text chunks.
3. If multimodal RAG is enabled, the backend searches visual embeddings.
4. Visual hits are reranked using:
   - vector score
   - query keyword overlap
   - caption presence
   - quality score
   - whether the visual is on a cited source page
   - whether the user explicitly asks for a figure/table/diagram/image
5. Only relevant visuals are returned.
6. If no relevant visual exists, the response is normal text-only RAG.

## API Response

Chat responses include:

```json
{
  "answer": "...",
  "sources": [...],
  "visuals": [
    {
      "visual_id": "...",
      "document_name": "...",
      "page_number": 12,
      "visual_type": "figure",
      "image_url": "/uploads/extracted_visuals/...png",
      "caption_text": "...",
      "score": 1.23
    }
  ]
}
```

## Scripts

Extract visuals for ready documents:

```bash
python scripts/extract_pdf_visuals.py
```

Extract visuals for one document:

```bash
python scripts/extract_pdf_visuals.py --document-id DOCUMENT_ID
```

Rebuild the visual vector index from existing DB rows:

```bash
python scripts/rebuild_visual_index.py
```

## Notes

- Page snapshots are intentionally indexed with lower priority than captioned figures/tables.
- Figure-region extraction is caption based and conservative; exact figure bounding boxes depend on PDF layout quality.
- Local Qdrant mode can be slow or locked by another running backend process. For large corpora, use Qdrant Docker or Qdrant Cloud.
