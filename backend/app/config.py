import os


class Settings:
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://pharmacy:pharmacy@localhost:5432/pharmacy_db",
    )
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "change_this_secret_in_production")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

    # Thresholds used by the AI / rules layer
    LOW_STOCK_DEFAULT_REORDER_LEVEL: int = 20
    EXPIRY_WARNING_DAYS: int = 60  # flag batches expiring within this many days


settings = Settings()
