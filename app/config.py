from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    mongodb_uri: str = "mongodb://localhost:27017/rag_db"
    faiss_index_path: str = "./faiss_index"

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
