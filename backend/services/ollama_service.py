import json
import httpx
from fastapi import HTTPException
from typing import List, Dict

OLLAMA_BASE_URL = "http://localhost:11434"
CHAT_ENDPOINT = "/api/chat"

async def stream_ollama_response(history: List[Dict[str, str]], model_name: str = "llama3.2:3b"):
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
                    raise HTTPException(status_code=500, detail="Failed to communicate with Ollama")
                
                async for line in response.aiter_lines():
                    if line:
                        try:
                            chunk_data = json.loads(line)
                            content = chunk_data.get("message", {}).get("content", "")
                            if content:
                                yield content
                        except json.JSONDecodeError:
                            continue
                            
        except httpx.RequestError as e:
            raise HTTPException(status_code=503, detail=f"Ollama server unreachable: {str(e)}")
