import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # API Configuration
    API_TITLE: str = "TWID AI Chat Service"
    API_VERSION: str = "1.0.0"
    
    # CORS Settings
    ALLOWED_ORIGINS: list = ["*"]  # In production, restrict to specific domains
    
    # Gemini AI Configuration
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "your-gemini-api-key")
    
    # Elasticsearch Configuration
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://elasticsearch:9200")
    ELASTICSEARCH_USERNAME: str = os.getenv("ELASTICSEARCH_USERNAME", "elastic")
    ELASTICSEARCH_PASSWORD: str = os.getenv("ELASTICSEARCH_PASSWORD", "changeme")
    ELASTICSEARCH_VERIFY_CERTS: bool = False  # Set to True in production
    
    # PHP Service Configuration
    PHP_SERVICE_URL: str = os.getenv("PHP_SERVICE_URL", "http://twid_mapi:80")
    PHP_SERVICE_API_KEY: str = os.getenv("PHP_SERVICE_API_KEY", "internal-api-key")
    
    class Config:
        env_file = ".env"

settings = Settings()