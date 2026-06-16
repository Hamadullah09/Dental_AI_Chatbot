"""
Retrieval‑augmented generation utilities for the dental chatbot.

This module handles embedding queries and documents, searching a Qdrant collection
for relevant context, and calling the large language model to produce an answer.

Environment variables:
    QDRANT_URL: Base URL of the Qdrant server (e.g. http://localhost:6333)
    QDRANT_API_KEY: API key for Qdrant (optional if not using authentication)
    QDRANT_COLLECTION: Name of the collection to search (default: dental_docs)
    OPENAI_API_KEY: API key for the OpenAI service

To use a different LLM provider, replace the call_llm function below.
"""

import os
from typing import List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.http import models

# Optional import; if you prefer another provider, modify call_llm accordingly
import openai

# Load configuration from environment
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "dental_docs")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Initialize embedding model
_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")

# Initialize Qdrant client
_qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)


def embed_text(text: str) -> np.ndarray:
    """Return the embedding vector for a given text."""
    return _embedding_model.encode([text])[0]


def search_documents(query: str, limit: int = 4) -> List[models.ScoredPoint]:
    """Search the Qdrant collection for documents similar to the query.

    Args:
        query: The user question as plain text.
        limit: Number of documents to retrieve.

    Returns:
        A list of scored points containing payloads with text and source metadata.
    """
    vector = embed_text(query)
    results = _qdrant_client.search(
        collection_name=QDRANT_COLLECTION,
        query_vector=vector.tolist(),
        limit=limit,
    )
    return results


def call_llm(prompt: str) -> str:
    """Send a prompt to the language model and return the generated text.

    By default this calls the OpenAI ChatCompletion API.  To use a different
    provider (e.g. Gemini), replace this function with the appropriate API calls.

    Args:
        prompt: The full prompt containing context and question.

    Returns:
        The assistant's answer as a string.
    """
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is not set.  Please add it to your environment.")
    openai.api_key = OPENAI_API_KEY
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful dental assistant.  Use the context provided to answer questions and cite your sources."},
            {"role": "user", "content": prompt},
        ],
        temperature=0.2,
    )
    return response["choices"][0]["message"]["content"].strip()


def get_rag_response(question: str) -> Tuple[str, List[str]]:
    """Generate an answer and sources for a user question.

    This function embeds the question, searches for relevant document chunks,
    concatenates the context, builds a prompt and calls the LLM.  It returns
    the answer and a list of source identifiers.

    Args:
        question: The user question as plain text.

    Returns:
        A tuple containing the answer and a list of source strings.
    """
    hits = search_documents(question, limit=4)
    contexts: List[str] = []
    sources: List[str] = []

    for hit in hits:
        payload = hit.payload or {}
        text = payload.get("text")
        source = payload.get("source")
        if text:
            contexts.append(text)
        if source:
            sources.append(source)

    # Build the prompt for the language model
    context_str = "\n\n".join(contexts)
    prompt = (
        "You are an AI dental assistant.  Use the context provided to answer the question. "
        "If the context does not include enough information, respond with a polite disclaimer.\n\n"
        f"Context:\n{context_str}\n\n"
        f"Question: {question}\n\n"
        "Answer:"
    )

    answer = call_llm(prompt)

    return answer, sources
