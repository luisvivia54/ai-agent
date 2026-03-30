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
import base64
import time
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


def _mask_token(token: str) -> str:
    token = (token or "").strip()
    if not token:
        return "VACIO"
    if len(token) <= 24:
        return token[:8] + "..."
    return token[:12] + "..." + token[-8:]


def _strip_bearer(value: str) -> str:
    raw = (value or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _decode_jwt_payload(token: str) -> dict:
    raw = _strip_bearer(token)
    if not raw:
        return {}

    parts = raw.split(".")
    if len(parts) < 2:
        return {}

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        return json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}


def _token_debug_summary(payload: dict) -> dict:
    now = int(time.time())
    exp = payload.get("exp")
    iat = payload.get("iat")
    realm_access = payload.get("realm_access") or {}
    resource_access = payload.get("resource_access") or {}
    realm_roles = realm_access.get("roles") if isinstance(realm_access, dict) else []

    return {
        "iss": payload.get("iss"),
        "azp": payload.get("azp"),
        "aud": payload.get("aud"),
        "sub": payload.get("sub"),
        "preferred_username": payload.get("preferred_username"),
        "client_id": payload.get("clientId") or payload.get("client_id"),
        "realm_roles": realm_roles,
        "has_admin_role": "admin" in [str(r).lower() for r in (realm_roles or [])],
        "resource_access_keys": list(resource_access.keys()) if isinstance(resource_access, dict) else [],
        "issued_at": iat,
        "expires_at": exp,
        "expires_in_seconds": (exp - now) if isinstance(exp, int) else None,
    }


def _probe_backend_admin(headers: dict) -> dict:
    try:
        from tools.tocho5 import BASE_URL

        url = f"{BASE_URL}/api/admin/__authcheck__"
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return {
                "url": url,
                "status": resp.status,
                "body_preview": body[:200],
            }
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        return {
            "url": getattr(e, "url", ""),
            "status": e.code,
            "body_preview": body[:300],
        }
    except Exception as e:
        return {"error": str(e)}


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


# ── Debug Keycloak ────────────────────────────────────────────────────────────

@app.get("/debug/keycloak")
async def debug_keycloak():
    """Diagnóstico de conexión a Keycloak. Quitar en producción."""
    try:
        from keycloak import token_manager
        from tools.tocho5 import STATIC_API_TOKEN, _headers

        static_token = _strip_bearer(STATIC_API_TOKEN)
        keycloak_token = token_manager.get_token()
        auth_source = "static_api_token" if static_token else "keycloak"
        selected_token = static_token or keycloak_token
        payload = _decode_jwt_payload(selected_token)

        return {
            "keycloak_url":  token_manager.url,
            "realm":         token_manager.realm,
            "client_id":     token_manager.client_id,
            "configured":    token_manager.is_configured,
            "static_api_token_present": bool(static_token),
            "keycloak_token_ok": bool(keycloak_token),
            "auth_source_selected": auth_source,
            "selected_token_ok": bool(selected_token),
            "selected_token_preview": _mask_token(selected_token),
            "jwt_payload": _token_debug_summary(payload),
            "backend_admin_probe": _probe_backend_admin(_headers()),
        }
    except Exception as e:
        return {"error": str(e)}


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
