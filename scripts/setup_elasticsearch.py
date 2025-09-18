from elasticsearch import Elasticsearch
import os
import sys
import logging
import json
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import our ElasticsearchManager
from app.services.elasticsearch_manager import ElasticsearchManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default Elasticsearch settings (can be overridden via environment variables)
ES_HOST = os.environ.get("ELASTICSEARCH_HOST", "localhost")
ES_PORT = int(os.environ.get("ELASTICSEARCH_PORT", "9200"))
ES_USER = os.environ.get("ELASTICSEARCH_USER", "")
ES_PASSWORD = os.environ.get("ELASTICSEARCH_PASSWORD", "")
ES_GLOBAL_INDEX = os.environ.get("ES_GLOBAL_INDEX", "global_intent_training")
ES_USER_PREFIX = os.environ.get("ES_USER_PREFIX", "user_intent_training")

def get_global_training_examples() -> List[Dict[str, Any]]:
    """
    Define a set of high-quality training examples for each intent type.
    These examples will be used as the baseline for the intent classifier.
    
    Returns:
        List of training examples
    """
    examples = [
        # PAY_TO_PERSON examples
        {
            "query": "Send 500 rupees to Raj for dinner",
            "intent": "PAY_TO_PERSON",
            "confidence": 1.0,
            "extracted_data": {
                "payee_name": "Raj",
                "amount": 500,
                "note": "dinner"
            },
            "data_quality": 10
        },
        {
            "query": "Transfer ₹1000 to Priya",
            "intent": "PAY_TO_PERSON",
            "confidence": 1.0,
            "extracted_data": {
                "payee_name": "Priya",
                "amount": 1000,
                "note": None
            },
            "data_quality": 10
        },
        {
            "query": "Pay Amit 2500 for the concert tickets",
            "intent": "PAY_TO_PERSON",
            "confidence": 1.0,
            "extracted_data": {
                "payee_name": "Amit",
                "amount": 2500,
                "note": "concert tickets"
            },
            "data_quality": 10
        },
        
        # PAY_BILL examples
        {
            "query": "Pay my electricity bill",
            "intent": "PAY_BILL",
            "confidence": 1.0,
            "extracted_data": {
                "bill_type": "electricity",
                "biller_name": None,
                "amount": None
            },
            "data_quality": 10
        },
        {
            "query": "Pay Reliance water bill of 780 rupees",
            "intent": "PAY_BILL",
            "confidence": 1.0,
            "extracted_data": {
                "bill_type": "water",
                "biller_name": "Reliance",
                "amount": 780
            },
            "data_quality": 10
        },
        {
            "query": "Pay my Airtel mobile bill",
            "intent": "PAY_BILL",
            "confidence": 1.0,
            "extracted_data": {
                "bill_type": "mobile",
                "biller_name": "Airtel",
                "amount": None
            },
            "data_quality": 10
        },
        
        # CHECK_REWARDS examples
        {
            "query": "How many reward points do I have?",
            "intent": "CHECK_REWARDS",
            "confidence": 1.0,
            "extracted_data": {
                "reward_type": "points"
            },
            "data_quality": 10
        },
        {
            "query": "Check my cashback balance",
            "intent": "CHECK_REWARDS",
            "confidence": 1.0,
            "extracted_data": {
                "reward_type": "cashback"
            },
            "data_quality": 10
        },
        {
            "query": "Show my total rewards",
            "intent": "CHECK_REWARDS",
            "confidence": 1.0,
            "extracted_data": {
                "reward_type": None
            },
            "data_quality": 10
        },
        
        # TRANSACTION_HISTORY examples
        {
            "query": "Show me my transactions from last week",
            "intent": "TRANSACTION_HISTORY",
            "confidence": 1.0,
            "extracted_data": {
                "time_period": "last week",
                "transaction_type": None
            },
            "data_quality": 10
        },
        {
            "query": "Get my payment history for September",
            "intent": "TRANSACTION_HISTORY",
            "confidence": 1.0,
            "extracted_data": {
                "time_period": "September",
                "transaction_type": "payment"
            },
            "data_quality": 10
        },
        {
            "query": "View recent transactions",
            "intent": "TRANSACTION_HISTORY",
            "confidence": 1.0,
            "extracted_data": {
                "time_period": "recent",
                "transaction_type": None
            },
            "data_quality": 10
        },
        
        # OTHER examples
        {
            "query": "What's the weather like today?",
            "intent": "OTHER",
            "confidence": 1.0,
            "extracted_data": {},
            "data_quality": 10
        },
        {
            "query": "Tell me a joke",
            "intent": "OTHER",
            "confidence": 1.0,
            "extracted_data": {},
            "data_quality": 10
        },
        {
            "query": "What are your operating hours?",
            "intent": "OTHER",
            "confidence": 1.0,
            "extracted_data": {},
            "data_quality": 10
        }
    ]
    
    return examples

def setup_elasticsearch():
    """Set up Elasticsearch indices and mappings and populate with global training data"""
    
    try:
        # Use our ElasticsearchManager
        # Handle authentication if provided
        connection_params = {'host': ES_HOST, 'port': ES_PORT, 'scheme': 'http'}
        if ES_USER and ES_PASSWORD:
            connection_params['http_auth'] = (ES_USER, ES_PASSWORD)
            
        es_manager = ElasticsearchManager(
            es_host=ES_HOST,
            es_port=ES_PORT,
            global_index=ES_GLOBAL_INDEX,
            user_index_prefix=ES_USER_PREFIX,
            es_auth=connection_params
        )
        
        logger.info("Connected to Elasticsearch")
        
        # Insert global training examples
        examples = get_global_training_examples()
        es_manager.bulk_insert_global_examples(examples)
        logger.info(f"Successfully inserted {len(examples)} global training examples")
        
        return True
        
    except Exception as e:
        logger.error(f"Failed to set up Elasticsearch: {str(e)}")
        return False

if __name__ == "__main__":
    if setup_elasticsearch():
        logger.info("Elasticsearch setup completed successfully")
    else:
        logger.error("Elasticsearch setup failed")