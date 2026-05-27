import asyncio
import os
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

VENV_PATH = "/home/aadith/Documents/HTML/web/AI_Chat/backend/.venv/bin"

server_params = StdioServerParameters(
    command=os.path.join(VENV_PATH, "arch-ops-server"),
    args=[],
    env={
        "PATH": f"{VENV_PATH}:/usr/bin:/bin",
    }
)

async def call_arch_mcp_tool(tool_name: str, arguments: dict) -> str:
    try:
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                
                result = await session.call_tool(tool_name, arguments=arguments)
                
                if result.content and len(result.content) > 0:
                    return result.content[0].text
                return "⚙️ Tool completed execution successfully with an empty text trace response."
                
    except Exception as e:
        return f"⚠️ Arch MCP Session Connection Fault: {str(e)}"
