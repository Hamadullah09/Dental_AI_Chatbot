# Dental AI Chatbot - RAG Pipeline

## Overview

The Retrieval-Augmented Generation (RAG) pipeline retrieves relevant dental information from uploaded documents and generates accurate, cited responses.

## Pipeline Stages

```
User Query
    ↓
Query Rewriting
    ↓
Hybrid Retrieval
    ├── Vector Search (Qdrant)
    └── Keyword Search (BM25)
    ↓
Merging & Deduplication
    ↓
Relevance Filtering
    ↓
Cross-Encoder Reranking
    ↓
Adjacent Chunk Expansion
    ↓
Context Compression
    ↓
LLM Generation
    ↓
Citation Verification
    ↓
Response Formatting
```

## 1. Query Rewriting

**File**: `app/services/rag.py`

Expands dental terminology for better retrieval:

```python
dental_term_map = {
    r"\btooth\s+ache\b": "dental pain pulpitis",
    r"\bbad\s+breath\b": "halitosis oral odor",
    r"\bhole\s+in\s+tooth\b": "dental caries cavity",
    r"\bgum\s+bleeding\b": "gingival bleeding periodontal",
    r"\bswollen\s+gums\b": "gingival swelling inflammation",
    r"\bloose\s+tooth\b": "tooth mobility periodontal",
    r"\bsensitive\s+teeth\b": "dental sensitivity dentin hypersensitivity",
    r"\byellow\s+teeth\b": "tooth discoloration staining",
    r"\bwisdom\s+tooth\b": "third molar",
    r"\bbraces\b": "orthodontic appliance fixed appliance",
}
```

## 2. Hybrid Retrieval

### Vector Search

**Model**: all-MiniLM-L6-v2 (384 dimensions)

```python
vector = embedding_model.encode([query])[0].tolist()
results = qdrant.search(
    collection_name="dental_chunks",
    query_vector=vector,
    limit=candidate_limit,
    query_filter=build_qdrant_filter(filters)
)
```

**Scoring**: Cosine similarity

### Keyword Search (BM25)

```python
# Qdrant full-text search
results = qdrant.query(
    collection_name="dental_chunks",
    query=query,
    limit=candidate_limit
)
```

**Scoring**: BM25 term frequency

### Merging

```python
merged = merge_chunks(vector_results + keyword_results)
# Deduplicates by chunk text hash
# Combines scores from both methods
```

## 3. Relevance Filtering

```python
def is_relevant_chunk(question: str, chunk: RetrievedChunk, threshold: float) -> bool:
    # Check minimum relevance score
    combined_score = (
        chunk.vector_score * 0.5 +
        chunk.keyword_score * 0.3 +
        chunk.rerank_score * 0.2
    )
    return combined_score >= threshold
```

## 4. Cross-Encoder Reranking

**Model**: BGE-reranker-v2-m3

```python
class CrossEncoderReranker:
    def rerank(self, query: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
        pairs = [(query, chunk.text) for chunk in chunks]
        scores = self.model.predict(pairs)
        
        for chunk, score in zip(chunks, scores):
            chunk.rerank_score = float(score)
        
        return sorted(chunks, key=lambda c: c.rerank_score, reverse=True)
```

## 5. Adjacent Chunk Expansion

Expands context by including neighboring chunks:

```python
def expand_adjacent_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    expanded = list(chunks)
    for chunk in chunks[:3]:
        # Get chunk before
        prev = fetch_chunk_by_position(chunk.document_id, chunk.chunk_index - 1)
        if prev and should_use_chunk(question, prev):
            expanded.append(prev)
        
        # Get chunk after
        next_chunk = fetch_chunk_by_position(chunk.document_id, chunk.chunk_index + 1)
        if next_chunk and should_use_chunk(question, next_chunk):
            expanded.append(next_chunk)
    
    return merge_chunks(expanded)
```

## 6. Context Compression

```python
def compress_context(question: str, text: str) -> str:
    # Remove irrelevant sentences
    # Keep sentences that answer the question
    # Limit to token budget
    sentences = split_sentences(text)
    relevant = [s for s in sentences if is_relevant_to_question(s, question)]
    return " ".join(relevant[:max_sentences])
```

## 7. LLM Generation

**Model**: Qwen2.5-VL:7b (via Ollama)

```python
system_prompt = """You are DentalGPT, an expert dental AI assistant. 
You provide accurate, evidence-based dental information grounded in the provided context. 
Always cite your sources using [Source N] format.
Never provide medical advice that replaces professional dental consultation.
Include the medical disclaimer at the end of every response."""

answer = llm.generate(
    prompt=user_prompt,
    system_prompt=system_prompt,
    context=context_text
)
```

## 8. Citation Verification

```python
def validate_citations(sources: list[SourceCitation]) -> list[SourceCitation]:
    validated = []
    for source in sources:
        if source.document_name and source.document_name != "Unknown":
            validated.append(source)
    return validated
```

## Visual Retrieval

### Visual Pipeline

```python
class VisualPipeline:
    def process_visual(self, image_path: str, question: str) -> dict:
        # 1. Extract OCR text
        ocr_text = extract_ocr(image_path)
        
        # 2. Classify visual type
        visual_type = classify_visual(image_path, ocr_text)
        
        # 3. Check caption match
        caption_match = check_caption_match(question, ocr_text)
        
        # 4. Calculate confidence
        confidence = calculate_confidence(ocr_text, question, caption_match)
        
        # 5. Generate description
        description = generate_description(image_path, ocr_text, visual_type)
        
        return {
            "ocr_text": ocr_text,
            "visual_type": visual_type,
            "caption_match": caption_match,
            "confidence_score": confidence,
            "description": description
        }
```

### Visual Types

- `diagram` - Anatomical diagrams
- `chart` - Charts and graphs
- `xray` - Dental x-rays
- `photo` - Clinical photographs
- `illustration` - Medical illustrations
- `table` - Data tables

## RAG Modes

### Simple Mode
Basic retrieval without enhancements.

### Memory Mode
Includes conversation history in retrieval.

### Multi-Query Mode
Generates multiple query variants and merges results.

### HyDE Mode
Generates hypothetical answer, then retrieves similar content.

### Corrective Mode
Retrieves, evaluates, and retrieves again if needed.

### Self-RAG Mode
Self-reflects on retrieved content before generating.

## Performance Metrics

### Retrieval Metrics

```python
# Precision@k
precision_at_k = relevant_retrieved / total_retrieved

# Recall@k
recall_at_k = relevant_retrieved / total_relevant

# MRR (Mean Reciprocal Rank)
mrr = sum(1/rank for rank in relevant_ranks) / total_queries

# nDCG (Normalized Discounted Cumulative Gain)
ndcg = dcg / ideal_dcg
```

### Generation Metrics

```python
# Faithfulness
faithfulness = supported_claims / total_claims

# Groundedness
groundedness = grounded_sentences / total_sentences

# Citation Accuracy
citation_accuracy = correct_citations / total_citations

# Hallucination Rate
hallucination_rate = hallucinated_claims / total_claims
```

## Configuration

```python
# app/core/config.py

# Retrieval
RETRIEVAL_TOP_K=5
RETRIEVAL_MIN_RELEVANCE_SCORE=0.3
ENABLE_QUERY_REWRITING=true
ENABLE_KEYWORD_SEARCH=true
ENABLE_ADJACENT_CHUNK_EXPANSION=true

# RAG Mode
RAG_MODE=corrective

# Visual RAG
ENABLE_MULTIMODAL_RAG=true
VISUAL_MIN_RELEVANCE_SCORE=0.95
VISUAL_MAX_TO_ANALYZE=2

# Embeddings
EMBEDDING_MODEL_NAME=all-MiniLM-L6-v2
EMBEDDING_DIMENSION=384
```

## Quality Improvements

### Chunk Quality Assessment

```python
def assess_chunk_quality(text: str) -> dict:
    return {
        "length": len(text),
        "has_numbers": bool(re.search(r'\d', text)),
        "has_dental_terms": bool(re.search(r'\b(tooth|gum|dental|oral)\b', text, re.I)),
        "is_form_or_survey": is_form_or_survey_question(text),
        "repeated_lines": count_repeated_lines(text),
    }
```

### Noise Filtering

- Remove repeated headers/footers
- Filter page numbers
- Remove form/survey questions
- Clean OCR artifacts

## Troubleshooting

### Low Retrieval Quality

1. Check embedding model is loaded
2. Verify Qdrant collection exists
3. Test with simple query first
4. Check document was ingested properly

### Slow Retrieval

1. Reduce `RETRIEVAL_TOP_K`
2. Disable `ENABLE_ADJACENT_CHUNK_EXPANSION`
3. Check Qdrant performance
4. Monitor embedding generation time

### Poor Answer Quality

1. Check `RAG_MODE` setting
2. Verify LLM model is loaded
3. Test with different prompts
4. Review retrieved chunks
