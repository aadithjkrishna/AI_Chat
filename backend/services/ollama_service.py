import json
import httpx
from fastapi import HTTPException
from typing import List, Dict, AsyncGenerator

OLLAMA_BASE_URL = "http://localhost:11434"
CHAT_ENDPOINT = "/api/chat"

async def stream_ollama_response(history: List[Dict[str, str]], model_name: str = "llama3.2:3b") -> AsyncGenerator[str, None]:
    """
    Streams raw token deltas asynchronously from the local Ollama daemon chat completion api,
    ensuring robust parsing for history maps containing native tool invocation contexts.
    """
    payload = {
        "model": model_name,
        "messages": history,          
        "stream": True
    }
    
    headers = {
        "Content-Type": "application/json",
        "Connection": "keep-alive"
    }
    
    async with httpx.AsyncClient(base_url=OLLAMA_BASE_URL, headers=headers) as client:
        try:
            async with client.stream("POST", CHAT_ENDPOINT, json=payload, timeout=60.0) as response:
                if response.status_code != 200:
                    raise HTTPException(status_code=500, detail="Failed to communicate with Ollama daemon service layer.")
                
                async for line in response.aiter_lines():
                    if not line:
                        continue
                        
                    try:
                        chunk_data = json.loads(line)
                        
                        # 🧠 Defensively unpack the data message block layout structure safely
                        message_obj = chunk_data.get("message")
                        if not message_obj:
                            # Handle standard meta chunks (e.g. final stats records block arrays containing 'done': true)
                            continue
                            
                        content = message_obj.get("content", "")
                        if content:
                            yield content
                            
                    except json.JSONDecodeError:
                        # Ignore standard framing anomalies or incomplete trailing buffer artifacts
                        continue
                            
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Ollama server instance currently unreachable: {str(e)}")