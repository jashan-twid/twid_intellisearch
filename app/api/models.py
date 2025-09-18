from dataclasses import dataclass, field
from typing import Dict, Any, Optional, List
from datetime import datetime

@dataclass
class IntentData:
    intent: str
    confidence: float
    extracted_data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self):
        return {
            "intent": self.intent,
            "confidence": self.confidence,
            "extracted_data": self.extracted_data
        }

@dataclass
class ChatMessage:
    user_id: str
    query: str
    intent_data: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    is_feedback: bool = False
    
    def to_dict(self):
        return {
            "user_id": self.user_id,
            "query": self.query,
            "intent_data": self.intent_data,
            "timestamp": self.timestamp.isoformat(),
            "is_feedback": self.is_feedback
        }