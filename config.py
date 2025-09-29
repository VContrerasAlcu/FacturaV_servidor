import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()

class Settings(BaseSettings):
    DATABASE_URL: str = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/facturav_db")
    JWT_SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", "clave-secreta-por-defecto-cambiar-en-produccion")
    JWT_ALGORITHM: str = os.getenv("JWT_ALGORITHM", "HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 1440))  # 24 horas
    
    # Azure Document Intelligence (nuevo nombre para Form Recognizer)
    AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT: str = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT", "")
    AZURE_DOCUMENT_INTELLIGENCE_KEY: str = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY", "")
    
    # Compatibilidad con nombres antiguos
    AZURE_FORM_RECOGNIZER_ENDPOINT: str = os.getenv("AZURE_FORM_RECOGNIZER_ENDPOINT", "")
    AZURE_FORM_RECOGNIZER_KEY: str = os.getenv("AZURE_FORM_RECOGNIZER_KEY", "")
    
    # Email
    SENDGRID_API_KEY: str = os.getenv("SENDGRID_API_KEY", "")
    FROM_EMAIL: str = os.getenv("FROM_EMAIL","")
    
    # Obtener endpoints con fallback
    @property
    def document_intelligence_endpoint(self):
        return (self.AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT or 
                self.AZURE_FORM_RECOGNIZER_ENDPOINT)
    
    @property
    def document_intelligence_key(self):
        return (self.AZURE_DOCUMENT_INTELLIGENCE_KEY or 
                self.AZURE_FORM_RECOGNIZER_KEY)
    
    class Config:
        case_sensitive = True

settings = Settings()