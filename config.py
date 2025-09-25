import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/facturav_db")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "clave-secreta-por-defecto-cambiar-en-produccion")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))  # 24 horas
    AZURE_FORM_RECOGNIZER_ENDPOINT: str = os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT", "")
    AZURE_FORM_RECOGNIZER_KEY: str = os.getenv("AZURE_FORM_RECOGNIZER_KEY", "")
    SMTP_SERVER: str = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", 587))
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL","")
    
    class Config:
        case_sensitive = True

settings = Settings()