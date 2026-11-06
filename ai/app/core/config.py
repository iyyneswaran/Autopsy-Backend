from pydantic_settings import BaseSettings
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[3] / 'server' / '.env')


class Settings(BaseSettings):

    PROJECT_NAME: str = "Atopsy AI Service"

    VERSION: str = "1.0.0"

    DATABASE_URL: str

    SECRET_KEY: str = ""
    JWT_ACCESS_SECRET: str = ""

    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    MAX_FILE_SIZE: int = 50 * 1024 * 1024

    # ── Pipeline Configuration ──────────────────

    # Storage
    STORAGE_BACKEND: str = "local"  # "local" | "s3"
    STORAGE_ROOT: str = "app/storage/pipeline"
    S3_BUCKET: str = ""
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    S3_REGION: str = "us-east-1"

    # Upload limits
    PIPELINE_MAX_FILE_SIZE: int = 500 * 1024 * 1024  # 500 MB
    PIPELINE_CHUNK_SIZE: int = 5 * 1024 * 1024  # 5 MB chunks
    PIPELINE_MAX_BATCH_SIZE: int = 20

    # Redis (optional — for queue/cache)
    REDIS_URL: str = ""

    # Temp storage
    TEMP_DIR: str = "app/storage/temp"

    # Google Gemini (for handwriting OCR)
    GOOGLE_API_KEY: str = ""
    TESSERACT_CMD: str = "tesseract"

    # Normalization
    NORMALIZATION_QUALITY_THRESHOLD: float = 0.5
    DEFAULT_TIMEZONE: str = "UTC"

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
