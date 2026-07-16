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
    # Load history — gracefully skip if MongoDB is offline
    history = None
    messages = []
    try:
        history = get_mongodb_history(session_id)
        history.add_user_message(message)
        messages = history.messages
    except Exception:
        # MongoDB unavailable — proceed without persistent history
        from langchain_core.messages import HumanMessage
        messages = [HumanMessage(content=message)]

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
            if final_response and history:
                try:
                    history.add_ai_message(final_response)
                except Exception:
                    pass  # MongoDB offline — skip saving
                
        except Exception as e:
            yield f"\nError: {str(e)}".encode("utf-8")

    return StreamingResponse(generate(), media_type="text/plain")


class ScrapeRequest(BaseModel):
    url: str
    max_pages: int = 50   # safety cap — crawl at most this many pages
    max_depth: int = 3    # how many link-levels deep to follow

@app.post("/scrape")
async def scrape_url(body: ScrapeRequest):
    """
    Crawls a website starting from the given URL.
    Follows all internal links (same domain) up to max_depth levels deep
    and up to max_pages total pages, then indexes all text into FAISS.
    """
    from urllib.parse import urlparse, urljoin, urldefrag
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from app.config import settings
    import requests
    from bs4 import BeautifulSoup

    start_url = body.url.strip()
    if not start_url.startswith("http://") and not start_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Invalid URL. Must start with http:// or https://")

    parsed_start = urlparse(start_url)
    base_domain = parsed_start.netloc  # e.g. "docs.python.org"

    # BFS queue: (url, depth)
    queue: list[tuple[str, int]] = [(start_url, 0)]
    visited: set[str] = set()
    all_documents: list[Document] = []

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }

    def normalise(url: str) -> str:
        """Strip fragment and trailing slash for deduplication."""
        url, _ = urldefrag(url)
        return url.rstrip("/")

    def is_internal(url: str) -> bool:
        parsed = urlparse(url)
        return parsed.netloc == base_domain or parsed.netloc == ""

    def extract_links(soup: BeautifulSoup, page_url: str) -> list[str]:
        links = []
        for tag in soup.find_all("a", href=True):
            href = tag["href"]
            absolute = urljoin(page_url, href)
            clean = normalise(absolute)
            parsed = urlparse(clean)
            # Only http/https, same domain, no media files
            if parsed.scheme in ("http", "https") and is_internal(clean):
                ext = parsed.path.split(".")[-1].lower() if "." in parsed.path.split("/")[-1] else ""
                if ext not in ("png", "jpg", "jpeg", "gif", "svg", "pdf", "zip", "css", "js"):
                    links.append(clean)
        return links

    errors: list[str] = []

    while queue and len(visited) < body.max_pages:
        current_url, depth = queue.pop(0)
        canonical = normalise(current_url)

        if canonical in visited:
            continue
        visited.add(canonical)

        try:
            resp = requests.get(current_url, headers=headers, timeout=10)
            resp.raise_for_status()
            content_type = resp.headers.get("Content-Type", "")
            if "text/html" not in content_type:
                continue

            soup = BeautifulSoup(resp.text, "lxml")

            # Remove script / style / nav noise
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            if text.strip():
                all_documents.append(Document(
                    page_content=text,
                    metadata={"source": canonical}
                ))

            # Follow links if we haven't hit max depth
            if depth < body.max_depth:
                for link in extract_links(soup, current_url):
                    if normalise(link) not in visited:
                        queue.append((link, depth + 1))

        except Exception as exc:
            errors.append(f"{current_url}: {exc}")
            continue

    if not all_documents:
        raise HTTPException(
            status_code=422,
            detail=f"No readable text found. Errors: {'; '.join(errors[:3])}"
        )

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.split_documents(all_documents)

    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)

    if os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path):
        vector_store = FAISS.load_local(
            settings.faiss_index_path, embeddings, allow_dangerous_deserialization=True
        )
        vector_store.add_documents(chunks)
    else:
        vector_store = FAISS.from_documents(chunks, embeddings)

    vector_store.save_local(settings.faiss_index_path)
    reload_retriever()

    return JSONResponse({
        "message": f"Crawled {len(visited)} page(s) from '{base_domain}' and indexed into knowledge base",
        "chunks_added": len(chunks),
        "pages_crawled": len(visited),
        "source": start_url
    })


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


@app.delete("/documents/{filename:path}")
async def delete_document(filename: str):
    """
    Removes all chunks belonging to the given filename from the FAISS index
    and rebuilds the index without them.
    """
    from langchain_openai import OpenAIEmbeddings
    from langchain_community.vectorstores import FAISS
    from langchain_core.documents import Document
    from app.config import settings

    if not (os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path)):
        raise HTTPException(status_code=404, detail="No knowledge base found.")

    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
    vector_store = FAISS.load_local(
        settings.faiss_index_path, embeddings, allow_dangerous_deserialization=True
    )

    # Collect all chunks NOT belonging to the file we want to delete
    remaining_docs: list[Document] = []
    removed = 0
    for doc_id, doc in vector_store.docstore._dict.items():
        src = doc.metadata.get("source", "")
        if src == filename:
            removed += 1
        else:
            remaining_docs.append(doc)

    if removed == 0:
        raise HTTPException(status_code=404, detail=f"Document '{filename}' not found in the knowledge base.")

    # Rebuild the index from the remaining documents (or wipe it if none left)
    if remaining_docs:
        new_store = FAISS.from_documents(remaining_docs, embeddings)
        new_store.save_local(settings.faiss_index_path)
    else:
        # No documents left — delete the index folder entirely
        import shutil as _shutil
        _shutil.rmtree(settings.faiss_index_path)

    # Hot-reload so the agent immediately reflects the change
    reload_retriever()

    return JSONResponse({
        "message": f"Removed '{filename}' from the knowledge base.",
        "chunks_removed": removed,
        "documents_remaining": len(set(d.metadata.get("source", "") for d in remaining_docs))
    })


@app.get("/health")
def health_check():
    return {"status": "ok"}
