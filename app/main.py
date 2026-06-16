from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path

# Import RAG function from local module
from rag import get_rag_response

app = FastAPI()

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    question: str

class ChatResponse(BaseModel):
    answer: str
    sources: list[str]

@app.get("/")
async def root():
    """Serve the basic HTML front‑end or a placeholder message."""
    index_path = Path(__file__).parent.parent / "static" / "index.html"
    if index_path.exists():
        return Response(content=index_path.read_text(), media_type="text/html")
    return {"message": "Dental AI Chatbot"}

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest):
    """Handle chat requests by retrieving context and generating an answer."""
    if not req.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        answer, sources = get_rag_response(req.question)
        return ChatResponse(answer=answer, sources=sources)
    except Exception as exc:
        # Surface the error to the client; in production you should log this
        raise HTTPException(status_code=500, detail=str(exc))
