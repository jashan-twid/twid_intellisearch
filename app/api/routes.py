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
        if user_id and es_manager:
            user_prompt = es_manager.generate_system_prompt(user_id=user_id)
            if "Examples:" in user_prompt and len(user_prompt) > 1000:
                model_to_use = get_intent_classifier_model(user_prompt)
                logger.info(f"Using personalized model for user {user_id}")

        from app.services.intent_classifier import classify_intent_direct
        intent_data = classify_intent_direct(model_to_use, query)

        # PAY_TO_PERSON contact lookup
        if (
            intent_data.get("intent") == "PAY_TO_PERSON"
            and user_id and es_manager
            and "payee_name" in intent_data.get("extracted_data", {})
        ):
            payee_name = intent_data["extracted_data"]["payee_name"]
            # Search for contacts in user's contacts index
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
                        # Add array of all matching contacts with name mapping
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