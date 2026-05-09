from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):

    PROJECT_NAME: str = "Atopsy AI Service"

    VERSION: str = "1.0.0"

    DATABASE_URL: str

    SECRET_KEY: str

    ALGORITHM: str = "HS256"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    MAX_FILE_SIZE: int = 50 * 1024 * 1024

    class Config:
        env_file = ".env"


settings = Settings()