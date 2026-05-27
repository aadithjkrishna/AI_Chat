import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from api.chat import router as chat_router

app = FastAPI(title="Ollama Chatbot Backend")

app.include_router(chat_router)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.abspath(os.path.join(BASE_DIR, "../frontend"))
CSS_DIR = os.path.join(FRONTEND_DIR, "css")
SCRIPTS_DIR = os.path.join(FRONTEND_DIR, "scripts")

@app.get("/")
async def serve_home():
    return FileResponse(os.path.join(FRONTEND_DIR, "home", "index.html"))


app.mount("/css", StaticFiles(directory=CSS_DIR), name="css")
app.mount("/scripts", StaticFiles(directory=SCRIPTS_DIR), name="scripts")
