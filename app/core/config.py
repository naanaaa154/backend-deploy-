from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # Ollama
    OLLAMA_BASE_URL: str
    OLLAMA_LLM_MODEL: str
    OLLAMA_EMBEDDING_MODEL: str
    # OLLAMA_CLASSIFIER_MODEL: str
    

    # LLM Provider
    LLM_PROVIDER: str = "ollama"

    OLLAMA_BASE_NGROK_URL: str

    # Groq
    GROQ_API_KEY: str | None = None
    GROQ_LLM_MODEL: str | None = None
    GROQ_LLM_MODEL_CLASSIFIER: str | None = None

    # Database
    DATABASE_URL: str

    # External rerank endpoint (optional)
    RERANK_ENDPOINT: str | None = None

    # Security
    JWT_SECRET_KEY: str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
