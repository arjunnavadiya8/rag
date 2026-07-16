import os
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from langgraph.prebuilt import create_react_agent
from langchain_core.tools import tool
from app.config import settings

def get_mongodb_history(session_id: str) -> MongoDBChatMessageHistory:
    return MongoDBChatMessageHistory(
        session_id=session_id,
        connection_string=settings.mongodb_uri,
        database_name="rag_db",
        collection_name="chat_histories"
    )

def _build_retriever():
    """Build a fresh retriever from the FAISS index on disk."""
    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
    if os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path):
        vector_store = FAISS.load_local(
            settings.faiss_index_path,
            embeddings,
            allow_dangerous_deserialization=True
        )
    else:
        vector_store = FAISS.from_texts(["No data ingested yet."], embeddings)
    return vector_store.as_retriever(search_kwargs={"k": 4})

# Module-level retriever (mutable via reload_retriever)
_retriever = _build_retriever()

def reload_retriever():
    """Hot-reloads the retriever after new documents are uploaded."""
    global _retriever
    _retriever = _build_retriever()

def get_rag_agent():
    # 1. Setup LLM
    llm = ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key, streaming=True)

    # 2. Document search tool (always uses the latest _retriever via closure)
    @tool
    def search_documents(query: str) -> str:
        """Searches the uploaded documents for information. Use this to answer questions from the personal knowledge base."""
        docs = _retriever.invoke(query)
        return "\n\n".join([d.page_content for d in docs])

    tools = [search_documents]

    # 3. System Prompt — strictly restrict to personal knowledge base
    system_prompt = """You are a STRICT retrieval-augmented generation assistant.
    You have access to a document search tool that queries the user's personal knowledge base.

    CRITICAL RULES:
    1. You MUST answer questions based ONLY on the information found in the personal knowledge base.
    2. If the user asks ANY factual question (e.g., about people, companies, weather, history, programming) that is NOT explicitly answered in the retrieved documents, you MUST decline to answer. Say: "I can only answer questions based on your personal knowledge base."
    3. Under NO CIRCUMSTANCES should you use your pre-trained general knowledge to answer a question. 
    4. You may respond naturally to basic greetings (like "Hello", "Hi").

    When answering, use proper Markdown formatting.
    """

    agent = create_react_agent(llm, tools=tools, prompt=system_prompt)
    return agent

# Singleton instance of the LangGraph agent
rag_agent = get_rag_agent()
