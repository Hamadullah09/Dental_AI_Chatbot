"""
Offline ingestion script for dental documents.

This script reads all PDF files from the `knowledge_base/` directory, extracts
text, splits it into overlapping chunks, embeds each chunk and uploads it to
Qdrant.  It will recreate the collection each time, so run it cautiously.

Usage:

    python ingest.py

Make sure to set the QDRANT_URL, QDRANT_API_KEY and QDRANT_COLLECTION
environment variables before running.  You should also install the
required dependencies from requirements.txt.
"""

import os
from pathlib import Path
import uuid

from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http import models
from sentence_transformers import SentenceTransformer
from langchain.text_splitter import RecursiveCharacterTextSplitter
from pypdf import PdfReader

# Load environment variables from .env if present
load_dotenv()

QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
QDRANT_COLLECTION = os.getenv("QDRANT_COLLECTION", "dental_docs")

# Directory containing PDF documents
KNOWLEDGE_BASE_DIR = Path("knowledge_base")

# Initialize embedding model and Qdrant client
_embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
_qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract all text from a PDF file."""
    reader = PdfReader(str(pdf_path))
    text = ""
    for page in reader.pages:
        try:
            text += page.extract_text() + "\n"
        except Exception:
            # Skip pages that cannot be parsed
            continue
    return text


def ingest_pdf(pdf_path: Path) -> int:
    """Read a PDF, split into chunks, embed and upload to Qdrant.

    Returns the number of chunks uploaded.
    """
    text = extract_text_from_pdf(pdf_path)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
    )
    chunks = splitter.split_text(text)
    vectors = _embedding_model.encode(chunks)

    operations = []
    for chunk, vector in zip(chunks, vectors):
        payload = {
            "text": chunk,
            "source": pdf_path.name,
        }
        operations.append(
            models.PointStruct(id=str(uuid.uuid4()), vector=vector.tolist(), payload=payload)
        )

    if operations:
        _qdrant_client.upsert(collection_name=QDRANT_COLLECTION, points=operations)

    return len(operations)


def recreate_collection():
    """Create or recreate the Qdrant collection with the correct vector size."""
    vector_size = _embedding_model.get_sentence_embedding_dimension()
    _qdrant_client.recreate_collection(
        collection_name=QDRANT_COLLECTION,
        vectors_config=models.VectorParams(size=vector_size, distance=models.Distance.COSINE),
    )


def main() -> None:
    if not KNOWLEDGE_BASE_DIR.exists():
        raise FileNotFoundError("knowledge_base directory not found.  Create it and add PDF documents.")

    recreate_collection()

    total_chunks = 0
    for pdf in KNOWLEDGE_BASE_DIR.glob("*.pdf"):
        print(f"Ingesting {pdf} ...")
        num_chunks = ingest_pdf(pdf)
        print(f"\tUploaded {num_chunks} chunks from {pdf.name}")
        total_chunks += num_chunks

    print(f"Finished ingesting {total_chunks} chunks across {len(list(KNOWLEDGE_BASE_DIR.glob('*.pdf')))} files.")


if __name__ == "__main__":
    main()
