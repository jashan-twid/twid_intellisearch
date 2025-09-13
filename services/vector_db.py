import logging
from elasticsearch import AsyncElasticsearch
from datetime import datetime
from typing import List, Dict, Optional, Any
import uuid

from config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Elasticsearch client
es = AsyncElasticsearch(
    hosts=[settings.ELASTICSEARCH_URL],
    basic_auth=(settings.ELASTICSEARCH_USERNAME, settings.ELASTICSEARCH_PASSWORD),
    verify_certs=settings.ELASTICSEARCH_VERIFY_CERTS
)

# Index name for chat history
CHAT_INDEX = "twid_chat_history"

async def ensure_index_exists():
    """Ensure the chat history index exists"""
    if not await es.indices.exists(index=CHAT_INDEX):
        await es.indices.create(
            index=CHAT_INDEX,
            body={
                "mappings": {
                    "properties": {
                        "user_id": {"type": "keyword"},
                        "session_id": {"type": "keyword"},
                        "message": {"type": "text"},
                        "response": {"type": "text"},
                        "intent": {"type": "keyword"},
                        "message_vector": {
                            "type": "dense_vector",
                            "dims": 768,
                            "index": True,
                            "similarity": "cosine"
                        },
                        "timestamp": {"type": "date"}
                    }
                }
            }
        )
        logger.info(f"Created index: {CHAT_INDEX}")

async def store_chat_history(user_id: str, message: str, response: str, 
                            intent: str, session_id: Optional[str] = None):
    """
    Store chat message and response in Elasticsearch
    """
    try:
        await ensure_index_exists()
        
        # In a real implementation, you would compute embeddings here
        # For simplicity, we're using a placeholder vector
        placeholder_vector = [0.0] * 768
        
        doc = {
            "user_id": user_id,
            "session_id": session_id or str(uuid.uuid4()),
            "message": message,
            "response": response,
            "intent": intent,
            "message_vector": placeholder_vector,  # Replace with actual embedding
            "timestamp": datetime.utcnow().isoformat()
        }
        
        result = await es.index(index=CHAT_INDEX, document=doc)
        logger.info(f"Stored chat message: {result['_id']}")
        return result['_id']
    
    except Exception as e:
        logger.error(f"Error storing chat history: {str(e)}")
        # Continue execution even if storage fails
        return None

async def get_chat_history(user_id: str, limit: int = 20) -> List[Dict]:
    """
    Retrieve chat history for a user
    """
    try:
        await ensure_index_exists()
        
        result = await es.search(
            index=CHAT_INDEX,
            body={
                "query": {
                    "term": {
                        "user_id": user_id
                    }
                },
                "sort": [
                    {"timestamp": {"order": "desc"}}
                ],
                "size": limit
            }
        )
        
        history = []
        for hit in result["hits"]["hits"]:
            source = hit["_source"]
            history.append({
                "id": hit["_id"],
                "message": source["message"],
                "response": source["response"],
                "intent": source["intent"],
                "timestamp": source["timestamp"]
            })
        
        return history
    
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        return []