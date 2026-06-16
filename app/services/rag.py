from dataclasses import dataclass

from openai import OpenAI
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer

from app.core.config import get_settings
from app.schemas import SourceCitation


@dataclass
class RetrievedChunk:
    text: str
    citation: SourceCitation


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = SentenceTransformer(self.settings.embedding_model_name)
        self.qdrant = QdrantClient(url=self.settings.qdrant_url, api_key=self.settings.qdrant_api_key)
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        vector = self.embedding_model.encode([question])[0].tolist()
        hits = self.qdrant.search(
            collection_name=self.settings.qdrant_collection,
            query_vector=vector,
            limit=top_k or self.settings.retrieval_top_k,
        )
        chunks: list[RetrievedChunk] = []
        for hit in hits:
            payload = hit.payload or {}
            text = str(payload.get("text") or "").strip()
            if not text:
                continue
            chunks.append(
                RetrievedChunk(
                    text=text,
                    citation=SourceCitation(
                        document_id=payload.get("document_id"),
                        document_name=str(payload.get("document_name") or payload.get("source") or "Unknown document"),
                        page_number=payload.get("page_number"),
                        chunk_index=payload.get("chunk_index"),
                        score=float(hit.score) if hit.score is not None else None,
                    ),
                )
            )
        return chunks

    def build_prompt(self, question: str, chunks: list[RetrievedChunk]) -> str:
        context = "\n\n".join(
            f"[{idx}] {chunk.citation.document_name}, page {chunk.citation.page_number}, "
            f"chunk {chunk.citation.chunk_index}\n{chunk.text}"
            for idx, chunk in enumerate(chunks, start=1)
        )
        return (
            "You are Dental AI, a cautious retrieval-augmented dental assistant. "
            "Answer only from the provided dental context. If the context is insufficient, say so. "
            "Do not diagnose, prescribe, or replace a licensed clinician. "
            "Use concise clinical language and mention the relevant source numbers inline.\n\n"
            f"Context:\n{context or 'No relevant context was retrieved.'}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

    def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return (
                "I could not find enough indexed dental source material to answer that reliably. "
                "Please ask an administrator to upload relevant dental PDFs, or consult a licensed dental professional."
            )

        prompt = self.build_prompt(question, chunks)
        if not self.openai_client:
            preview = chunks[0].text[:900].strip()
            return (
                "Based on the retrieved dental reference, here is the most relevant context I found: "
                f"{preview}"
            )

        response = self.openai_client.chat.completions.create(
            model=self.settings.openai_model,
            temperature=0.2,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a dental RAG assistant. Ground every answer in retrieved context and "
                        "include a brief safety caveat when the question asks for care decisions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )
        return response.choices[0].message.content.strip()

    def answer(self, question: str, top_k: int | None = None) -> tuple[str, list[SourceCitation]]:
        chunks = self.retrieve(question, top_k=top_k)
        answer = self.generate_answer(question, chunks)
        citations = [chunk.citation for chunk in chunks]
        return answer, citations
