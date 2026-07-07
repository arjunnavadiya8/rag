import os
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.runnables import RunnablePassthrough
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_mongodb.chat_message_histories import MongoDBChatMessageHistory
from app.config import settings
from operator import itemgetter

def get_mongodb_history(session_id: str) -> MongoDBChatMessageHistory:
    return MongoDBChatMessageHistory(
        session_id=session_id,
        connection_string=settings.mongodb_uri,
        database_name="rag_db",
        collection_name="chat_histories"
    )

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
    You must ONLY use the provided context to answer the question. 
    If the answer cannot be found in the context, you must say "I can only answer questions based on the provided document." Do not use your outside knowledge to answer the question itself.
    
    However, if the user asks about an acronym or abbreviation (like "SVM"), you MAY use your general knowledge to infer what it stands for (e.g., "Support Vector Machine") in order to find the relevant information in the context.
    
    When answering, preserve any formatting, examples, bullet points, and code blocks found in the context. Output your response using proper Markdown.
    
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
        {
            "context": itemgetter("question") | retriever | format_docs, 
            "question": itemgetter("question"), 
            "chat_history": itemgetter("chat_history")
        }
        | qa_prompt
        | llm
        | StrOutputParser()
    )

    # 5. Wrap with Message History
    chain_with_history = RunnableWithMessageHistory(
        rag_chain,
        get_mongodb_history,
        input_messages_key="question",
        history_messages_key="chat_history",
    )

    return chain_with_history

# Singleton instance of the chain
rag_chain_with_history = get_rag_chain()
