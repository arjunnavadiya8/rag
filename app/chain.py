import os
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import RedisChatMessageHistory
from app.config import settings

def get_redis_history(session_id: str) -> RedisChatMessageHistory:
    return RedisChatMessageHistory(session_id, url=settings.redis_url)

def get_rag_chain():
    # 1. Setup LLM and Embeddings
    llm = ChatOpenAI(model="gpt-4o", api_key=settings.openai_api_key)
    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)

    # 2. Setup Retriever
    if os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path):
        vector_store = FAISS.load_local(
            settings.faiss_index_path, 
            embeddings, 
            allow_dangerous_deserialization=True
        )
    else:
        # Fallback if no index is present yet
        vector_store = FAISS.from_texts(["No data ingested yet."], embeddings)
        
    retriever = vector_store.as_retriever(search_kwargs={"k": 4})

    # 3. Setup Prompt Template
    qa_system_prompt = """You are an assistant for question-answering tasks. 
    Use the following pieces of retrieved context to answer the question. 
    If you don't know the answer, just say that you don't know. 
    Use three sentences maximum and keep the answer concise.
    
    Context: {context}"""
    
    qa_prompt = ChatPromptTemplate.from_messages([
        ("system", qa_system_prompt),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{question}"),
    ])

    def format_docs(docs):
        return "\n\n".join(doc.page_content for doc in docs)

    # 4. Build the Chain using LCEL
    rag_chain = (
        {"context": retriever | format_docs, "question": RunnablePassthrough(), "chat_history": RunnablePassthrough()}
        | qa_prompt
        | llm
        | StrOutputParser()
    )

    # 5. Wrap with Message History
    chain_with_history = RunnableWithMessageHistory(
        rag_chain,
        get_redis_history,
        input_messages_key="question",
        history_messages_key="chat_history",
    )

    return chain_with_history

# Singleton instance of the chain
rag_chain_with_history = get_rag_chain()
