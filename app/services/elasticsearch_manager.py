import json
import logging
import time
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from elasticsearch import Elasticsearch
from elasticsearch.exceptions import ConnectionError, TransportError

logger = logging.getLogger(__name__)

def retry_elasticsearch_operation(max_retries=5, initial_backoff=1, max_backoff=30):
    """
    Decorator to retry Elasticsearch operations with exponential backoff
    
    Args:
        max_retries: Maximum number of retry attempts
        initial_backoff: Initial backoff time in seconds
        max_backoff: Maximum backoff time in seconds
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            retries = 0
            backoff = initial_backoff
            
            while True:
                try:
                    return func(*args, **kwargs)
                except (ConnectionError, TransportError) as e:
                    retries += 1
                    if retries > max_retries:
                        logger.error(f"Maximum retries ({max_retries}) reached. Operation failed: {str(e)}")
                        raise
                    
                    logger.warning(f"Elasticsearch operation failed (attempt {retries}/{max_retries}), "
                                   f"retrying in {backoff} seconds. Error: {str(e)}")
                    time.sleep(backoff)
                    # Exponential backoff with cap
                    backoff = min(backoff * 2, max_backoff)
        return wrapper
    return decorator

class ElasticsearchManager:
    @retry_elasticsearch_operation()
    def create_index_with_mapping(self, index_name: str, mapping: dict):
        """
        Create an index with a custom mapping if it doesn't exist
        """
        if not self.es_client.indices.exists(index=index_name):
            self.es_client.indices.create(index=index_name, body=mapping)
            logger.info(f"Created Elasticsearch index '{index_name}' with custom mapping")

    @retry_elasticsearch_operation()
    def bulk_insert_generic_bills(self, bills: list, index_name: str = "generic_bills"):
        """
        Bulk insert generic bill data into Elasticsearch
        """
        if not bills:
            return
        bulk_data = []
        for bill in bills:
            action = {"index": {"_index": index_name}}
            bulk_data.append(action)
            bulk_data.append(bill)
        self.es_client.bulk(body=bulk_data, refresh=True)
        logger.info(f"Inserted {len(bills)} generic bills into Elasticsearch index '{index_name}'")

    @retry_elasticsearch_operation()
    def bulk_insert_user_credit_cards(self, cards: list, index_name: str = "user_credit_cards"):
        """
        Bulk insert user-specific credit card data into Elasticsearch
        """
        if not cards:
            return
        bulk_data = []
        for card in cards:
            action = {"index": {"_index": index_name}}
            bulk_data.append(action)
            bulk_data.append(card)
        self.es_client.bulk(body=bulk_data, refresh=True)
        logger.info(f"Inserted {len(cards)} user credit cards into Elasticsearch index '{index_name}'")
    """Manages training data in Elasticsearch for global and user-specific examples"""
    
    def __init__(self, es_host="localhost", es_port=9200, 
                 global_index="global_intent_training", 
                 user_index_prefix="user_intent_training",
                 es_auth=None):
        """
        Initialize Elasticsearch connection
        
        Args:
            es_host: Elasticsearch host
            es_port: Elasticsearch port
            global_index: Index for global training data
            user_index_prefix: Prefix for user-specific indices
            es_auth: Optional dict with auth parameters (http_auth, api_key, etc.)
        """
        # Handle connection params
        if es_auth:
            self.es_client = Elasticsearch([es_auth])
        else:
            self.es_client = Elasticsearch([{'host': es_host, 'port': es_port, 'scheme': 'http'}])
            
        self.global_index = global_index
        self.user_index_prefix = user_index_prefix
        
        # Test the connection with retry
        self._test_connection()
        
        # Create global index if it doesn't exist
        self._create_index_if_not_exists(self.global_index)
        
    @retry_elasticsearch_operation(max_retries=10, initial_backoff=2, max_backoff=60)
    def _test_connection(self):
        """Test Elasticsearch connection with retries"""
        if self.es_client.ping():
            logger.info("Successfully connected to Elasticsearch")
        else:
            raise ConnectionError("Failed to connect to Elasticsearch")
    
    def _get_user_index(self, user_id: str) -> str:
        """
        Get the index name for a specific user
        
        Args:
            user_id: Unique user identifier
            
        Returns:
            Index name for the user
        """
        return f"{self.user_index_prefix}_{user_id}"
    
    @retry_elasticsearch_operation()
    def _create_index_if_not_exists(self, index_name: str):
        """
        Create an index if it doesn't exist
        
        Args:
            index_name: Name of the index to create
        """
        if not self.es_client.indices.exists(index=index_name):
            mapping = {
                "mappings": {
                    "properties": {
                        "query": {"type": "text"},
                        "intent": {"type": "keyword"},
                        "confidence": {"type": "float"},
                        "extracted_data": {"type": "object"},
                        "timestamp": {"type": "date"},
                        "user_feedback": {"type": "boolean"},
                        "is_global": {"type": "boolean"},
                        "data_quality": {"type": "integer"}  # 1-10 score to rank example quality
                    }
                }
            }
            self.es_client.indices.create(index=index_name, body=mapping)
            logger.info(f"Created Elasticsearch index '{index_name}'")
    
    @retry_elasticsearch_operation()
    def save_example(self, query: str, classification: Dict[str, Any], 
                    user_id: Optional[str] = None, 
                    user_feedback: Optional[bool] = None,
                    is_global: bool = False,
                    data_quality: int = 5):
        """
        Save a classification example to Elasticsearch
        
        Args:
            query: User query text
            classification: Classification result
            user_id: Optional user identifier
            user_feedback: Optional boolean indicating user feedback
            is_global: Whether this example should be stored as global
            data_quality: Quality score for this training example (1-10)
        """
        document = {
            "query": query,
            "intent": classification.get("intent", "OTHER"),
            "confidence": classification.get("confidence", 0.0),
            "extracted_data": classification.get("extracted_data", {}),
            "timestamp": datetime.now().isoformat(),
            "user_feedback": user_feedback,
            "is_global": is_global,
            "data_quality": data_quality
        }
        
        # Determine which index to use
        if is_global:
            index = self.global_index
        elif user_id:
            index = self._get_user_index(user_id)
            # Create user-specific index if needed
            self._create_index_if_not_exists(index)
        else:
            # If neither global nor user-specific, use global as default
            index = self.global_index
        
        self.es_client.index(index=index, body=document)
        logger.debug(f"Saved training example to Elasticsearch index '{index}': {query}")
    
    @retry_elasticsearch_operation()
    def get_examples_by_intent(self, intent: str, user_id: Optional[str] = None,
                              max_global_examples: int = 3, 
                              max_user_examples: int = 2) -> List[Dict[str, Any]]:
        """
        Get examples for a specific intent from Elasticsearch
        
        Args:
            intent: Intent type to filter examples
            user_id: Optional user identifier
            max_global_examples: Maximum number of global examples to return
            max_user_examples: Maximum number of user-specific examples to return
            
        Returns:
            List of matching examples
        """
        results = []
        
        # First get high-quality global examples
        global_query = {
            "size": max_global_examples,
            "sort": [
                {"data_quality": {"order": "desc"}},
                {"timestamp": {"order": "desc"}}
            ],
            "query": {
                "bool": {
                    "must": [
                        {"term": {"intent": intent}},
                        {"term": {"is_global": True}}
                    ]
                }
            }
        }
        
        try:
            # We use a separate try-except here to continue execution even if global examples fail
            global_result = self.es_client.search(index=self.global_index, body=global_query)
            global_examples = [hit["_source"] for hit in global_result["hits"]["hits"]]
            results.extend(global_examples)
        except Exception as e:
            logger.error(f"Failed to retrieve global examples: {str(e)}")
        
        # Then get user-specific examples if a user_id was provided
        if user_id:
            user_index = self._get_user_index(user_id)
            
            try:
                # Only query if the user index exists
                if self.es_client.indices.exists(index=user_index):
                    user_query = {
                        "size": max_user_examples,
                        "sort": [{"timestamp": {"order": "desc"}}],
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"intent": intent}}
                                ]
                            }
                        }
                    }
                    
                    # First try with positive feedback
                    feedback_query = {**user_query}
                    feedback_query["query"]["bool"]["must"].append({"term": {"user_feedback": True}})
                    
                    feedback_result = self.es_client.search(index=user_index, body=feedback_query)
                    feedback_examples = [hit["_source"] for hit in feedback_result["hits"]["hits"]]
                    
                    # If we don't have enough examples with feedback, get regular examples
                    if len(feedback_examples) < max_user_examples:
                        remaining = max_user_examples - len(feedback_examples)
                        regular_result = self.es_client.search(
                            index=user_index, 
                            body={**user_query, "size": remaining}
                        )
                        regular_examples = [hit["_source"] for hit in regular_result["hits"]["hits"]]
                        results.extend(feedback_examples + regular_examples)
                    else:
                        results.extend(feedback_examples)
            except Exception as e:
                logger.error(f"Failed to retrieve user examples: {str(e)}")
        
        return results
    
    @retry_elasticsearch_operation()
    def bulk_insert_global_examples(self, examples: List[Dict[str, Any]]) -> None:
        """
        Insert multiple global training examples at once
        
        Args:
            examples: List of example objects with query, classification, etc.
        """
        if not examples:
            return
            
        bulk_data = []
        for example in examples:
            # Create action/data pairs for bulk API
            action = {"index": {"_index": self.global_index}}
            
            # Convert classification object if present
            if "classification" in example:
                classification = example["classification"]
            else:
                classification = {
                    "intent": example.get("intent", "OTHER"),
                    "confidence": example.get("confidence", 1.0),
                    "extracted_data": example.get("extracted_data", {})
                }
            
            # Create document
            document = {
                "query": example["query"],
                "intent": classification.get("intent", "OTHER"),
                "confidence": classification.get("confidence", 1.0),
                "extracted_data": classification.get("extracted_data", {}),
                "timestamp": example.get("timestamp", datetime.now().isoformat()),
                "user_feedback": example.get("user_feedback", True),  # Default to True for seed data
                "is_global": True,
                "data_quality": example.get("data_quality", 10)  # Default high quality for seed data
            }
            
            bulk_data.append(action)
            bulk_data.append(document)
        
        if bulk_data:
            self.es_client.bulk(body=bulk_data, refresh=True)
            logger.info(f"Inserted {len(examples)} global examples into Elasticsearch")
    
    @retry_elasticsearch_operation()
    def generate_system_prompt(self, user_id: Optional[str] = None,
                              max_examples_per_intent: int = 5) -> str:
        """
        Generate a system prompt using training examples from Elasticsearch
        
        Args:
            user_id: Optional user identifier for personalized prompt
            max_examples_per_intent: Maximum examples per intent to include
            
        Returns:
            System prompt string
        """
        # Base system prompt
        system_prompt = """
        You are an intent classification system for a financial assistant.
        
        Classify user queries into these intents:
        - PAY_TO_PERSON: For person-to-person payments
        - PAY_BILL: For bill payments (electricity, water, etc.)
        - OTHER: For any other queries
        
        Examples:
        """
        
        # Add examples for each intent type
        intents = ["PAY_TO_PERSON", "PAY_BILL", "CHECK_REWARDS", "TRANSACTION_HISTORY", "OTHER"]
        example_count = 1
        
        # Calculate examples distribution - more for user if user_id provided
        if user_id:
            # If user-specific, use 2 global + 3 user examples per intent
            max_global = 2
            max_user = 3
        else:
            # If not user-specific, use all global examples
            max_global = max_examples_per_intent
            max_user = 0
        
        for intent in intents:
            # Get examples for this intent from Elasticsearch
            examples = self.get_examples_by_intent(
                intent, 
                user_id=user_id,
                max_global_examples=max_global,
                max_user_examples=max_user
            )
            
            # Add examples to prompt
            for example in examples:
                query = example.get("query", "")
                
                # Reconstruct classification object
                classification = {
                    "intent": example.get("intent", "OTHER"),
                    "confidence": example.get("confidence", 1.0),
                    "extracted_data": example.get("extracted_data", {})
                }
                
                system_prompt += f"""
                {example_count}. Query: "{query}"
                   Classification: {json.dumps(classification, indent=2)}
                """
                example_count += 1
        
        # Add extraction rules and output format
        system_prompt += """
        For PAY_TO_PERSON, extract:
            Follow these rules strictly:

            1. **payee_name**:
            - VERY IMP: For all scenarios, there can be some mismatches or ambiguities in names.
            - Compare the given payee name in the query against the user's contacts.
            - First, check for an exact full match (case-insensitive). If found, return only that contact.
            - If no exact match:
                - Use fuzzy/AI similarity. Only consider contacts with ≥80% similarity.
                - If one contact is clearly the best match, return only that contact.
                - If multiple contacts have close similarity scores (within 5–10% of each other), return the list of those candidates.
            - If no contact crosses 80% similarity, return `null` for `payee_name`.

            2. **amount**:
            - Extract the payment amount in INR (integer).

            3. **note**:
            - Extract the reason/purpose for payment, if present. Otherwise return `null`.

        For PAY_BILL, extract:
        - category_name: Type of bill (Out of these: CREDIT CARD, FASTAG, ELECTRICITY, GAS, INSURANCE)
        - biller_name: Name of the biller (Like 'Axis', 'HDFC')
        - amount: The payment amount (if specified)

        Return a JSON object with the following structure:
        {
            "intent": "INTENT_TYPE",
            "confidence": 0.9,
            "extracted_data": {
                // Relevant extracted fields based on intent type
            }
        }

        Return raw JSON only with NO markdown formatting, NO code blocks, and NO additional text.
        """
        
        return system_prompt