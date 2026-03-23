"""
Servidor principal (FastAPI + Webhook WhatsApp)
================================================
Un solo proceso que maneja:
  - Interfaz web en /
  - Chat API en /chat
  - Webhook de WhatsApp en /webhook

Corre con: python -m uvicorn server:app --host 0.0.0.0 --port 8000
"""

import json
import asyncio
import urllib.request
import urllib.error
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent import AIAgent
from config import Config

app = FastAPI(title="Tochero5 AI Agent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Un agente por sesión ─────────────────────────────────────────────────────
_agents: dict[str, AIAgent] = {}

def get_agent(session_id: str = "default") -> AIAgent:
    if session_id not in _agents:
        _agents[session_id] = AIAgent()
    return _agents[session_id]

def _set_session(session_id: str):
    """Setea la sesión activa para que PENDING funcione por número de WhatsApp."""
    try:
        from tools.tocho5 import set_session
        set_session(session_id)
    except Exception:
        pass


# ── Modelos ──────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"


# ── Web UI ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html_path = Path(__file__).parent / "static" / "index.html"
    return html_path.read_text(encoding="utf-8")


# ── Chat API ─────────────────────────────────────────────────────────────────

@app.post("/chat")
async def chat(req: ChatRequest):
    _set_session(req.session_id)
    agent = get_agent(req.session_id)
    reply = await asyncio.to_thread(agent.chat, req.message)
    return {"reply": reply}


@app.post("/reset")
async def reset(req: ChatRequest = None):
    sid = req.session_id if req else "default"
    if sid in _agents:
        _agents[sid].reset()
    return {"status": "ok"}


@app.get("/tools")
async def get_tools():
    agent = get_agent()
    return {"tools": agent.registry.get_all_tools()}


@app.get("/health")
async def health():
    return {"status": "ok", "model": Config.MODEL}


# ── WhatsApp Webhook ─────────────────────────────────────────────────────────

@app.get("/webhook")
async def whatsapp_verify(request: Request):
    params    = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == Config.WHATSAPP_VERIFY_TOKEN:
        print("✅ Webhook de WhatsApp verificado.")
        return HTMLResponse(content=challenge, status_code=200)
    return JSONResponse({"error": "token invalido"}, status_code=403)


@app.post("/webhook")
async def whatsapp_receive(request: Request):
    try:
        data    = await request.json()
        entry   = data["entry"][0]["changes"][0]["value"]
        message = entry.get("messages", [None])[0]

        if not message or message.get("type") != "text":
            return JSONResponse({"status": "ignored"})

        from_number = message["from"]
        text        = message["text"]["body"]
        print(f"📩 WhatsApp de {from_number}: {text}")

        # Sesión única por número de teléfono
        session_id = f"wa_{from_number}"
        _set_session(session_id)
        agent = get_agent(session_id)

        reply = await asyncio.to_thread(agent.chat, text)
        await asyncio.to_thread(_send_whatsapp, from_number, reply)
        return JSONResponse({"status": "ok"})

    except (KeyError, IndexError, TypeError) as e:
        print(f"⚠️  Webhook error: {e}")
        return JSONResponse({"status": "ignored"})


def _send_whatsapp(to: str, message: str):
    token    = Config.WHATSAPP_TOKEN
    phone_id = Config.WHATSAPP_PHONE_ID

    if not token or not phone_id:
        print(f"⚠️  WhatsApp no configurado.")
        return

    # WhatsApp limita mensajes a 1600 chars
    if len(message) > 1600:
        message = message[:1550] + "\n\n_(mensaje truncado)_"

    url     = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }).encode("utf-8")

    req = urllib.request.Request(
        url, data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        urllib.request.urlopen(req, timeout=10)
        print(f"✅ WhatsApp enviado a {to}")
    except urllib.error.HTTPError as e:
        print(f"❌ WhatsApp error: {e.read().decode()}")