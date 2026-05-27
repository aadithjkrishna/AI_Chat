from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict
import httpx

from services.ollama_service import stream_ollama_response
from services.mcp_service import call_arch_mcp_tool

router = APIRouter()

class ChatRequest(BaseModel):
    history: List[Dict[str, str]]     
    model: str = "llama3.2:3b"

ARCH_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_system_info",
            "description": "Get general system indexing status, local library metrics, and cached record metadata blocks."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_aur",
            "description": "Search the local cache, remote tracking nodes, or trigger download sequences for explicit media assets.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The exact media query matching text or track patterns."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_archwiki",
            "description": "Query documentation records or systemic instructions regarding media infrastructure configurations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The targeted configuration keyword string parameter."}
                },
                "required": ["query"]
            }
        }
    }
]

@router.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest):
    
    clean_history = [msg for msg in payload.history if msg.get('role') in ['user', 'assistant', 'system', 'tool']]
    
    if not any(msg.get('role') == 'system' for msg in clean_history):
        clean_history.insert(0, {
            "role": "system", 
            "content": "You are a highly intelligent system control assistant. Chat naturally with Aadith. If a query requires searching, processing, or retrieving media assets, invoke your tools dynamically."
        })

    async def event_generator():
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    "http://localhost:11434/api/chat",
                    json={
                        "model": payload.model,
                        "messages": clean_history,
                        "tools": ARCH_TOOLS,
                        "stream": False
                    },
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                message = data.get("message", {})
            except Exception as e:
                yield f"data: ⚠️ Error evaluating intent via Ollama daemon: {str(e)}\n\n"
                return

        if "tool_calls" in message and message["tool_calls"]:
            tool_call = message["tool_calls"][0]["function"]
            target_tool = tool_call["name"]
            tool_args = tool_call.get("arguments", {})

            param_display = f" with arguments {tool_args}" if tool_args else ""
            yield f"data: ⚙️ *Arch-MCP Server: Using`{target_tool}` {param_display}...*\n\n"

            terminal_output = await call_arch_mcp_tool(target_tool, tool_args)

            execution_history = list(clean_history)
            execution_history.append(message)
        
            execution_history.append({
                "role": "tool",
                "name": target_tool,
                "content": str(terminal_output)
            })

            async for text_chunk in stream_ollama_response(execution_history, payload.model):
                yield f"data: {text_chunk}\n\n"

        else:
            async for text_chunk in stream_ollama_response(clean_history, payload.model):
                yield f"data: {text_chunk}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/api/models")
async def get_ollama_models():
    """Fetches the complete catalog list of local engine runtimes available."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get("http://localhost:11434/api/tags", timeout=5.0)
            response.raise_for_status()
            data = response.json()
            
            model_names = [model["name"] for model in data.get("models", [])]
            return {"models": model_names if model_names else ["llama3.2:3b"]}
            
    except Exception as e:
        print(f"⚠️ Error querying background tags endpoint: {str(e)}")
        return {"models": ["llama3.2:3b"]}