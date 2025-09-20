from flask import Blueprint, request, jsonify, current_app
from app import es_manager, classifier_model
from app.services.intent_classifier import classify_intent_with_feedback, get_intent_classifier_model
import json
import logging
import threading

logger = logging.getLogger(__name__)
api_bp = Blueprint('api', __name__)

# Thread-safe lock for model updates
model_update_lock = threading.Lock()

def refresh_model_async():
    """Refresh the model with the latest training data in a background thread"""
    from app import classifier_model
    
    try:
        with model_update_lock:
            # Generate new system prompt from Elasticsearch data
            system_prompt = es_manager.generate_system_prompt()
            
            # Create a new model with the updated prompt
            new_model = get_intent_classifier_model(system_prompt)
            
            # Replace the global model - need to use a different approach since it's imported
            import app
            app.classifier_model = new_model
            
        logger.info("Model refreshed with latest training data")
    except Exception as e:
        logger.error(f"Error refreshing model: {str(e)}")

@api_bp.route('/classify-intent', methods=['POST'])
def classify_intent_route():
    """
    Classify user query intent
    ---
    Expected JSON payload:
    {
        "user_id": "string" (optional),
        "query": "string",
        "context": {} (optional)
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "No data provided"}), 400

        user_id = data.get('user_id')
        query = data.get('query')
        if not query:
            return jsonify({"error": "Missing required field: query"}), 400

        if not classifier_model:
            return jsonify({"error": "Classifier model not initialized"}), 500

        # Personalized model logic (unchanged)
        model_to_use = classifier_model

        # --- Custom: Collect contact names for user_id ---
        contact_names = []
        if user_id and es_manager:
            contact_index = f"user_contacts_{user_id}"
            try:
                if es_manager.es_client.indices.exists(index=contact_index):
                    # Get all contact names for the user
                    resp = es_manager.es_client.search(
                        index=contact_index,
                        body={
                            "size": 1000,
                            "_source": ["name"],
                            "query": {"match_all": {}}
                        }
                    )
                    hits = resp.get("hits", {}).get("hits", [])
                    contact_names = [hit["_source"]["name"] for hit in hits if "name" in hit["_source"]]
            except Exception as e:
                logger.warning(f"Failed to fetch contact names: {str(e)}")
        if user_id and es_manager:
            user_prompt = es_manager.generate_system_prompt(user_id=user_id)
            if "Examples:" in user_prompt and len(user_prompt) > 1000:
                model_to_use = get_intent_classifier_model(user_prompt)
                logger.info(f"Using personalized model for user {user_id}")

        from app.services.intent_classifier import classify_intent_direct

        # --- Custom: For PAY_TO_PERSON, pass contact names to AI ---
        ai_context = data.get("context", {})
        if contact_names:
            ai_context = dict(ai_context)  # copy
            ai_context["contact_names"] = contact_names
        logger.debug(f"AI context: {ai_context}")
        intent_data = classify_intent_direct(model_to_use, query, context=ai_context)
        logger.info(f"Intent classified: {intent_data}")

        # --- PAY_BILL: Add user-specific bill data in extracted_data.additional_data ---
        if intent_data.get("intent") == "PAY_BILL" and user_id and es_manager:
            biller_name = intent_data.get("extracted_data", {}).get("biller_name")
            category_name = intent_data.get("extracted_data", {}).get("category_name")
            matched_cards = []
            if biller_name:
                # Remove common terms like 'bank' (case-insensitive, word boundary)
                import re
                normalized_biller = re.sub(r"\\bbank\\b", "", biller_name, flags=re.IGNORECASE).strip()
                try:
                    resp = es_manager.es_client.search(
                        index="user_credit_cards",
                        body={
                            "size": 100,
                            "query": {
                                "bool": {
                                    "must": [
                                        {"term": {"customer_id": user_id}},
                                        {"match": {"biller_name": normalized_biller}}
                                    ]
                                }
                            }
                        }
                    )
                    matched_cards = [hit["_source"] for hit in resp["hits"]["hits"]]
                except Exception as e:
                    logger.warning(f"Failed to fetch user credit cards: {str(e)}")
            logger.info(f"Matched cards for user {user_id}: {matched_cards}")
            # Always fetch generic bills for fallback
            generic_bills = []
            try:
                resp = es_manager.es_client.search(
                    index="generic_bills",
                    body={"size": 1000, "query": {"match_all": {}}}
                )
                generic_bills = [hit["_source"] for hit in resp["hits"]["hits"]]
            except Exception as e:
                logger.warning(f"Failed to fetch generic bills: {str(e)}")
            if matched_cards:
                # Only deduplicate by unique_bill_id if present, otherwise include all
                seen = set()
                deduped_cards = []
                for card in matched_cards:
                    unique_id = None
                    # Try to get unique_bill_id from card['request'] if present
                    if isinstance(card.get("request"), dict):
                        unique_id = card["request"].get("unique_bill_id")
                    if unique_id:
                        if unique_id not in seen:
                            seen.add(unique_id)
                            deduped_cards.append(card)
                    else:
                        deduped_cards.append(card)
                intent_data["extracted_data"]["additional_data"] = deduped_cards
            else:
                # If no matched card, filter generic bills by biller_name (ignoring 'bank')
                filtered_bills = generic_bills
                if biller_name:
                    import re
                    normalized_biller = re.sub(r"\\bbank\\b", "", biller_name, flags=re.IGNORECASE).strip().lower()
                    filtered_bills = []
                    for b in generic_bills:
                        title_match = b.get("title") and normalized_biller in re.sub(r"\\bbank\\b", "", b["title"], flags=re.IGNORECASE).strip().lower()
                        biller_name_match = b.get("biller_name") and normalized_biller in re.sub(r"\\bbank\\b", "", b["biller_name"], flags=re.IGNORECASE).strip().lower()
                        if title_match or biller_name_match:
                            filtered_bills = [b]
                            break
                # Optionally filter by category_name as well
                if category_name:
                    filtered_bills = [b for b in filtered_bills if any(r.get("category_id") == 22 for r in b.get("request", []))] if category_name.upper() == "CREDIT CARD" else filtered_bills
                intent_data["extracted_data"]["additional_data"] = filtered_bills

        # --- PAY_TO_PERSON: Add contacts as before ---
        if (
            intent_data.get("intent") == "PAY_TO_PERSON"
            and user_id and es_manager
            and "payee_name" in intent_data.get("extracted_data", {})
        ):
            payee_name = intent_data["extracted_data"]["payee_name"]
            # Only search if payee_name is in contact_names
            if payee_name in contact_names:
                try:
                    contact_index = f"user_contacts_{user_id}"
                    if es_manager.es_client.indices.exists(index=contact_index):
                        search_body = {
                            "size": 10,  # Get multiple matches
                            "query": {"match": {"name": payee_name}}
                        }
                        resp = es_manager.es_client.search(index=contact_index, body=search_body)
                        hits = resp.get("hits", {}).get("hits", [])
                        # Handle multiple contacts with same name
                        if len(hits) > 0:
                            contact_list = []
                            for hit in hits:
                                contact_list.append({
                                    "name": hit["_source"].get("name"),
                                    "number": hit["_source"].get("number")
                                })
                            # Keep contacts list only within extracted_data
                            intent_data["extracted_data"]["contacts"] = contact_list
                            if "payee_name" in intent_data["extracted_data"]:
                                del intent_data["extracted_data"]["payee_name"]
                except Exception as e:
                    logger.warning(f"Contact lookup failed: {str(e)}")
            else:
                # If payee_name not in contact_names, show nothing
                intent_data["extracted_data"].pop("payee_name", None)
                intent_data["extracted_data"]["contacts"] = []

        # Store high-confidence results if ES is available (no feedback flow)
        if es_manager and intent_data.get("confidence", 0) > 0.8 and user_id:
            try:
                def store_result():
                    es_manager.save_example(
                        query=query,
                        classification=intent_data,
                        user_id=user_id,
                        is_global=False
                    )
                threading.Thread(target=store_result, daemon=True).start()
            except Exception as e:
                logger.warning(f"Failed to store result: {str(e)}")

        return jsonify(intent_data)
    
    except Exception as e:
        logger.error(f"Error in classify_intent_route: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@api_bp.route('/feedback', methods=['POST'])
def intent_feedback():
    """
    Provide feedback on intent classification
    ---
    Expected JSON payload:
    {
        "user_id": "string" (optional),
        "query": "string",
        "correct_intent": {
            "intent": "string",
            "confidence": float,
            "extracted_data": {}
        },
        "is_global": boolean (optional, defaults to false),
        "data_quality": int (optional, 1-10, defaults to 8 for user feedback)
    }
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data provided"}), 400
        
        user_id = data.get('user_id')
        query = data.get('query')
        correct_intent = data.get('correct_intent')
        is_global = data.get('is_global', False)
        data_quality = data.get('data_quality', 8)  # High quality for user feedback
        
        if not query or not correct_intent:
            return jsonify({"error": "Missing required fields"}), 400
        
        # Ensure correct_intent has required fields
        if 'intent' not in correct_intent:
            return jsonify({"error": "Missing intent field in correct_intent"}), 400
            
        if 'confidence' not in correct_intent:
            correct_intent['confidence'] = 1.0  # Assume 100% confidence for user feedback
            
        if 'extracted_data' not in correct_intent:
            correct_intent['extracted_data'] = {}
        
        # Store the feedback in Elasticsearch
        es_manager.save_example(
            query=query, 
            classification=correct_intent, 
            user_id=user_id, 
            user_feedback=True,
            is_global=is_global,
            data_quality=data_quality
        )
        
        # Trigger model refresh in background
        background_thread = threading.Thread(target=refresh_model_async)
        background_thread.daemon = True
        background_thread.start()
        
        return jsonify({"status": "feedback recorded successfully"})
    
    except Exception as e:
        logger.error(f"Error in intent_feedback: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500

@api_bp.route('/refresh-model', methods=['POST'])
def refresh_model():
    """Force a model refresh with the latest training data"""
    try:
        background_thread = threading.Thread(target=refresh_model_async)
        background_thread.daemon = True
        background_thread.start()
        
        return jsonify({"status": "model refresh initiated"})
    except Exception as e:
        logger.error(f"Error initiating model refresh: {str(e)}")
        return jsonify({"error": f"Internal server error: {str(e)}"}), 500