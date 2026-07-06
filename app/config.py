from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    openai_api_key: str
    redis_url: str = "redis://localhost:6379/0"
    faiss_index_path: str = "./faiss_index"

    class Config:
        env_file = ".env"

settings = Settings()
