import json
import logging
import re
from typing import Dict, Any, Optional, List
from google.generativeai import GenerativeModel
from app.services.elasticsearch_manager import ElasticsearchManager

logger = logging.getLogger(__name__)

def get_intent_classifier_model(system_prompt=None):
    """
    Create and return a Gemini model with the intent classification system prompt.
    
    Args:
        system_prompt: Optional custom system prompt to use
        
    Returns:
        GenerativeModel: Configured Gemini model instance
    """
    if system_prompt is None:
        system_prompt = """
        You are an intent classification system for a financial assistant.
        
        Classify user queries into these intents:
        - PAY_TO_PERSON: For person-to-person payments
        - PAY_BILL: For bill payments (electricity, water, etc.)
        - CHECK_REWARDS: For reward balance or reward-related queries
        - TRANSACTION_HISTORY: For transaction history or status queries
        - OTHER: For any other queries
        
        For PAY_TO_PERSON, extract:
        - payee_name: The person's name
        - amount: The payment amount (in INR)
        - note: Payment reason (if provided)
        
        For PAY_BILL, extract:
        - bill_type: Type of bill (electricity, water, gas, etc.)
        - biller_name: Name of the biller (if provided)
        - amount: The payment amount (if specified)
        
        For CHECK_REWARDS, extract:
        - reward_type: Type of rewards (if specified)
        
        For TRANSACTION_HISTORY, extract:
        - time_period: Time period mentioned (today, yesterday, last week, etc.)
        - transaction_type: Type of transactions (if specified)
        
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
    
    # Create model without system prompt
    model = GenerativeModel(model_name="gemini-2.5-flash")
    
    # Store the system prompt in the model object for later use
    model.system_prompt = system_prompt
    
    return model

def classify_intent(model, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Classify user query intent using Gemini AI
    
    Args:
        model: Gemini model instance
        query: User query text
        context: Optional context information
        
    Returns:
        Dict containing intent classification results
    """
    try:
        # Prepare context information
        user_message = query
        if context:
            context_str = json.dumps(context)
            user_message = f"{query}\nContext information: {context_str}"
        
        # Generate response from Gemini using just the user query
        if hasattr(model, 'system_prompt') and model.system_prompt:
            # If system_prompt is available, prepend it to the message
            # This is a workaround since older versions may not support system_instruction
            full_message = f"""
            System: {model.system_prompt}
            
            User: {user_message}
            """
            response = model.generate_content(full_message)
        else:
            # Fallback if no system_prompt is available
            response = model.generate_content(user_message)
        
        try:
            response_text = response.text if hasattr(response, 'text') else response.parts[0].text
            
            # Log the raw response for debugging
            logger.debug(f"Raw response from Gemini: {response_text}")
            
            # Check for and remove markdown code blocks
            json_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
            markdown_match = re.search(json_pattern, response_text)
            
            if markdown_match:
                # Extract JSON from markdown code block
                clean_json = markdown_match.group(1).strip()
                logger.debug(f"Extracted JSON from markdown: {clean_json}")
                intent_data = json.loads(clean_json)
            else:
                # Try parsing the response directly as JSON
                intent_data = json.loads(response_text.strip())
                
            # Validate response structure
            if not all(k in intent_data for k in ["intent", "confidence", "extracted_data"]):
                raise ValueError("Invalid response structure from Gemini API")
                
            return intent_data
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse Gemini response as JSON: {str(e)}")
            logger.error(f"Response text: {response_text}")
            
            # Fallback response
            return {
                "intent": "OTHER",
                "confidence": 0.5,
                "extracted_data": {},
                "error": "Failed to parse response"
            }
            
    except Exception as e:
        logger.error(f"Error in classify_intent: {str(e)}")
        return {
            "intent": "OTHER",
            "confidence": 0.1,
            "extracted_data": {},
            "error": str(e)
        }

def classify_intent_direct(model, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Classify user query intent directly without feedback loop
    
    Args:
        model: Gemini model instance
        query: User query text
        context: Optional context information
        
    Returns:
        Dict containing intent classification results
    """
    return classify_intent(model, query, context)

def classify_intent_with_feedback(model, es_manager, query: str, 
                                user_id: Optional[str] = None,
                                context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Classify user query intent, save to Elasticsearch, and incorporate feedback
    
    Args:
        model: Gemini model instance
        es_manager: ElasticsearchManager instance
        query: User query text
        user_id: Optional user identifier for personalized data
        context: Optional context information
        
    Returns:
        Dict containing intent classification results
    """
    # First get standard classification
    result = classify_intent(model, query, context)
    
    # Save to Elasticsearch for future training (only if confidence is high)
    if result.get("confidence", 0) > 0.8:
        es_manager.save_example(query, result, user_id=user_id, is_global=False)
    
    # If confidence is low, try with enhanced prompt
    if result.get("confidence", 0) < 0.7:
        try:
            # Create an enhanced prompt with specific guidance for this query type
            enhanced_prompt = f"""
            The user query "{query}" was difficult to classify.
            
            Consider these additional hints:
            - If the query mentions a person's name followed by an amount, it's likely PAY_TO_PERSON
            - Terms like "bill", "payment", "pay for" usually indicate PAY_BILL
            - Words like "points", "cashback", "miles" suggest CHECK_REWARDS
            - References to "history", "statement", "transactions" indicate TRANSACTION_HISTORY
            
            Please reclassify the query with these hints in mind.
            """
            
            # Get improved classification
            if hasattr(model, 'system_prompt') and model.system_prompt:
                # If system_prompt is available, include it with the enhanced prompt
                full_enhanced_prompt = f"""
                System: {model.system_prompt}
                
                User: {enhanced_prompt}
                """
                enhanced_response = model.generate_content(full_enhanced_prompt)
            else:
                enhanced_response = model.generate_content(enhanced_prompt)
            enhanced_text = enhanced_response.text if hasattr(enhanced_response, 'text') else enhanced_response.parts[0].text
            
            # Check for and remove markdown code blocks
            json_pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
            markdown_match = re.search(json_pattern, enhanced_text)
            
            if markdown_match:
                # Extract JSON from markdown code block
                clean_json = markdown_match.group(1).strip()
                enhanced_result = json.loads(clean_json)
            else:
                # Try parsing the response directly as JSON
                enhanced_result = json.loads(enhanced_text.strip())
            
            # Only replace if enhanced result has higher confidence
            if enhanced_result.get("confidence", 0) > result.get("confidence", 0):
                result = enhanced_result
                logger.info(f"Low confidence classification improved: {query}")
        
        except Exception as e:
            logger.error(f"Error in enhanced classification: {str(e)}")
            # Continue with original result if enhancement fails
    
    return result