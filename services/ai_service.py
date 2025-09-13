import os
import json
from typing import Dict, List, Optional
import logging
import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold

from models.chat import ChatResponse, Intent, ActionParameter
from config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configure Gemini API
genai.configure(api_key=settings.GEMINI_API_KEY)
model = genai.GenerativeModel(
    model_name="gemini-pro",
    safety_settings={
        HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
        HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    }
)

# Define prompts
SYSTEM_PROMPT = """
You are a helpful TWID financial assistant. Your goal is to help users with payments, bills, and rewards.
Extract the user's intent from their message and categorize it into one of these categories:
1. PAY_TO_PERSON - When user wants to send money to a contact
2. PAY_BILL - When user wants to pay a utility bill
3. CHECK_REWARDS - When user asks about their rewards or cashback
4. TRANSACTION_HISTORY - When user asks about past transactions
5. GENERAL_QUERY - For general questions

For each intent, extract the relevant parameters:
- PAY_TO_PERSON: amount, recipient_name, purpose
- PAY_BILL: bill_type, amount (if specified)
- CHECK_REWARDS: time_period (if specified)
- TRANSACTION_HISTORY: time_period, category (if specified)

Respond with a JSON object in this format:
{
  "intent": "INTENT_NAME",
  "parameters": {
    "param1": "value1",
    "param2": "value2"
  },
  "response": "Human friendly response",
  "requires_backend_call": true/false
}
"""

async def process_message(user_id: str, message: str, session_id: Optional[str] = None, 
                          context: Optional[Dict] = None) -> ChatResponse:
    """
    Process user message with Gemini AI and return structured response
    """
    try:
        # Create conversation with history if provided
        chat = model.start_chat(history=[])
        
        # Add system prompt
        chat.send_message(SYSTEM_PROMPT)
        
        # Add context if available (could be previous messages)
        if context and context.get("history"):
            for msg in context["history"]:
                if msg["role"] == "user":
                    chat.send_message(msg["content"])
                elif msg["role"] == "assistant":
                    # Just logging here - we don't send assistant messages to Gemini
                    logger.info(f"Including assistant message in context: {msg['content'][:50]}...")
        
        # Send user message and get response
        response = chat.send_message(message)
        
        # Parse Gemini response
        try:
            # The response may contain a JSON string inside the text
            response_text = response.text
            
            # Try to extract JSON if it's wrapped in text
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                ai_response = json.loads(json_str)
            else:
                # Fallback if no JSON detected
                logger.warning(f"No JSON detected in response: {response_text[:100]}...")
                ai_response = {
                    "intent": "GENERAL_QUERY",
                    "parameters": {},
                    "response": response_text,
                    "requires_backend_call": False
                }
        except json.JSONDecodeError:
            logger.error(f"Failed to parse JSON from response: {response_text[:100]}...")
            ai_response = {
                "intent": "GENERAL_QUERY",
                "parameters": {},
                "response": response_text,
                "requires_backend_call": False
            }
        
        # Create structured response
        intent = Intent(
            name=ai_response["intent"],
            requires_backend_call=ai_response.get("requires_backend_call", False)
        )
        
        parameters = []
        for key, value in ai_response.get("parameters", {}).items():
            parameters.append(ActionParameter(name=key, value=value))
        
        return ChatResponse(
            response=ai_response["response"],
            intent=intent,
            parameters=parameters
        )
    
    except Exception as e:
        logger.error(f"Error in AI processing: {str(e)}")
        # Return fallback response
        return ChatResponse(
            response="I'm sorry, I encountered an error processing your request. Please try again.",
            intent=Intent(name="ERROR", requires_backend_call=False),
            parameters=[]
        )