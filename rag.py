"""Compatibility wrapper for the Dental AI RAG service."""

from app.services.rag import RAGService


def get_rag_response(question: str) -> tuple[str, list[str]]:
    answer, citations = RAGService().answer(question)
    sources = [
        f"{citation.document_name} p.{citation.page_number}"
        if citation.page_number
        else citation.document_name
        for citation in citations
    ]
    return answer, sources


if __name__ == "__main__":
    prompt = input("Ask a dental question: ")
    response, response_sources = get_rag_response(prompt)
    print(response)
    print("Sources:", ", ".join(response_sources))
