"""Sierra Outfitters agent API — FastAPI + in-memory sessions."""

from __future__ import annotations

import base64
import mimetypes
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.agent import run_agent

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

app = FastAPI(title="Sierra Outfitters Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# session_id -> OpenAI-style message list (user/assistant/tool)
sessions: dict[str, list[dict[str, Any]]] = {}
# session_id -> UI-friendly messages for the frontend
ui_sessions: dict[str, list[dict[str, Any]]] = {}

ASSETS_DIR = ROOT / "assets"
MAX_IMAGE_BYTES = 8 * 1024 * 1024


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[dict[str, Any]]


class ChatResponse(BaseModel):
    session_id: str
    message: str
    products: list[dict[str, Any]] | None = None


class ResetResponse(BaseModel):
    session_id: str
    ok: bool = True


def _ensure_session(session_id: str | None) -> str:
    sid = session_id.strip() if session_id else ""
    if not sid:
        sid = str(uuid.uuid4())
    sessions.setdefault(sid, [])
    ui_sessions.setdefault(sid, [])
    return sid


def _build_user_content(text: str, image_b64: str | None, image_mime: str | None) -> Any:
    text = (text or "").strip()
    if not image_b64:
        return text or "Hello"
    parts: list[dict[str, Any]] = []
    parts.append(
        {
            "type": "text",
            "text": text or "Please look at this image and help me.",
        }
    )
    parts.append(
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_mime or 'image/png'};base64,{image_b64}",
            },
        }
    )
    return parts


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/history", response_model=HistoryResponse)
def get_history(x_session_id: str | None = Header(default=None)) -> HistoryResponse:
    sid = _ensure_session(x_session_id)
    return HistoryResponse(session_id=sid, messages=ui_sessions.get(sid, []))


@app.post("/api/reset", response_model=ResetResponse)
def reset(x_session_id: str | None = Header(default=None)) -> ResetResponse:
    sid = _ensure_session(x_session_id)
    sessions[sid] = []
    ui_sessions[sid] = []
    return ResetResponse(session_id=sid)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(default=""),
    x_session_id: str | None = Header(default=None),
    image: UploadFile | None = File(default=None),
) -> ChatResponse:
    sid = _ensure_session(x_session_id)

    image_b64 = None
    image_mime = None
    image_preview = None
    if image is not None and image.filename:
        data = await image.read()
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(status_code=400, detail="Image too large (max 8MB)")
        image_mime = image.content_type or mimetypes.guess_type(image.filename)[0] or "image/png"
        if not image_mime.startswith("image/"):
            raise HTTPException(status_code=400, detail="Only image uploads are supported")
        image_b64 = base64.b64encode(data).decode("ascii")
        image_preview = f"data:{image_mime};base64,{image_b64}"

    if not message.strip() and not image_b64:
        raise HTTPException(status_code=400, detail="Send a message or an image")

    user_content = _build_user_content(message, image_b64, image_mime)
    user_msg = {"role": "user", "content": user_content}

    try:
        assistant_text, updated, products = run_agent(sessions[sid], user_msg)
    except Exception as exc:  # noqa: BLE001 — surface cleanly to UI
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sessions[sid] = updated

    ui_sessions[sid].append(
        {
            "role": "user",
            "content": message.strip(),
            "image": image_preview,
        }
    )
    ui_sessions[sid].append(
        {
            "role": "assistant",
            "content": assistant_text,
            "products": products,
        }
    )

    return ChatResponse(session_id=sid, message=assistant_text, products=products)


@app.get("/assets/{filename}")
def serve_asset(filename: str) -> FileResponse:
    path = ASSETS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path)


# Optional: also mount full assets dir
if ASSETS_DIR.is_dir():
    app.mount("/static-assets", StaticFiles(directory=str(ASSETS_DIR)), name="static-assets")
