from dataclasses import dataclass
import re

from openai import OpenAI
from qdrant_client import QdrantClient

from app.core.config import get_settings
from app.schemas import SourceCitation
from app.services.embeddings import get_embedding_model
from app.services.vector_store import get_qdrant_client


@dataclass
class RetrievedChunk:
    text: str
    citation: SourceCitation


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = get_embedding_model()
        self.qdrant = get_qdrant_client()
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None

    def retrieve(self, question: str, top_k: int | None = None) -> list[RetrievedChunk]:
        vector = self.embedding_model.encode([question])[0].tolist()
        limit = top_k or self.settings.retrieval_top_k
        if hasattr(self.qdrant, "search"):
            hits = self.qdrant.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=vector,
                limit=limit,
            )
        else:
            query_result = self.qdrant.query_points(
                collection_name=self.settings.qdrant_collection,
                query=vector,
                limit=limit,
            )
            hits = query_result.points
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
            return self.generate_extract_answer(question, chunks)

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
        citations = dedupe_citations([chunk.citation for chunk in chunks])
        return answer, citations

    def generate_extract_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        question_l = question.lower()
        context = " ".join(chunk.text for chunk in chunks)
        sentences = split_sentences(context)

        if any(term in question_l for term in ["list", "name", "types", "diseases", "conditions"]):
            items = extract_oral_disease_items(context)
            if items:
                bullets = "\n".join(f"- {item}" for item in items)
                return (
                    "According to the uploaded dental references, important oral diseases and conditions include:\n\n"
                    f"{bullets}\n\n"
                    "This is an educational summary from the retrieved sources, not a diagnosis."
                )

        keywords = question_keywords(question)
        ranked = rank_sentences(sentences, keywords)
        selected = ranked[:4] if ranked else sentences[:3]
        selected = [sentence for sentence in selected if sentence.strip()]
        if not selected:
            return (
                "I found related source material, but it was not clear enough to answer this question directly. "
                "Try asking a more specific dental question."
            )

        answer = " ".join(selected)
        if len(answer) > 1200:
            answer = answer[:1200].rsplit(" ", 1)[0] + "."
        return (
            "Based on the uploaded dental references: "
            f"{answer}\n\n"
            "For personal symptoms or treatment decisions, consult a licensed dental professional."
        )


def split_sentences(text: str) -> list[str]:
    cleaned = " ".join(text.split())
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)
    return [part.strip() for part in parts if len(part.strip()) > 25]


def question_keywords(question: str) -> set[str]:
    stopwords = {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
        "in", "is", "it", "list", "of", "on", "or", "the", "to", "what", "which",
        "with", "about", "tell", "me", "please",
    }
    return {
        token
        for token in re.findall(r"[a-zA-Z][a-zA-Z-]{2,}", question.lower())
        if token not in stopwords
    }


def rank_sentences(sentences: list[str], keywords: set[str]) -> list[str]:
    def score(sentence: str) -> tuple[int, int]:
        sentence_l = sentence.lower()
        matches = sum(1 for keyword in keywords if keyword in sentence_l)
        dental_boost = sum(
            1
            for term in ["oral", "dental", "disease", "caries", "periodontal", "cancer", "teeth", "tooth"]
            if term in sentence_l
        )
        return matches * 3 + dental_boost, -len(sentence)

    return [sentence for sentence in sorted(sentences, key=score, reverse=True) if score(sentence)[0] > 0]


def extract_oral_disease_items(context: str) -> list[str]:
    canonical: list[tuple[str, str]] = [
        (r"untreated caries.*deciduous|untreated caries.*primary", "Untreated caries of deciduous or primary teeth"),
        (r"untreated caries.*permanent", "Untreated caries of permanent teeth"),
        (r"\bdental caries\b|\btooth decay\b", "Dental caries"),
        (r"\bsevere periodontal disease\b", "Severe periodontal disease"),
        (r"\bperiodontal disease\b", "Periodontal disease"),
        (r"\bedentulism\b|\btotal tooth loss\b", "Edentulism or total tooth loss"),
        (r"cancer of the lip and oral cavity", "Cancer of the lip and oral cavity"),
        (r"\boral cancer\b", "Oral cancer"),
        (r"\bnoma\b", "Noma"),
        (r"oral manifestations", "Oral manifestations of systemic or infectious disease"),
        (r"traumatic dental injuries", "Traumatic dental injuries"),
        (r"congenital malformations", "Congenital oral and dental malformations"),
        (r"cleft lip|cleft palate", "Cleft lip and palate"),
    ]
    context_l = context.lower()
    items: list[str] = []
    for pattern, label in canonical:
        if re.search(pattern, context_l) and label not in items:
            items.append(label)
    return items[:10]


def dedupe_citations(citations: list[SourceCitation]) -> list[SourceCitation]:
    seen: set[tuple[str, int | None, int | None]] = set()
    unique: list[SourceCitation] = []
    for citation in citations:
        key = (citation.document_name, citation.page_number, citation.chunk_index)
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation)
    return unique
