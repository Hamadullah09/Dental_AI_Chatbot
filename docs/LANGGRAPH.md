# Dental AI Chatbot - LangGraph Workflow

## Overview

The LangGraph agent orchestrates the RAG pipeline through a state machine with conditional routing. It handles intent detection, query rewriting, retrieval, evidence evaluation, and response generation.

## Graph Structure

```
                    ┌─────────────────┐
                    │  detect_intent  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │can_answer_direct│
                    └────────┬────────┘
                             │
                ┌────────────┼────────────┐
                │                         │
        ┌───────▼──────┐          ┌───────▼──────┐
        │ generate_    │          │ rewrite_     │
        │ direct_answer│          │ query        │
        └───────┬──────┘          └───────┬──────┘
                │                         │
                │                 ┌───────▼──────┐
                │                 │ retrieve_    │
                │                 │ chunks       │
                │                 └───────┬──────┘
                │                         │
                │                 ┌───────▼──────┐
                │                 │ retrieve_    │
                │                 │ visuals      │
                │                 └───────┬──────┘
                │                         │
                │                 ┌───────▼──────┐
                │                 │ rerank_      │
                │                 │ results      │
                │                 └───────┬──────┘
                │                         │
                │                 ┌───────▼────────┐
                │                 │has_enough_     │
                │                 │evidence        │
                │                 └───────┬────────┘
                │                         │
                │            ┌────────────┼────────────┐
                │            │                         │
                │    ┌───────▼──────┐          ┌───────▼──────┐
                │    │ build_       │          │ search_      │
                │    │ context      │          │ more         │
                │    └───────┬──────┘          └───────┬──────┘
                │            │                         │
                │            │            ┌────────────┼────────────┐
                │            │            │                         │
                │    ┌───────▼──────┐ ┌───▼───────┐        ┌───────▼──────┐
                │    │ generate_    │ │ respond_  │        │              │
                │    │ answer       │ │ with_     │        │              │
                │    └───────┬──────┘ │ uncertain │        │              │
                │            │        └─────┬─────┘        │              │
                │    ┌───────▼──────┐       │              │              │
                │    │ validate_    │       │              │              │
                │    │ citations    │       │              │              │
                │    └───────┬──────┘       │              │              │
                │            │              │              │              │
                └────────────┼──────────────┼──────────────┘              │
                             │              │                             │
                    ┌────────▼──────────────▼────────────┐               │
                    │         format_response            │               │
                    └────────────────┬───────────────────┘               │
                                     │                                   │
                                     └───────────────────────────────────┘
                                              (merge to END)
```

## Node Descriptions

### 1. detect_intent
**File**: `app/agent/nodes/planner.py:40`

Classifies the user query into one of:
- `emergency` - Urgent dental issues (pain, trauma, bleeding)
- `visual` - Questions about images, diagrams, x-rays
- `treatment` - Treatment-related questions
- `symptom` - Symptom-related questions
- `direct` - Simple greetings, definitions
- `general` - Other dental questions

**Logic**: Keyword matching against predefined sets.

### 2. can_answer_directly
**File**: `app/agent/nodes/planner.py:62`

Returns `"yes"` if:
- Intent is `direct`
- Query contains greeting patterns

Returns `"no"` otherwise.

### 3. generate_direct_answer
**File**: `app/agent/nodes/planner.py:74`

Generates a simple response for:
- Greetings: "Hello! I'm DentalGPT..."
- Thanks: "You're welcome!..."
- Goodbye: "Goodbye!..."

### 4. rewrite_query
**File**: `app/agent/nodes/planner.py:173`

Expands dental terms for better retrieval:
- "tooth ache" → "dental pain pulpitis"
- "bad breath" → "halitosis oral odor"
- "hole in tooth" → "dental caries cavity"
- "gum bleeding" → "gingival bleeding periodontal"

**Output**: `rewritten_query`, `query_variants`

### 5. retrieve_chunks
**File**: `app/agent/graph.py:18`

Performs hybrid retrieval:
1. Vector search (Qdrant)
2. Keyword search (BM25)
3. Merge and deduplicate
4. Filter by relevance score

**Output**: `retrieved_chunks`

### 6. retrieve_visuals
**File**: `app/agent/graph.py:58`

Finds related visual content:
1. Uses reranked chunks to find candidate visuals
2. Scores by relevance to query
3. Extracts OCR text and descriptions

**Output**: `retrieved_visuals`, `visual_context`

### 7. rerank_results
**File**: `app/agent/graph.py:133`

Reranks chunks using:
- Vector similarity score (35%)
- Keyword match score (25%)
- Cross-encoder rerank score (40%)

**Output**: `reranked_chunks`, `reranked_visuals`

### 8. has_enough_evidence
**File**: `app/agent/nodes/planner.py:95`

Returns `"yes"` if:
- No chunks retrieved (always try to answer)
- Intent is `emergency`
- At least 2 chunks with score > 0.5
- At least 3 chunks total

Returns `"no"` otherwise.

### 9. search_more
**File**: `app/agent/nodes/planner.py:108`

Retries retrieval with:
- Increased `top_k` (adds 3 per retry)
- Deduplicates against existing chunks
- Updates `retry_count`

**Max retries**: Configurable (default 2)

### 10. build_context
**File**: `app/agent/nodes/planner.py:218`

Assembles context for LLM:
1. Formats chunks with source citations
2. Appends visual context
3. Prepends conversation memory

**Output**: `context_text`

### 11. generate_answer
**File**: `app/agent/graph.py:154`

Generates response using:
1. System prompt with dental expertise instructions
2. User prompt with conversation history
3. Context from retrieval

**Output**: `answer`, `sources`, `visuals`

### 12. validate_citations
**File**: `app/agent/nodes/planner.py:244`

Validates:
- Sources have valid document names
- Sources are not "Unknown"
- Falls back to top chunks if no valid sources

**Output**: `sources` (validated)

### 13. respond_with_uncertainty
**File**: `app/agent/nodes/planner.py:160`

Generates fallback response when evidence is insufficient:
- Acknowledges limitation
- Recommends professional consultation
- Includes medical disclaimer

### 14. format_response
**File**: `app/agent/nodes/planner.py:271`

Final formatting:
- Ensures answer exists
- Adds medical disclaimer
- Sets answer mode

## State Schema

```python
@dataclass
class AgentState:
    # Input
    question: str
    session_id: str
    user_id: str
    user_role: str
    document_id: str | None
    search_web: bool
    top_k: int | None
    filters: dict

    # Processing
    intent: str
    rewritten_query: str
    query_variants: list[str]
    conversation_history: list[dict]
    retry_count: int
    max_retries: int

    # Retrieval
    retrieved_chunks: list[dict]
    retrieved_visuals: list[dict]
    reranked_chunks: list[dict]
    reranked_visuals: list[dict]

    # Context
    context_text: str
    visual_context: str
    memory_context: str

    # Output
    answer: str
    answer_mode: str
    sources: list[SourceCitation]
    visuals: list[VisualCitation]
    disclaimer: str
    error: str | None

    # Traces
    traces: list[dict]
```

## Conditional Edges

### detect_intent → (generate_direct_answer | rewrite_query)
```python
can_answer_directly(state) → "yes" | "no"
```

### rerank_results → (build_context | search_more)
```python
has_enough_evidence(state) → "yes" | "no"
```

### search_more → (build_context | respond_with_uncertainty)
```python
lambda state: "enough" if state.retrieved_chunks and state.retry_count <= state.max_retries else "uncertain"
```

## Tracing

Every node adds a trace entry:
```python
state.add_trace(
    node_name="hybrid_retriever",
    status="completed",
    detail="5 chunks retrieved",
    duration_ms=123.45
)
```

**Available traces**:
- `intent_detector` - Intent classification
- `query_rewriter` - Query expansion
- `hybrid_retriever` - Vector + keyword search
- `visual_retriever` - Visual content retrieval
- `reranker` - Cross-encoder reranking
- `context_builder` - Context assembly
- `llm` - LLM generation
- `citation_validator` - Source validation
- `response_formatter` - Final formatting
- `error_recovery` - Retry logic
- `search_more` - Additional retrieval

## Error Handling

### Retry Logic
```python
if state.error and state.retry_count < state.max_retries:
    state.retry_count += 1
    state.error = None
    # Retry from current node
```

### Fallback Response
When retries exhausted:
```python
state.answer = "I encountered an issue processing your request. Please try again or contact support."
state.answer_mode = "error"
```

### Uncertainty Response
When evidence insufficient:
```python
state.answer = "I don't have sufficient information..."
state.answer_mode = "insufficient_evidence"
```

## Configuration

Key settings in `app/core/config.py`:

```python
enable_query_rewriting: bool = True
enable_keyword_search: bool = True
enable_multimodal_rag: bool = True
enable_adjacent_chunk_expansion: bool = True
retrieval_top_k: int = 5
retrieval_min_relevance_score: float = 0.3
multi_query_max_variants: int = 3
rag_mode: str = "corrective"  # simple | memory | multi_query | hyde | corrective | self_rag
```
