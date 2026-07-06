# Production-Ready RAG Application

This repository contains a production-ready Retrieval-Augmented Generation (RAG) application built with **FastAPI**, **LangChain**, **FAISS**, and **Redis**.

## Features

- **FastAPI**: Provides a fast, async web server and automatically generates interactive Swagger documentation.
- **LangChain**: Orchestrates the RAG pipeline utilizing LCEL (LangChain Expression Language).
- **FAISS**: Extremely fast, in-memory vector database used to store and retrieve document embeddings. Indexes are saved locally to disk.
- **Redis**: Stores chat history for each session, allowing the LLM to retain conversational context.
- **Dockerized Redis**: A simple `docker-compose.yml` to spin up your Redis instance locally.

## Architecture

1. **Ingestion**: Documents are loaded, split into chunks using `RecursiveCharacterTextSplitter`, embedded using OpenAI's embedding model, and then stored in a FAISS vector index.
2. **Retrieval**: When a user asks a question, the FAISS retriever finds the most relevant document chunks based on semantic similarity.
3. **Generation**: The retrieved context and the user's chat history (fetched from Redis) are passed to an OpenAI model (`gpt-4o`) to generate a concise and accurate response.

## Prerequisites

- **Python 3.10+**
- **Docker Desktop** (to run the Redis container)
- An **OpenAI API Key**

## Getting Started

### 1. Setup Infrastructure
Start the Redis container used for storing chat history:
```bash
docker-compose up -d
```

### 2. Environment Variables
Create a `.env` file in the root of the project (if not present) and add your OpenAI API key:
```env
OPENAI_API_KEY=sk-your-actual-key-here
REDIS_URL=redis://localhost:6379/0
FAISS_INDEX_PATH=./faiss_index
```

### 3. Install Dependencies
Create a virtual environment and install the required packages:
```bash
python -m venv .venv
# On Windows
.venv\Scripts\activate
# On Mac/Linux
# source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Data Ingestion
Run the ingestion script to create a dummy document, embed it, and build the initial FAISS index:
```bash
python -m app.ingest
```
This script saves the vector store index to the `./faiss_index` directory.

### 5. Start the Server
Start the FastAPI application with auto-reloading:
```bash
uvicorn app.main:app --reload
```

## API Usage

Once the server is running, you can access the interactive API documentation at:
**http://127.0.0.1:8000/docs**

### Chat Endpoint
- **URL**: `/chat`
- **Method**: `POST`
- **Body**:
  ```json
  {
    "session_id": "your-unique-session-id",
    "message": "What is LangChain?"
  }
  ```
Send follow-up questions using the same `session_id` to test the Redis-backed chat memory!
