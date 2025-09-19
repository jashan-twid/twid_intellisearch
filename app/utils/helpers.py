import re
import json
from typing import Dict, Any, List, Optional

def sanitize_input(text: str) -> str:
    """
    Sanitize user input text
    
    Args:
        text: Input text to sanitize
        
    Returns:
        Sanitized text
    """
    # Remove any potential script injections
    text = re.sub(r'<script.*?>.*?</script>', '', text, flags=re.DOTALL)
    
    # Remove other HTML tags
    text = re.sub(r'<.*?>', '', text)
    
    # Trim whitespace
    text = text.strip()
    
    return text

def extract_amount(text: str) -> Optional[float]:
    """
    Extract monetary amount from text
    
    Args:
        text: Text containing amount
        
    Returns:
        Extracted amount as float or None if not found
    """
    # Match patterns like ₹500, Rs. 500, 500 rupees, etc.
    patterns = [
        r'₹\s*(\d+(?:\.\d+)?)',
        r'Rs\.?\s*(\d+(?:\.\d+)?)',
        r'(\d+(?:\.\d+)?)\s*(?:rupees|rs\.?)',
        r'(\d+(?:\.\d+)?)\s*(?:inr)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return float(match.group(1))
    
    return None

def extract_contact_name(text: str) -> Optional[str]:
    """
    Extract contact name from text
    
    Args:
        text: Text containing contact name
        
    Returns:
        Extracted contact name or None if not found
    """
    # Simple extraction for demo purposes
    # In a real app, this would be more sophisticated
    patterns = [
        r'to\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)',
        r'pay\s+([A-Za-z]+(?:\s+[A-Za-z]+)?)'
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    
    return None

def format_response(intent_data: Dict[str, Any], deeplink: Optional[str] = None) -> Dict[str, Any]:
    """
    Format response for client
    
    Args:
        intent_data: Intent classification data
        deeplink: Optional deeplink for direct action
        
    Returns:
        Formatted response
    """
    response = {
        "intent": intent_data.get("intent"),
        "confidence": intent_data.get("confidence"),
        "extracted_data": intent_data.get("extracted_data", {}),
    }
    
    if deeplink:
        response["deeplink"] = deeplink
        
    return response