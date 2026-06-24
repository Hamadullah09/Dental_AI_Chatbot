from dataclasses import dataclass
import re

from openai import OpenAI, OpenAIError
from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.schemas import SourceCitation
from app.services.chunk_quality import assess_chunk_quality, is_form_or_survey_question
from app.services.embeddings import get_embedding_model
from app.services.vector_store import get_qdrant_client
from app.services.web_search import WebSearchResult, WebSearchService


@dataclass
class RetrievedChunk:
    text: str
    citation: SourceCitation
    metadata: dict
    vector_score: float = 0.0
    keyword_score: float = 0.0
    rerank_score: float = 0.0


class RAGService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.embedding_model = get_embedding_model()
        self.qdrant = get_qdrant_client()
        self.openai_client = OpenAI(api_key=self.settings.openai_api_key) if self.settings.openai_api_key else None
        self.web_search = WebSearchService()

    def retrieve(self, question: str, top_k: int | None = None, filters: dict | None = None) -> list[RetrievedChunk]:
        vector = self.embedding_model.encode([question])[0].tolist()
        final_limit = top_k or self.settings.retrieval_top_k
        candidate_limit = max(20, final_limit * 4)
        query_filter = build_qdrant_filter(filters or {})
        allow_noisy = bool((filters or {}).get("include_noisy")) or is_form_or_survey_question(question)

        vector_chunks = self.vector_search(vector, candidate_limit, query_filter)
        keyword_chunks = self.keyword_search(question, candidate_limit, filters or {})
        merged = filter_chunks_for_question(question, merge_chunks(vector_chunks + keyword_chunks), allow_noisy=allow_noisy)
        if not merged and filters and not filters.get("document_id"):
            vector_chunks = self.vector_search(vector, candidate_limit, None)
            keyword_chunks = self.keyword_search(question, candidate_limit, {})
            merged = filter_chunks_for_question(question, merge_chunks(vector_chunks + keyword_chunks), allow_noisy=allow_noisy)
        reranked = rerank_chunks(question, merged)
        compressed = [
            RetrievedChunk(
                text=compress_context(question, chunk.text),
                citation=chunk.citation,
                metadata=chunk.metadata,
                vector_score=chunk.vector_score,
                keyword_score=chunk.keyword_score,
                rerank_score=chunk.rerank_score,
            )
            for chunk in reranked[:final_limit]
        ]
        return compressed

    def vector_search(
        self,
        vector: list[float],
        limit: int,
        query_filter: qmodels.Filter | None,
    ) -> list[RetrievedChunk]:
        if hasattr(self.qdrant, "search"):
            hits = self.qdrant.search(
                collection_name=self.settings.qdrant_collection,
                query_vector=vector,
                limit=limit,
                query_filter=query_filter,
            )
        else:
            query_result = self.qdrant.query_points(
                collection_name=self.settings.qdrant_collection,
                query=vector,
                limit=limit,
                query_filter=query_filter,
            )
            hits = query_result.points
        return [self.hit_to_chunk(hit, vector_score=float(hit.score or 0.0)) for hit in hits]

    def keyword_search(self, question: str, limit: int, filters: dict) -> list[RetrievedChunk]:
        terms = question_keywords(question)
        if not terms:
            return []

        chunks: list[RetrievedChunk] = []
        offset = None
        scanned = 0
        while scanned < 5000:
            records, offset = self.qdrant.scroll(
                collection_name=self.settings.qdrant_collection,
                scroll_filter=build_qdrant_filter(filters),
                limit=256,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            if not records:
                break
            scanned += len(records)
            for record in records:
                payload = record.payload or {}
                text = str(payload.get("text") or "")
                score = keyword_score(text, terms)
                if score <= 0:
                    continue
                chunks.append(self.payload_to_chunk(payload, keyword_score=score))
            if offset is None:
                break
        return sorted(chunks, key=lambda chunk: chunk.keyword_score, reverse=True)[:limit]

    def hit_to_chunk(self, hit, vector_score: float = 0.0) -> RetrievedChunk:
        return self.payload_to_chunk(hit.payload or {}, vector_score=vector_score)

    def payload_to_chunk(
        self,
        payload: dict,
        vector_score: float = 0.0,
        keyword_score: float = 0.0,
    ) -> RetrievedChunk:
        text = str(payload.get("text") or "").strip()
        quality = assess_chunk_quality(text)
        payload = {
            **payload,
            "chunk_id": payload.get("chunk_id") or payload.get("qdrant_point_id"),
            "quality_score": float(payload.get("quality_score", quality.quality_score) or 0.0),
            "is_noisy": bool(payload.get("is_noisy", quality.is_noisy)),
            "noise_reasons": payload.get("noise_reasons") or quality.noise_reasons,
        }
        return RetrievedChunk(
            text=text,
            citation=SourceCitation(
                document_id=payload.get("document_id"),
                document_name=str(
                    payload.get("book_title")
                    or payload.get("title")
                    or payload.get("document_name")
                    or payload.get("source")
                    or "Unknown document"
                ),
                page_number=payload.get("page_number"),
                chunk_index=payload.get("chunk_index"),
                score=vector_score or keyword_score or None,
            ),
            metadata=payload,
            vector_score=vector_score,
            keyword_score=keyword_score,
        )

    def build_prompt(self, question: str, chunks: list[RetrievedChunk]) -> str:
        context = "\n\n".join(
            f"[{idx}] {chunk.citation.document_name}, page {chunk.citation.page_number}, "
            f"chunk {chunk.citation.chunk_index}\n{chunk.text}"
            for idx, chunk in enumerate(chunks, start=1)
        )
        return (
            "You are a safe dental assistant. Answer only from the provided evidence. "
            "Use only context that directly answers the user's question. Do not dump raw chunk text. "
            "Ignore irrelevant survey, questionnaire, tick/cross, form, index, bibliography, or table-artifact content unless the user specifically asks about those forms. "
            "Do not diagnose. Do not prescribe medicines. "
            "If evidence is weak or insufficient, say: I do not have enough relevant evidence in the uploaded documents. "
            "For severe pain, swelling, fever, pus, trauma, or bleeding, recommend urgent dental care. "
            "Always include citations with document name and page number.\n\n"
            f"Context:\n{context or 'No relevant context was retrieved.'}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )

    def generate_answer(self, question: str, chunks: list[RetrievedChunk]) -> str:
        if not chunks:
            return (
                "I do not have enough relevant evidence in the uploaded documents to answer that reliably. "
                "For symptoms or treatment decisions, please consult a licensed dental professional."
            )

        prompt = self.build_prompt(question, chunks)
        if not self.openai_client:
            return self.generate_extract_answer(question, chunks)

        try:
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
        except OpenAIError:
            return self.generate_extract_answer(question, chunks)

    def generate_hybrid_answer(
        self,
        question: str,
        chunks: list[RetrievedChunk],
        web_results: list[WebSearchResult],
    ) -> str:
        if not web_results:
            return (
                "I could not find enough trusted web evidence for that question right now. "
                "Please try again later or ask using the uploaded PDF sources."
            )
        if not self.openai_client:
            bullets = "\n".join(f"- {result.title}: {result.content[:280]}" for result in web_results[:3])
            return (
                "Trusted web sources found the following relevant information:\n\n"
                f"{bullets}\n\n"
                "Please verify the linked sources before using this for clinical decisions."
            )

        pdf_context = "\n\n".join(
            f"[PDF {idx}] {chunk.citation.document_name}, page {chunk.citation.page_number}\n{chunk.text}"
            for idx, chunk in enumerate(chunks[:3], start=1)
        )
        web_context = "\n\n".join(
            f"[WEB {idx}] {result.title}\nURL: {result.url}\n{result.content}"
            for idx, result in enumerate(web_results, start=1)
        )
        prompt = (
            "Answer the dental question using only the provided PDF and trusted web evidence. "
            "Prefer uploaded PDFs for stable textbook knowledge, and use web evidence for current/latest information. "
            "Do not diagnose or prescribe. If evidence is insufficient, say so. Include concise citations by source name.\n\n"
            f"PDF evidence:\n{pdf_context or 'No strong PDF evidence.'}\n\n"
            f"Trusted web evidence:\n{web_context}\n\n"
            f"Question: {question}\n\n"
            "Answer:"
        )
        try:
            response = self.openai_client.chat.completions.create(
                model=self.settings.openai_model,
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a safe dental assistant using trusted sources and clear citations.",
                    },
                    {"role": "user", "content": prompt},
                ],
            )
            return response.choices[0].message.content.strip()
        except OpenAIError:
            return self.generate_extract_answer(question, chunks)

    def answer(
        self,
        question: str,
        top_k: int | None = None,
        filters: dict | None = None,
    ) -> tuple[str, list[SourceCitation]]:
        conversational_answer = answer_conversational_prompt(question)
        if conversational_answer:
            return conversational_answer, []

        definition_answer = answer_basic_dental_definition(question)
        if definition_answer:
            return definition_answer, []

        filters = filters or {}
        try:
            chunks = self.retrieve(question, top_k=top_k, filters=filters)
        except Exception:
            chunks = []
        local_answer = self.generate_answer(question, chunks)
        wants_web = bool(filters.get("search_web"))
        local_is_weak = is_insufficient_answer(local_answer)

        if wants_web:
            try:
                web_results = self.web_search.search(question) if self.web_search.is_configured else []
            except Exception as exc:
                return (
                    f"Web search could not run right now: {exc} "
                    "I can still answer from uploaded PDFs when relevant evidence is available."
                ), []
            if web_results:
                answer = self.generate_hybrid_answer(question, chunks, web_results)
                citations = dedupe_citations([chunk.citation for chunk in chunks[:3]])
                citations.extend(result.to_citation() for result in web_results)
                return answer, citations
            if wants_web and not self.web_search.is_configured:
                return (
                    "Web search is not configured yet. Add a Google, Tavily, or Brave Search API key to enable trusted online browsing. "
                    "I can still answer from uploaded PDFs when relevant evidence is available."
                ), []

        if local_is_weak:
            return local_answer, []
        answer = local_answer
        if is_insufficient_answer(answer):
            return answer, []
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

        code_answer = extract_code_answer(question, context)
        if code_answer:
            return (
                "Based on the uploaded dental references: "
                f"{code_answer}\n\n"
                "Please verify the cited source page before using this for clinical or academic work."
            )

        keywords = question_keywords(question)
        ranked = rank_sentences(sentences, keywords)
        selected = ranked[:4] if ranked else sentences[:3]
        selected = [sentence for sentence in selected if sentence.strip()]
        if not selected:
            return (
                "I do not have enough relevant evidence in the uploaded documents to answer that directly. "
                "For symptoms or treatment decisions, please consult a licensed dental professional."
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
    cleaned = clean_context_text(text)
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9])", cleaned)
    return [part.strip() for part in parts if len(part.strip()) > 25]


def answer_conversational_prompt(question: str) -> str | None:
    normalized = re.sub(r"[^a-zA-Z0-9\s?]", " ", question.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)

    greetings = {
        "hi", "hello", "hey", "hy", "salam", "assalam o alaikum",
        "assalamualaikum", "aoa", "good morning", "good evening",
    }
    if normalized in greetings:
        return (
            "Hi, I am Dental AI. I can help answer dental questions using the PDFs uploaded by the admin. "
            "You can ask about oral diseases, tooth decay, gum disease, prevention, symptoms, or dental care guidance."
        )

    if normalized in {"who are you", "what are you", "ap kon ho", "tum kon ho"}:
        return (
            "I am Dental AI, a retrieval-based dental assistant. I use uploaded dental reference PDFs to give grounded, cited answers. "
            "I can support learning and general dental guidance, but I do not replace a licensed dentist."
        )

    if any(phrase in normalized for phrase in ["what can you do", "help me", "how can you help", "kia kar sakte"]):
        return (
            "I can help with dental topics such as oral diseases, dental caries, periodontal disease, oral hygiene, prevention, "
            "and questions from uploaded dental guidelines. Ask a specific question like: 'What are symptoms of periodontal disease?'"
        )

    symptom_terms = ["pain", "dard", "bleeding", "swelling", "soojan", "toothache", "sensitivity", "infection"]
    personal_terms = ["my", "meri", "mera", "mujhe", "mere", "i have", "i feel"]
    if any(term in normalized for term in symptom_terms) and any(term in normalized for term in personal_terms):
        return (
            "I can give general dental guidance, but I cannot diagnose you personally online. "
            "Please tell me: where is the problem, how long it has been happening, pain level, swelling/fever, bleeding, "
            "and whether there was injury or recent dental treatment. If you have facial swelling, fever, pus, trouble swallowing, "
            "or severe pain, contact a dentist or emergency service urgently."
        )

    small_talk = {"thanks", "thank you", "ok", "okay", "shukriya", "jazakallah"}
    if normalized in small_talk:
        return "You are welcome. Ask me any dental question when you are ready."

    return None


def answer_basic_dental_definition(question: str) -> str | None:
    normalized = re.sub(r"[^a-zA-Z0-9\s?]", " ", question.lower()).strip()
    normalized = re.sub(r"\s+", " ", normalized)
    definition_patterns = ("what is", "define", "meaning of", "what do you mean by")
    if not any(normalized.startswith(pattern) for pattern in definition_patterns):
        return None

    if "oral health" in normalized:
        return (
            "Oral health means the health of the mouth, teeth, gums, and related oral tissues. "
            "It includes being free from problems such as tooth decay, gum disease, oral infections, pain, sores, "
            "and conditions that affect eating, speaking, smiling, or quality of life.\n\n"
            "Good oral health is supported by brushing with fluoride toothpaste, cleaning between teeth, limiting sugary foods and drinks, "
            "avoiding tobacco, and getting regular dental checkups."
        )
    return None


def is_insufficient_answer(answer: str) -> bool:
    normalized = answer.lower()
    return "i do not have enough relevant evidence" in normalized or "no relevant context was retrieved" in normalized


def is_current_info_question(question: str) -> bool:
    normalized = question.lower()
    triggers = [
        "latest", "current", "recent", "new guideline", "updated guideline",
        "2025", "2026", "today", "now", "new research", "official guideline",
        "recent study", "current recommendation",
    ]
    return any(trigger in normalized for trigger in triggers)


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


def build_qdrant_filter(filters: dict | None) -> qmodels.Filter | None:
    if not filters:
        return None

    must: list = []

    review_status = filters.get("review_status")
    if review_status:
        must.append(qmodels.FieldCondition(key="review_status", match=qmodels.MatchValue(value=review_status)))

    trust_levels = filters.get("trust_levels") or default_trust_levels(filters.get("user_role"))
    if trust_levels:
        must.append(qmodels.FieldCondition(key="trust_level", match=qmodels.MatchAny(any=trust_levels)))

    document_types = filters.get("document_types") or default_document_types(filters.get("user_role"))
    if document_types:
        must.append(qmodels.FieldCondition(key="document_type", match=qmodels.MatchAny(any=document_types)))

    min_year = filters.get("min_year")
    if min_year:
        must.append(qmodels.FieldCondition(key="year", range=qmodels.Range(gte=float(min_year))))

    document_id = filters.get("document_id")
    if document_id:
        must.append(qmodels.FieldCondition(key="document_id", match=qmodels.MatchValue(value=document_id)))

    if not must:
        return None
    return qmodels.Filter(must=must)


def default_trust_levels(user_role: str | None) -> list[str]:
    if user_role == "patient":
        return ["high", "medium"]
    return ["high", "medium"]


def default_document_types(user_role: str | None) -> list[str]:
    if user_role == "patient":
        return ["guideline", "patient_education", "textbook"]
    return ["guideline", "textbook", "patient_education", "research_article"]


def keyword_score(text: str, terms: set[str]) -> float:
    text_l = text.lower()
    score = 0.0
    for term in terms:
        occurrences = text_l.count(term)
        if occurrences:
            score += 1.0 + min(occurrences, 5) * 0.25
    phrase = " ".join(sorted(terms))
    if len(phrase) > 4 and phrase in text_l:
        score += 3.0
    return score


def merge_chunks(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    merged: dict[tuple[str, int | None, int | None], RetrievedChunk] = {}
    for chunk in chunks:
        key = (
            chunk.citation.document_id or chunk.citation.document_name,
            chunk.citation.page_number,
            chunk.citation.chunk_index,
        )
        existing = merged.get(key)
        if not existing:
            merged[key] = chunk
            continue
        existing.vector_score = max(existing.vector_score, chunk.vector_score)
        existing.keyword_score = max(existing.keyword_score, chunk.keyword_score)
        existing.citation.score = max(existing.vector_score, existing.keyword_score)
    return list(merged.values())


def rerank_chunks(question: str, chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    terms = question_keywords(question)
    for chunk in chunks:
        trust_boost = {"high": 0.25, "medium": 0.1, "low": -0.25}.get(str(chunk.metadata.get("trust_level")), 0.0)
        review_boost = 0.2 if chunk.metadata.get("review_status") == "approved" else -0.2
        quality_score = float(chunk.metadata.get("quality_score", 1.0) or 0.0)
        quality_boost = (quality_score - 0.6) * 0.5
        lexical = keyword_score(chunk.text, terms)
        noise_penalty = -1.0 if chunk.metadata.get("is_noisy") else 0.0
        chunk.rerank_score = (
            chunk.vector_score
            + (chunk.keyword_score * 0.35)
            + (lexical * 0.2)
            + trust_boost
            + review_boost
            + quality_boost
            + noise_penalty
        )
        chunk.citation.score = chunk.rerank_score
    return sorted(chunks, key=lambda item: item.rerank_score, reverse=True)


def filter_chunks_for_question(question: str, chunks: list[RetrievedChunk], allow_noisy: bool = False) -> list[RetrievedChunk]:
    return [chunk for chunk in chunks if should_use_chunk(question, chunk, allow_noisy=allow_noisy)]


def should_use_chunk(question: str, chunk: RetrievedChunk, allow_noisy: bool = False) -> bool:
    quality = assess_chunk_quality(chunk.text)
    metadata_noisy = bool(chunk.metadata.get("is_noisy", quality.is_noisy))
    quality_score = float(chunk.metadata.get("quality_score", quality.quality_score) or 0.0)
    reasons = chunk.metadata.get("noise_reasons") or quality.noise_reasons
    if isinstance(reasons, str):
        reasons_l = reasons.lower()
    else:
        reasons_l = " ".join(str(reason).lower() for reason in reasons)

    if allow_noisy:
        return quality_score >= 0.1

    if metadata_noisy or quality_score < 0.6:
        return False
    if any(term in reasons_l for term in ["questionnaire", "form", "h17040", "reference_index", "bibliography"]):
        return False
    if is_form_or_survey_question(chunk.text) and not is_form_or_survey_question(question):
        return False
    return True


def compress_context(question: str, text: str) -> str:
    terms = question_keywords(question)
    cleaned = clean_context_text(text)
    sentences = split_sentences(cleaned)
    if not sentences:
        return cleaned[:900]
    ranked = rank_sentences(sentences, terms)
    selected = ranked[:5] if ranked else sentences[:3]
    compressed = " ".join(selected).strip()
    if len(compressed) > 1000:
        compressed = compressed[:1000].rsplit(" ", 1)[0] + "."
    return compressed or cleaned[:900]


def clean_context_text(text: str) -> str:
    cleaned = re.sub(r"BM\.indd\s+\d+\s+\d+/\d+/\d+\s+\d+:\d+:\d+\s+[AP]M", " ", text)
    cleaned = re.sub(r"\bPlate\s+\d+\b", " ", cleaned)
    cleaned = re.sub(r"\bAnnex\s+\d+\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def extract_code_answer(question: str, context: str) -> str | None:
    match = re.search(r"\bcode\s+([a-z0-9]+)\b", question.lower())
    if not match:
        return None
    code = re.escape(match.group(1))
    cleaned = clean_context_text(context)
    patterns = [
        rf"Code\s+{code}\s*:\s*([^.;]+)",
        rf"Code\s+{code}\s+and\s+code\s+[a-z0-9]+\s*:\s*([^.;]+)",
        rf"Code\s+[a-z0-9]+\s+and\s+code\s+{code}\s*:\s*([^.;]+)",
    ]
    findings: list[str] = []
    for pattern in patterns:
        for found in re.findall(pattern, cleaned, flags=re.IGNORECASE):
            finding = found.strip(" ,:-")
            if finding and finding.lower() not in {item.lower() for item in findings}:
                findings.append(finding)
    if not findings:
        return None
    bullets = "\n".join(f"- Code {match.group(1).upper()}: {finding}" for finding in findings[:5])
    return f"The retrieved evidence mentions:\n\n{bullets}"


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
