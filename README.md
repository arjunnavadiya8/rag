# Production-Ready Agentic RAG Application

This repository contains a production-ready, strict Retrieval-Augmented Generation (RAG) application built with **FastAPI**, **LangGraph**, **FAISS**, **MongoDB**, and a modern **React (Vite)** frontend.

## Features

### Backend (FastAPI & LangGraph)
- **LangGraph**: Orchestrates the RAG agent using `create_react_agent` with a custom `search_documents` tool.
- **Strict RAG Ingestion & Querying**: The agent is strictly constrained to answer factual questions *only* using the uploaded document context. Factual questions outside the context are politely declined to prevent hallucination.
- **FAISS**: Extremely fast, in-memory vector database used to store and retrieve document embeddings. Indexes are saved locally to disk.
- **MongoDB**: Stores session-based chat histories (`MongoDBChatMessageHistory`), allowing the agent to retain conversational context. The backend handles offline MongoDB states gracefully by falling back to non-persistent chat memory.
- **Dynamic Knowledge Base Management**:
  - `POST /upload`: Upload PDF or TXT files. They are chunked, embedded, and dynamically added to the FAISS index with hot-reloading (no server restart required).
  - `GET /documents`: Lists all unique document sources currently indexed.
  - `DELETE /documents/{filename}`: Removes all chunks of a specific document from the FAISS index and hot-reloads the retriever.
- **LangSmith Tracing**: Integrated observability for debugging the agent's path, tool calls, and LLM responses.

### Frontend (React & Vite)
- **Interactive Chat Interface**: A sleek dark-themed UI that streams agent responses token by token.
- **System Tool Notifications**: Shows live notifications (e.g. `*[System: Using search_documents...]*`) so the user knows exactly when the agent is querying the knowledge base.
- **Chat Session Sidebar**: Support for creating new chats, renaming chats, and deleting chats with local storage persistence.
- **Knowledge Base Panel**: Built-in drag-and-drop zone and file picker for easy file ingestion, along with a list of currently active documents and a button to remove them.

---

## Architecture

1. **Ingestion**: Uploaded documents are parsed (using `PyPDFLoader` for PDFs and `TextLoader` for text files), split into chunks using `RecursiveCharacterTextSplitter`, embedded using OpenAI's embedding model, and saved to the FAISS index folder.
2. **Retrieval**: The `search_documents` tool queries the local FAISS index to fetch the most relevant context chunks based on semantic similarity.
3. **Generation**: The agent combines the user's message and chat history (loaded from MongoDB) and queries OpenAI's `gpt-4o` under strict instructions to rely only on the retrieved context.

---

## Prerequisites

- **Python 3.10+**
- **Node.js** (to run the React frontend)
- **Docker Desktop** (to run the MongoDB container)
- An **OpenAI API Key**
- (Optional) **Tavily API Key** and **LangSmith API Key** for web searches/observability

---

## Getting Started

### 1. Start MongoDB (via Docker)
Spin up the local MongoDB instance using the provided `docker-compose.yml`:
```bash
docker compose up -d
```
*Note: Once started, MongoDB will automatically restart whenever Docker Desktop is running.*

### 2. Environment Setup
Create a `.env` file in the root of the project with the following configuration:
```env
OPENAI_API_KEY=sk-your-openai-key
TAVILY_API_KEY=tvly-your-tavily-key

# Optional LangSmith Tracing
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=lsv2_pt_your-langsmith-key
LANGCHAIN_PROJECT=rag

MONGODB_URI=mongodb://localhost:27017/rag_db
FAISS_INDEX_PATH=./faiss_index
```

### 3. Install & Start Backend
1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows (Powershell)
   .venv\Scripts\activate
   # macOS/Linux
   # source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```
   The backend will be running at `http://127.0.0.1:8000`. You can view the Swagger API docs at `http://127.0.0.1:8000/docs`.

### 4. Install & Start Frontend
1. Navigate to the frontend directory:
   ```bash
   cd frontend
   ```
2. Install Node packages:
   ```bash
   npm install
   ```
3. Start the React development server:
   ```bash
   npm run dev
   ```
   The web application will open at `http://localhost:5173`.

---

## API Endpoints

- `POST /chat` — Stream chat messages and retrieve response.
- `POST /upload` — Upload files (`.pdf`, `.txt`) to the knowledge base.
- `GET /documents` — Retrieve list of unique indexed files.
- `DELETE /documents/{filename}` — Delete all index chunks of a file.
- `GET /health` — Check server health status.

