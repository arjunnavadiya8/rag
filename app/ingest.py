import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from app.config import settings

def ingest_data(file_path: str):
    """
    Load data from a text file, chunk it, embed it, and save the FAISS index.
    """
    print(f"Loading document: {file_path}")
    loader = TextLoader(file_path)
    documents = loader.load()

    print("Splitting text into chunks...")
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    docs = text_splitter.split_documents(documents)

    print("Generating embeddings and building FAISS index...")
    embeddings = OpenAIEmbeddings(api_key=settings.openai_api_key)
    
    # If index already exists, load it and add to it, else create a new one
    if os.path.exists(settings.faiss_index_path) and os.path.isdir(settings.faiss_index_path):
        vector_store = FAISS.load_local(settings.faiss_index_path, embeddings, allow_dangerous_deserialization=True)
        vector_store.add_documents(docs)
    else:
        vector_store = FAISS.from_documents(docs, embeddings)
        
    print(f"Saving FAISS index to {settings.faiss_index_path}...")
    vector_store.save_local(settings.faiss_index_path)
    print("Ingestion complete.")

if __name__ == "__main__":
    # Example usage: create a dummy file and ingest it
    dummy_file = "sample.txt"
    if not os.path.exists(dummy_file):
        with open(dummy_file, "w") as f:
            f.write("LangChain is a framework for developing applications powered by language models.\n")
            f.write("FAISS is a library for efficient similarity search and clustering of dense vectors.\n")
            f.write("FastAPI is a modern, fast web framework for building APIs with Python.\n")
    
    ingest_data(dummy_file)
