from fastapi import FastAPI, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.chain import rag_chain_with_history

app = FastAPI(title="Production RAG API", description="RAG Application with LangChain, FAISS and Redis History")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatResponse(BaseModel):
    response: str


@app.post("/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(..., description="Type your question here"),
    session_id: str = Form("default_session", description="Change this to start a new conversation")
):
    try:
        # Invoke the chain with the message and session id for history
        response = rag_chain_with_history.invoke(
            {"question": message},
            config={"configurable": {"session_id": session_id}}
        )
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}
