from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.chain import rag_chain_with_history

app = FastAPI(title="Production RAG API", description="RAG Application with LangChain, FAISS and Redis History")

class ChatRequest(BaseModel):
    session_id: str
    message: str

class ChatResponse(BaseModel):
    response: str

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # Invoke the chain with the message and session id for history
        response = rag_chain_with_history.invoke(
            {"question": request.message},
            config={"configurable": {"session_id": request.session_id}}
        )
        return ChatResponse(response=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
def health_check():
    return {"status": "ok"}
