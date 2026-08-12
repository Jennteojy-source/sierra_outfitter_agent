"""Sierra Outfitters agent API — FastAPI + in-memory sessions."""

from __future__ import annotations

import base64
import mimetypes
import os
import uuid
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from server.agent import run_agent, run_nudge
from server.ratings import save_rating

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
session_meta: dict[str, dict[str, Any]] = {}

ASSETS_DIR = ROOT / "assets"
MAX_IMAGE_BYTES = 8 * 1024 * 1024


def _idle_seconds() -> int:
    raw = os.getenv("NUDGE_IDLE_SECONDS", "300")
    try:
        return max(5, min(int(raw), 3600))
    except ValueError:
        return 300


def _fresh_meta() -> dict[str, Any]:
    return {
        "nudged": False,
        "rated": False,
        "handed_off": False,
        "handoff_reason": None,
    }


class HistoryResponse(BaseModel):
    session_id: str
    messages: list[dict[str, Any]]
    handed_off: bool = False
    nudged: bool = False
    rated: bool = False


class ChatResponse(BaseModel):
    session_id: str
    message: str
    products: list[dict[str, Any]] | None = None
    handed_off: bool = False
    muted: bool = False
    kind: str | None = None


class ResetResponse(BaseModel):
    session_id: str
    ok: bool = True
    handed_off: bool = False
    nudged: bool = False


class ConfigResponse(BaseModel):
    nudge_idle_seconds: int


class NudgeResponse(BaseModel):
    session_id: str
    message: str | None = None
    already_sent: bool = False
    skipped: bool = False
    reason: str | None = None


class RatingRequest(BaseModel):
    rating: Literal["up", "down", "skip"]
    comment: str | None = Field(default=None, max_length=500)


class RatingResponse(BaseModel):
    session_id: str
    ok: bool = True
    already_rated: bool = False


def _ensure_session(session_id: str | None) -> str:
    sid = session_id.strip() if session_id else ""
    if not sid:
        sid = str(uuid.uuid4())
    sessions.setdefault(sid, [])
    ui_sessions.setdefault(sid, [])
    session_meta.setdefault(sid, _fresh_meta())
    return sid


def _meta(sid: str) -> dict[str, Any]:
    return session_meta.setdefault(sid, _fresh_meta())


def _has_exchange(sid: str) -> bool:
    ui = ui_sessions.get(sid, [])
    has_user = any(m.get("role") == "user" for m in ui)
    has_asst = any(m.get("role") == "assistant" for m in ui)
    return has_user and has_asst


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


@app.get("/api/config", response_model=ConfigResponse)
def get_config() -> ConfigResponse:
    return ConfigResponse(nudge_idle_seconds=_idle_seconds())


@app.get("/api/history", response_model=HistoryResponse)
def get_history(x_session_id: str | None = Header(default=None)) -> HistoryResponse:
    sid = _ensure_session(x_session_id)
    meta = _meta(sid)
    return HistoryResponse(
        session_id=sid,
        messages=ui_sessions.get(sid, []),
        handed_off=bool(meta.get("handed_off")),
        nudged=bool(meta.get("nudged")),
        rated=bool(meta.get("rated")),
    )


@app.post("/api/reset", response_model=ResetResponse)
def reset(x_session_id: str | None = Header(default=None)) -> ResetResponse:
    old = x_session_id.strip() if x_session_id else ""
    if old:
        sessions.pop(old, None)
        ui_sessions.pop(old, None)
        session_meta.pop(old, None)
    sid = str(uuid.uuid4())
    sessions[sid] = []
    ui_sessions[sid] = []
    session_meta[sid] = _fresh_meta()
    return ResetResponse(session_id=sid, ok=True, handed_off=False, nudged=False)


@app.post("/api/nudge", response_model=NudgeResponse)
def nudge(x_session_id: str | None = Header(default=None)) -> NudgeResponse:
    sid = _ensure_session(x_session_id)
    meta = _meta(sid)

    if meta.get("handed_off"):
        return NudgeResponse(session_id=sid, skipped=True, reason="handed_off")
    if not _has_exchange(sid):
        return NudgeResponse(session_id=sid, skipped=True, reason="no_exchange")

    if meta.get("nudged"):
        existing = next(
            (m for m in reversed(ui_sessions[sid]) if m.get("kind") == "nudge"),
            None,
        )
        return NudgeResponse(
            session_id=sid,
            message=(existing or {}).get("content"),
            already_sent=True,
        )

    try:
        text, updated = run_nudge(sessions[sid])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sessions[sid] = updated
    meta["nudged"] = True
    ui_sessions[sid].append(
        {
            "role": "assistant",
            "content": text,
            "kind": "nudge",
        }
    )
    return NudgeResponse(session_id=sid, message=text, already_sent=False)


@app.post("/api/rating", response_model=RatingResponse)
def submit_rating(
    body: RatingRequest,
    x_session_id: str | None = Header(default=None),
) -> RatingResponse:
    sid = _ensure_session(x_session_id)
    meta = _meta(sid)
    if meta.get("rated"):
        return RatingResponse(session_id=sid, ok=True, already_rated=True)

    nudge_msg = next(
        (m for m in reversed(ui_sessions.get(sid, [])) if m.get("kind") == "nudge"),
        None,
    )
    transcript = [
        {"role": m.get("role"), "content": m.get("content"), "kind": m.get("kind")}
        for m in ui_sessions.get(sid, [])
        if m.get("role") in ("user", "assistant")
    ]
    save_rating(
        {
            "session_id": sid,
            "rating": body.rating,
            "comment": (body.comment or "").strip() or None,
            "nudge_text": (nudge_msg or {}).get("content"),
            "transcript": transcript,
        }
    )
    meta["rated"] = True
    return RatingResponse(session_id=sid, ok=True, already_rated=False)


@app.post("/api/chat", response_model=ChatResponse)
async def chat(
    message: str = Form(default=""),
    x_session_id: str | None = Header(default=None),
    image: UploadFile | None = File(default=None),
) -> ChatResponse:
    sid = _ensure_session(x_session_id)
    meta = _meta(sid)

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

    ui_sessions[sid].append(
        {
            "role": "user",
            "content": message.strip(),
            "image": image_preview,
        }
    )

    if meta.get("handed_off"):
        return ChatResponse(
            session_id=sid,
            message="",
            handed_off=True,
            muted=True,
            kind=None,
        )

    user_content = _build_user_content(message, image_b64, image_mime)
    user_msg = {"role": "user", "content": user_content}

    try:
        assistant_text, updated, products, flags = run_agent(sessions[sid], user_msg)
    except Exception as exc:  # noqa: BLE001 — surface cleanly to UI
        ui_sessions[sid].pop()
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    sessions[sid] = updated
    handed_off = bool(flags.get("handed_off"))
    kind = "handoff" if handed_off else None
    if handed_off:
        meta["handed_off"] = True
        meta["handoff_reason"] = flags.get("handoff_reason")
        meta["nudged"] = True  # do not idle-nudge after a live handoff

    ui_sessions[sid].append(
        {
            "role": "assistant",
            "content": assistant_text,
            "products": products,
            "kind": kind,
        }
    )

    return ChatResponse(
        session_id=sid,
        message=assistant_text,
        products=products,
        handed_off=handed_off,
        muted=handed_off,
        kind=kind,
    )


@app.get("/assets/{filename}")
def serve_asset(filename: str) -> FileResponse:
    path = ASSETS_DIR / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Asset not found")
    return FileResponse(path)


if ASSETS_DIR.is_dir():
    app.mount("/static-assets", StaticFiles(directory=str(ASSETS_DIR)), name="static-assets")
