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
            "description": "Get general system information including kernel, memory, and uptime."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_updates_dry_run",
            "description": "Check if there are any Arch Linux system updates available."
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_aur",
            "description": "Search the Arch User Repository (AUR) for a specific package.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The name of the package"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_archwiki",
            "description": "Search the Arch Wiki for guides, errors, or documentation.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The topic to search for"}
                },
                "required": ["query"]
            }
        }
    }
]

@router.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest):
    
    clean_history = [msg for msg in payload.history if msg['role'] in ['user', 'assistant', 'system', 'tool']]
    
    if not any(msg['role'] == 'system' for msg in clean_history):
        clean_history.insert(0, {
            "role": "system", 
            "content": "You are a highly intelligent Arch Linux assistant. Chat naturally with the user. If they ask a question that requires system data, search, or updates, use your available tools."
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
                data = response.json()
                message = data.get("message", {})
            except Exception as e:
                yield f"data: ⚠️ Error communicating with Ollama: {str(e)}\n\n"
                return

        if "tool_calls" in message and message["tool_calls"]:
            tool_call = message["tool_calls"][0]["function"]
            target_tool = tool_call["name"]
            tool_args = tool_call.get("arguments", {})

            param_display = f" with args {tool_args}" if tool_args else ""
            yield f"data: ⚙️ *Arch-MCP Server: Invoking `{target_tool}`{param_display}...*\n\n"

            terminal_output = await call_arch_mcp_tool(target_tool, tool_args)

            clean_history.append(message)
            clean_history.append({
                "role": "tool",
                "content": str(terminal_output)
            })

            async for text_chunk in stream_ollama_response(clean_history, payload.model):
                yield f"data: {text_chunk}\n\n"

        else:
            async for text_chunk in stream_ollama_response(clean_history, payload.model):
                yield f"data: {text_chunk}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")