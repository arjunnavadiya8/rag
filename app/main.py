from fastapi import FastAPI, Form, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from app.chain import rag_agent, get_mongodb_history, reload_retriever
import shutil, os, tempfile

app = FastAPI(title="Production RAG API", description="RAG Application with LangGraph and MongoDB")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatResponse(BaseModel):
    response: str

@app.post("/chat")
async def chat(
    message: str = Form(..., description="Type your question here"),
    session_id: str = Form("default_session", description="Change this to start a new conversation")
):
    # Load history for this session
    history = get_mongodb_history(session_id)
    
    # Save the new user message to the database immediately
    history.add_user_message(message)
    
    # Construct the input messages for LangGraph (History + New Message)
    messages = history.messages

    async def generate():
        try:
            final_response = ""
            
            # Stream events from LangGraph
            async for event in rag_agent.astream_events(
                {"messages": messages},
                version="v1"
            ):
                kind = event["event"]
                
                # Stream the AI's text response token by token
                if kind == "on_chat_model_stream":
                    chunk = event["data"]["chunk"].content
                    if chunk:
                        if isinstance(chunk, str):
                            final_response += chunk
                            yield chunk.encode("utf-8")
                        elif isinstance(chunk, list):
                            # Sometimes chunks are complex blocks, extract text
                            for block in chunk:
                                if "text" in block:
                                    final_response += block["text"]
                                    yield block["text"].encode("utf-8")
                
                # Stream tool execution notifications
                elif kind == "on_tool_start":
                    tool_name = event["name"]
                    yield f"\n*[System: Using {tool_name}...]*\n\n".encode("utf-8")
                    
            # After the stream finishes, save the final complete AI message to MongoDB
            if final_response:
                history.add_ai_message(final_response)
                
        except Exception as e:
            yield f"\nError: {str(e)}".encode("utf-8")

    return StreamingResponse(generate(), media_type="text/plain")


@app.post("/upload")
async def upload_document(file: UploadFile = File(...)):
    """
    Accepts a PDF or TXT file, chunks it, embeds it, and adds it 
    to the live FAISS index without restarting the server.
    """
    allowed_types = ["application/pdf", "text/plain"]
    filename_lower = file.filename.lower()
    
    if not (filename_lower.endswith(".pdf") or filename_lower.endswith(".txt")):
        raise HTTPException(
            status_code=400,
            detail="Only PDF and TXT files are supported."
        )

    # Write the uploaded file to a temp location
    suffix = ".pdf" if filename_lower.endswith(".pdf") else ".txt"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        shutil.copyfileobj(file.file, tmp)
        tmp_path = tmp.name

    try:
        from langchain_community.document_loaders import PyPDFLoader, TextLoader
        from langchain_text_splitters import RecursiveCharacterTextSplitter
        from langchain_openai import OpenAIEmbeddings
        from langchain_community.vectorstores import FAISS
        from app.config import settings

        # Load the document
        if suffix == ".pdf":
            loader = PyPDFLoader(tmp_path)
        else:
            loader = TextLoader(tmp_path, encoding="utf-8")
        
        documents = loader.load()

        # Add source metadata using the original filename
        for doc in documents:
            doc.metadata["source"] = file.filename

        # Chunk the document
        splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = splitter.split_documents(documents)

        if not chunks:
            raise HTTPException(status_code=400, detail="Could not extract any text from the file.")

        # Embed and add to FAISS index
        embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)

        if os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path):
            vector_store = FAISS.load_local(
                settings.faiss_index_path, embeddings, allow_dangerous_deserialization=True
            )
            vector_store.add_documents(chunks)
        else:
            vector_store = FAISS.from_documents(chunks, embeddings)

        vector_store.save_local(settings.faiss_index_path)

        # IMPORTANT: Hot-reload the retriever in chain.py so new data is immediately available
        reload_retriever()

        return JSONResponse({
            "message": f"Successfully ingested '{file.filename}'",
            "chunks_added": len(chunks),
            "filename": file.filename
        })
    finally:
        os.unlink(tmp_path)


@app.get("/documents")
async def list_documents():
    """Returns the list of unique document sources in the FAISS index."""
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from app.config import settings

    if not (os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path)):
        return JSONResponse({"documents": []})

    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
    vector_store = FAISS.load_local(
        settings.faiss_index_path, embeddings, allow_dangerous_deserialization=True
    )
    
    sources = set()
    for doc_id, doc in vector_store.docstore._dict.items():
        src = doc.metadata.get("source", "Unknown")
        sources.add(src)

    return JSONResponse({"documents": sorted(list(sources))})


@app.get("/health")
def health_check():
    return {"status": "ok"}
