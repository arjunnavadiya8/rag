import os
from langchain_community.document_loaders import DirectoryLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from app.config import settings

def ingest_directory(directory_path: str):
    """
    Load all pdf documents from a directory, chunk them, embed them, and save the FAISS index.
    """
    print(f"Loading documents from directory: {directory_path}")
    
    # We use PyPDFLoader for all .pdf files in the directory
    loader = DirectoryLoader(directory_path, glob="**/*.pdf", loader_cls=PyPDFLoader)
    documents = loader.load()
    
    if not documents:
        print(f"No documents found in {directory_path}. Please add some .pdf files.")
        return

    print(f"Loaded {len(documents)} document(s). Splitting text into chunks...")
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
    data_dir = "data"
    
    # Ensure the data directory exists
    if not os.path.exists(data_dir):
        os.makedirs(data_dir)
        print(f"Created directory '{data_dir}'. Please add your .pdf files there.")
        
    ingest_directory(data_dir)
