import logging
from datetime import datetime
from typing import Dict, Any, Optional
import json

logger = logging.getLogger(__name__)

INDEX_NAME = "chat_intents"

def search_similar_intent(es_client, user_id: str, query: str) -> Optional[Dict[str, Any]]:
    """
    Search for similar intents in Elasticsearch
    
    Args:
        es_client: Elasticsearch client
        user_id: User ID
        query: User query text
        
    Returns:
        Intent data if found, None otherwise
    """
    if not es_client:
        logger.error("Elasticsearch client not initialized")
        return None
    
    try:
        # First try exact match
        exact_match_query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"match_phrase": {"query": query}}
                    ]
                }
            },
            "size": 1
        }
        
        result = es_client.search(index=INDEX_NAME, body=exact_match_query)
        
        if result['hits']['total']['value'] > 0:
            return result['hits']['hits'][0]['_source']['intent_data']
        
        # Then try semantic search
        semantic_query = {
            "query": {
                "bool": {
                    "must": [
                        {"term": {"user_id": user_id}},
                        {"match": {
                            "query": {
                                "query": query,
                                "fuzziness": "AUTO",
                                "minimum_should_match": "70%"
                            }
                        }}
                    ]
                }
            },
            "size": 1
        }
        
        result = es_client.search(index=INDEX_NAME, body=semantic_query)
        
        if result['hits']['total']['value'] > 0 and result['hits']['hits'][0]['_score'] > 8.0:
            return result['hits']['hits'][0]['_source']['intent_data']
            
        return None
        
    except Exception as e:
        logger.error(f"Error searching Elasticsearch: {str(e)}")
        return None

def store_intent(es_client, user_id: str, query: str, intent_data: Dict[str, Any], feedback: bool = False) -> bool:
    """
    Store intent data in Elasticsearch
    
    Args:
        es_client: Elasticsearch client
        user_id: User ID
        query: User query text
        intent_data: Intent classification data
        feedback: Whether this is feedback data
        
    Returns:
        True if successful, False otherwise
    """
    if not es_client:
        logger.error("Elasticsearch client not initialized")
        return False
    
    try:
        # Store in Elasticsearch
        doc = {
            "user_id": user_id,
            "query": query,
            "intent_data": intent_data,
            "timestamp": datetime.utcnow().isoformat(),
            "is_feedback": feedback
        }
        
        es_client.index(index=INDEX_NAME, body=doc)
        
        # Maintain only last 100 messages per user
        prune_old_messages(es_client, user_id)
        
        return True
        
    except Exception as e:
        logger.error(f"Error storing in Elasticsearch: {str(e)}")
        return False

def prune_old_messages(es_client, user_id: str, max_messages: int = 100) -> None:
    """
    Prune old messages to maintain only the latest messages
    
    Args:
        es_client: Elasticsearch client
        user_id: User ID
        max_messages: Maximum number of messages to keep
    """
    try:
        # Count total messages for this user
        count_query = {
            "query": {"term": {"user_id": user_id}}
        }
        
        count_result = es_client.count(index=INDEX_NAME, body=count_query)
        count = count_result['count']
        
        # If more than max_messages, delete oldest messages
        if count > max_messages:
            delete_count = count - max_messages
            
            # Find oldest messages
            search_query = {
                "query": {"term": {"user_id": user_id}},
                "sort": [{"timestamp": "asc"}],
                "size": delete_count
            }
            
            results = es_client.search(index=INDEX_NAME, body=search_query)
            
            # Delete them
            for hit in results['hits']['hits']:
                es_client.delete(index=INDEX_NAME, id=hit['_id'])
                
    except Exception as e:
        logger.error(f"Error pruning old messages: {str(e)}")