from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict
import re

from services.ollama_service import stream_ollama_response
from services.mcp_service import call_arch_mcp_tool

router = APIRouter()

class ChatRequest(BaseModel):
    history: List[Dict[str, str]]     
    model: str = "llama3.2:3b"

@router.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest):
    
    payload.history = [msg for msg in payload.history if msg['role'] != 'system']
    
    last_user_msg = payload.history[-1]["content"].lower()
    
    command_triggers = ["run", "execute", "neofetch", "fastfetch", "ls", "terminal", "pacman", "system", "update", "upgrade", "disk"]
    is_command_request = any(trigger in last_user_msg for trigger in command_triggers)
    
    if is_command_request:
        system_directive = (
            "You are an active terminal agent. The user wants to execute a system command. "
            "Output your intent using this exact layout: [RUN: command_here]. "
            "Do not output any introductory or concluding text."
        )
    else:
        system_directive = (
            "You are a helpful, friendly AI assistant chatting naturally with Aadith. "
            "Answer the user's questions directly. Do NOT use any bracket commands like [RUN: ...]."
        )
        
    payload.history.insert(0, {"role": "system", "content": system_directive})

    async def event_generator():
        collected_text = ""
        command_intercepted = False
        command_to_run = ""

        async for text_chunk in stream_ollama_response(payload.history, payload.model):
            collected_text += text_chunk
            
            match = re.search(r"\[RUN:\s*([^\]\n]+)", collected_text)
            if match and not command_intercepted:
                command_to_run = match.group(1).replace("]", "").strip().lower()
                command_intercepted = True
                break
            
            yield f"data: {text_chunk}\n\n"
        if command_intercepted and command_to_run:
            
            target_tool = "get_system_info"
            tool_args = {}
            
            if any(k in command_to_run for k in ["fastfetch", "neofetch", "system", "info"]):
                target_tool = "get_system_info"
            elif any(k in command_to_run for k in ["update", "upgrade", "pacman"]):
                target_tool = "check_updates_dry_run"
            elif any(k in command_to_run for k in ["disk", "space", "storage"]):
                target_tool = "check_disk_space"
            elif "news" in command_to_run:
                target_tool = "get_latest_news"
            
            yield f"data: ⚙️ *Arch-MCP Server: Invoking structured tool `{target_tool}`...*\n\n"
            terminal_output = await call_arch_mcp_tool(target_tool, tool_args)
            payload.history = [msg for msg in payload.history if msg['role'] != 'system']
            
            summary_directive = (
                "You are a helpful UI chat assistant. Read the technical data payload provided below "
                "and explain the contents clearly to Aadith. Use clean Markdown bullet points. "
                "Do NOT under any circumstances output any brackets like [RUN: ...] or system tags."
            )
            payload.history.insert(0, {"role": "system", "content": summary_directive})
            
            payload.history.append({"role": "assistant", "content": f"Invoked tool execution tracker for `{target_tool}`."})
            payload.history.append({
                "role": "user", 
                "content": f"The system tool returned this raw data profile:\n\n{terminal_output}\n\nSummarize this for me right now."
            })
            
            has_content = False
            async for text_chunk in stream_ollama_response(payload.history, payload.model):
                has_content = True
                yield f"data: {text_chunk}\n\n"
                
            if not has_content:
                formatted_fallback = terminal_output.replace("\n", "\n\n")
                yield f"data: 📊 **Direct System Log Trace Output:**\n\n{formatted_fallback}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
