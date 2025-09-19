import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Base configuration."""
    
    # Flask configuration
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-key-please-change-in-production')
    DEBUG = os.environ.get('DEBUG', 'False').lower() in ['true', '1', 't']
    
    # Elasticsearch configuration
    ELASTICSEARCH_HOST = os.environ.get('ELASTICSEARCH_HOST', 'localhost:9200')
    ELASTICSEARCH_USER = os.environ.get('ELASTICSEARCH_USER', '')
    ELASTICSEARCH_PASSWORD = os.environ.get('ELASTICSEARCH_PASSWORD', '')
    
    # Gemini API configuration
    GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
    
    # TWID MAPI service configuration
    MAPI_SERVICE_URL = os.environ.get('MAPI_SERVICE_URL', 'http://twid_mapi/api')
    MAPI_SERVICE_TOKEN = os.environ.get('MAPI_SERVICE_TOKEN', '')
    
    # Rate limiting
    RATE_LIMIT_PER_MINUTE = int(os.environ.get('RATE_LIMIT_PER_MINUTE', 60))

class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True

class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False

class TestingConfig(Config):
    """Testing configuration."""
    TESTING = True
    DEBUG = True
    ELASTICSEARCH_HOST = 'localhost:9200'

# Determine which config to load based on environment
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}

def get_config():
    env = os.environ.get('FLASK_ENV', 'default')
    return config.get(env, config['default'])