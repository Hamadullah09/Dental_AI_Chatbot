# Dental AI Chatbot

This repository contains a prototype for a retrieval‑augmented dental chatbot.  It lets dentists, dental students, clinics and hospitals ask questions about oral health and receive answers grounded in authoritative sources such as dental textbooks and clinical guidelines.

## Features

* **Retrieval‑Augmented Generation (RAG)** – queries are embedded and matched against a vector database to provide context to the large language model.
* **FastAPI backend** – provides a `/chat` endpoint and serves a simple chat UI.
* **PDF ingestion** – scripts to extract text from PDF documents, split them into overlapping chunks and store them in Qdrant.
* **Simple frontend** – a browser‑based UI for chatting with the assistant and viewing sources.
* **Extensible** – designed to be extended with user authentication, document uploads, evaluation tools and multimodal models.

## Setup

1. **Clone the repository**

   ```
   git clone https://github.com/Hamadullah09/Dental_AI_Chatbot.git
   cd Dental_AI_Chatbot
   ```

2. **Install dependencies**

   You can install dependencies using pip.  We recommend using a virtual environment.

   ```
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **Configure environment variables**

   Create a `.env` file in the project root with the following keys:

   ```
   QDRANT_URL=http://localhost:6333
   QDRANT_API_KEY=<your qdrant api key or leave blank if not needed>
   QDRANT_COLLECTION=dental_docs
   OPENAI_API_KEY=<your OpenAI API key>
   ```

   The `OPENAI_API_KEY` is used by `rag.py` to call the OpenAI API.  You may replace this with another provider (e.g. Gemini) by modifying `rag.py`.

4. **Add dental documents**

   Place PDF documents containing dental knowledge in the `knowledge_base/` directory.  These might include textbooks, clinical guidelines, drug databases and protocols.

5. **Ingest documents**

   Run the ingestion script to extract and embed the documents.  This will recreate the Qdrant collection and upload all chunks.

   ```
   python ingest.py
   ```

   By default the script uses the `all-MiniLM-L6-v2` model from `sentence-transformers` to generate embeddings.  You can change this in `ingest.py`.

6. **Run the server**

   Start the FastAPI server with uvicorn:

   ```
   uvicorn app.main:app --reload
   ```

   Open your browser at `http://127.0.0.1:8000` to use the chat interface.

## Architecture

The high‑level architecture is as follows:

1. User enters a question in the web UI.
2. The frontend calls the `/chat` endpoint with the question.
3. The backend embeds the query using `sentence-transformers` and searches the Qdrant collection for the most similar document chunks.
4. The retrieved chunks are concatenated into a context string and sent to the LLM via the `openai` package.
5. The LLM generates an answer conditioned on the context.
6. The backend returns the answer and source metadata to the frontend, which displays them to the user.

The code is organized into three main components:

| Path | Purpose |
|-----|---------|
| `app/main.py` | FastAPI app and endpoints |
| `rag.py` | Embedding, vector search and LLM call |
| `ingest.py` | Offline ingestion of PDFs into Qdrant |
| `static/index.html` | Basic chat UI |
| `knowledge_base/` | Place to store PDF documents |
| `docs/Remaining_Work.docx` | A high‑level plan for future work |

## Limitations and Next Steps

This project is a starting point.  It does **not** currently provide authentication, chat history, an upload portal, or evaluation metrics.  It also uses a basic embedding model and the OpenAI API.  For production use you should:

* Add user and admin roles with secure authentication.
* Implement an upload endpoint to ingest documents from the admin panel.
* Integrate a relational database for user sessions and message storage.
* Add evaluation and safety checks using the `llm‑evaluation‑for‑dentistry` toolkit.
* Expand the front‑end into a proper web application with React or Next.js.
* Consider using specialized dental models (e.g. DentalGPT, OralGPT) for multimodal queries.

See `docs/Remaining_Work.docx` for a more detailed list of enhancements.
