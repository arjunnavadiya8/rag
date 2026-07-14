from fastapi import FastAPI, HTTPException, Form
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from langchain_core.messages import HumanMessage, AIMessage
from app.chain import rag_agent, get_mongodb_history

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

@app.get("/health")
def health_check():
    return {"status": "ok"}
