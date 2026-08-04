import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://pharmacy:pharmacy@localhost:5432/pharmacy_db",
    )
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change_this_secret_in_production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    REFRESH_TOKEN_EXPIRE_DAYS: int = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

    # Optional real-LLM AI layer (Groq, OpenAI-compatible API). If GROQ_API_KEY
    # is unset, the app automatically stays on the offline rule-based AI layer
    # in services/ai_service.py — nothing breaks and no external calls happen.
    AI_PROVIDER: str = os.getenv("AI_PROVIDER", "rule_based")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL: str = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    GROQ_API_URL: str = "https://api.groq.com/openai/v1/chat/completions"

    # Thresholds used by the AI / rules layer
    LOW_STOCK_DEFAULT_REORDER_LEVEL: int = 20
    EXPIRY_WARNING_DAYS: int = 60  # flag batches expiring within this many days


settings = Settings()
