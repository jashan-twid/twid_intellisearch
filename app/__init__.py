import logging
import os
from flask import Flask
from flask_cors import CORS
import google.generativeai as genai
from config.settings import Config
from app.services.elasticsearch_manager import ElasticsearchManager
from app.services.intent_classifier import get_intent_classifier_model

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize global variables
es_manager = None
classifier_model = None

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    
    # Enable CORS
    CORS(app)
    
    # Initialize Elasticsearch Manager
    global es_manager
    try:
        es_host = app.config.get('ELASTICSEARCH_HOST', 'localhost')
        es_port = app.config.get('ELASTICSEARCH_PORT', 9200)
        es_global_index = app.config.get('ES_GLOBAL_INDEX', 'global_intent_training')
        es_user_prefix = app.config.get('ES_USER_PREFIX', 'user_intent_training')
        es_user = app.config.get('ELASTICSEARCH_USER')
        es_password = app.config.get('ELASTICSEARCH_PASSWORD')
        # Handle authentication if provided
        if es_user and es_password:
            connection_params = {
                'host': es_host, 
                'port': es_port, 
                'scheme': 'http',
                'http_auth': (es_user, es_password)
            }
            es_manager = ElasticsearchManager(
                es_host=es_host,
                es_port=es_port,
                global_index=es_global_index,
                user_index_prefix=es_user_prefix,
                es_auth=connection_params
            )
        else:
            es_manager = ElasticsearchManager(
                es_host=es_host,
                es_port=es_port,
                global_index=es_global_index,
                user_index_prefix=es_user_prefix
            )
        logger.info("Connected to Elasticsearch")
        # Import contacts from .vcf files on startup
        from app.utils.vcf_importer import import_all_user_contacts
        contacts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../contacts')
        import_all_user_contacts(contacts_dir, es_manager)
        logger.info("Imported contacts from .vcf files into Elasticsearch")

        # --- Index generic bill data and user credit card data on startup ---
        from app.services.bill_seed_data import GENERIC_BILL_DATA, USER_CREDIT_CARD_DATA
        # Create indices with simple mappings if not exist
        generic_bills_mapping = {
            "mappings": {
                "properties": {
                    "title": {"type": "text"},
                    "icon_url": {"type": "keyword"},
                    "id": {"type": "integer"},
                    "request": {"type": "nested"}
                }
            }
        }
        user_credit_cards_mapping = {
            "mappings": {
                "properties": {
                    "biller_name": {"type": "text"},
                    "biller_logo": {"type": "keyword"},
                    "customer_id": {"type": "keyword"},
                    "unique_bill_id": {"type": "keyword"}
                }
            }
        }
        es_manager.create_index_with_mapping("generic_bills", generic_bills_mapping)
        es_manager.create_index_with_mapping("user_credit_cards", user_credit_cards_mapping)
        es_manager.bulk_insert_generic_bills(GENERIC_BILL_DATA)
        es_manager.bulk_insert_user_credit_cards(USER_CREDIT_CARD_DATA)
        logger.info("Seeded generic bill data and user credit card data into Elasticsearch")
    except Exception as e:
        logger.error(f"Elasticsearch initialization error: {str(e)}")
    
    # Initialize Gemini API with system prompt from Elasticsearch examples
    global classifier_model
    try:
        # Configure Gemini API
        genai.configure(api_key=app.config['GEMINI_API_KEY'])
        
        # Generate system prompt from global training data
        if es_manager:
            system_prompt = es_manager.generate_system_prompt()
            classifier_model = get_intent_classifier_model(system_prompt)
            logger.info("Gemini API initialized with system prompt from training data")
        else:
            # Fallback to default model if Elasticsearch isn't available
            classifier_model = get_intent_classifier_model()
            logger.warning("Gemini API initialized with default system prompt (no training data)")
    except Exception as e:
        logger.error(f"Gemini API initialization error: {str(e)}")
    
    # Register blueprints
    from app.api.routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    # Register bills blueprint
    from app.api.bills import bills_bp
    app.register_blueprint(bills_bp, url_prefix='/api')
    
    @app.route('/health')
    def health_check():
        return {"status": "healthy", "service": "twid_intellisearch"}
    
    return app