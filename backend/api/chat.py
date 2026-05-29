from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import List, Dict, Any, Optional
import httpx
import pypdf
import io

from services.ollama_service import stream_ollama_response
from services.mcp_service import call_arch_mcp_tool
from services.rag_service import rag_store, chunk_text_or_code

router = APIRouter()

# Allow Any type in history to natively support base64 image strings from multi-modal payloads
class ChatRequest(BaseModel):
    history: List[Dict[str, Any]]     
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
            "description": "Search the Arch User Repository (AUR) for a specific software package.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The exact name of the software package to search for (e.g., 'vlc', 'spotify', 'ffmpeg'). Do not use generic descriptions."
                    }
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

@router.post("/api/upload")
async def upload_and_index_file(file: UploadFile = File(...)):
    """Accepts documents and programming files, parses content into memory buffers, and updates vector context."""
    try:
        filename = file.filename.lower()
        content_text = ""
        
        if filename.endswith(".pdf"):
            # Prevent file stream descriptor loss by reading to an in-memory byte buffer
            pdf_bytes = await file.read()
            pdf_stream = io.BytesIO(pdf_bytes)
            pdf_reader = pypdf.PdfReader(pdf_stream)
            
            for page in pdf_reader.pages:
                text = page.extract_text()
                if text:
                    content_text += text + "\n"
        else:
            # Cleanly decode source files (.txt, .c, .cpp, .h, .java)
            bytes_content = await file.read()
            content_text = bytes_content.decode("utf-8", errors="ignore")

        if not content_text.strip():
            raise HTTPException(status_code=400, detail="The provided file did not yield any parsable plain text characters.")

        # Chunk using your layout-aware split strategies
        chunks = chunk_text_or_code(content_text, filename)
        await rag_store.add_chunks(chunks)
        
        return {"status": "success", "chunks_indexed": len(chunks)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to complete document vector ingestion: {str(e)}")


@router.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest):
    
    # 1. Clean history and explicitly preserve image arrays for multi-modal vision pipelines
    clean_history = []
    for msg in payload.history:
        if msg.get('role') in ['user', 'assistant', 'system', 'tool']:
            cleaned_msg = {
                "role": msg.get("role"),
                "content": msg.get("content", "")
            }
            # Keep base64 image strings attached to the message block if present
            if "images" in msg:
                cleaned_msg["images"] = msg["images"]
            clean_history.append(cleaned_msg)
    
    # 2. Setup highly strict system configuration rules
    if not any(msg.get('role') == 'system' for msg in clean_history):
        clean_history.insert(0, {
            "role": "system", 
            "content": (
                "You are a highly intelligent system control assistant. Chat naturally with Aadith. "
                "You have direct access to uploaded contexts and vision image matrices when provided. "
                "DO NOT run tools to analyze file metadata summaries or images. "
                "Only use your 'search_aur' or 'search_archwiki' tools if explicitly ordered to find a package/instruction configuration."
            )
        })

    # 3. Handle document injection loop (Bypassed if user is sending a visual image stream)
    if clean_history:
        latest_user_msg = clean_history[-1]
        
        # Only inject text documents if there are no image buffers attached to this message turn
        if latest_user_msg.get("role") == "user" and latest_user_msg.get("content") and not latest_user_msg.get("images"):
            user_query = latest_user_msg["content"]
            
            # Catch generic prompts that break high-dimensional cosine matching matrices
            generic_triggers = ["what is this", "analyze this", "summarize this", "read this", "explain this"]
            is_generic = any(trigger in user_query.lower() for trigger in generic_triggers)

            context = ""
            if is_generic and rag_store.documents:
                # Instantly grab the last 3 chunks direct from memory without running vector similarities
                context = "\n\n---\n\n".join(rag_store.documents[-3:])
            else:
                context = await rag_store.query_relevant_context(user_query, top_k=3)
            
            if context:
                latest_user_msg["content"] = (
                    f"Use the following verified document reference context to answer the question.\n"
                    f"Context:\n{context}\n\n"
                    f"User Question: {user_query}"
                )

    async def event_generator():
        async with httpx.AsyncClient() as client:
            try:
                # Evaluates potential function intent across active tools
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

        # 4. Handle tool execution flow
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
            # 5. Route normal token streaming execution (handles vision and text arrays natively)
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