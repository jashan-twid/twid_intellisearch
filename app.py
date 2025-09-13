from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional
import httpx
import os
import json
from datetime import datetime
import logging

# Internal imports
from models.chat import ChatMessage, ChatResponse, Intent
from services.ai_service import process_message
from services.vector_db import store_chat_history, get_chat_history
from config import settings

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="TWID AI Chat Service")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    user_id: str
    message: str
    session_id: Optional[str] = None
    context: Optional[Dict] = None

@app.post("/api/chat/message", response_model=ChatResponse)
async def chat_message(request: ChatRequest):
    """
    Process a chat message and return a response with intent classification
    """
    try:
        # Process message with AI
        chat_response = await process_message(
            user_id=request.user_id,
            message=request.message,
            session_id=request.session_id,
            context=request.context
        )
        
        # Store chat in vector database for history
        await store_chat_history(
            user_id=request.user_id,
            message=request.message,
            response=chat_response.response,
            intent=chat_response.intent.name,
            session_id=request.session_id
        )
        
        # Call PHP backend if necessary to execute action
        if chat_response.intent.requires_backend_call:
            # Implement PHP service call here
            php_response = await call_php_service(
                intent=chat_response.intent,
                parameters=chat_response.parameters,
                user_id=request.user_id
            )
            # Merge PHP response data with chat response
            chat_response.action_data = php_response.get("data")
            chat_response.deeplink = php_response.get("deeplink")
        
        return chat_response
        
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")

@app.get("/api/chat/history/{user_id}")
async def get_user_chat_history(user_id: str, limit: int = 20):
    """
    Retrieve chat history for a user
    """
    try:
        history = await get_chat_history(user_id, limit=limit)
        return {"history": history}
    except Exception as e:
        logger.error(f"Error retrieving chat history: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error retrieving chat history: {str(e)}")

async def call_php_service(intent, parameters, user_id):
    """
    Call the PHP backend service to execute actions based on intent
    """
    php_endpoint = f"{settings.PHP_SERVICE_URL}/api/ai-actions/execute"
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                php_endpoint,
                json={
                    "intent": intent.name,
                    "parameters": parameters,
                    "user_id": user_id
                },
                headers={
                    "X-API-Key": settings.PHP_SERVICE_API_KEY,
                    "Content-Type": "application/json"
                },
                timeout=10.0
            )
            
            if response.status_code != 200:
                logger.error(f"PHP service error: {response.text}")
                raise HTTPException(status_code=response.status_code, 
                                   detail=f"Backend service error: {response.text}")
                
            return response.json()
    except httpx.RequestError as e:
        logger.error(f"Error communicating with PHP service: {str(e)}")
        raise HTTPException(status_code=503, detail="Service communication error")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)