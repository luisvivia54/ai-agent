"""
Webhook de WhatsApp (opcional)
===============================
Servidor Flask para recibir mensajes de WhatsApp y responder con el agente.

Ejecuta: python webhook.py
Expón tu servidor con: ngrok http 5000
Configura la URL del webhook en Meta Business: https://TU-URL/webhook
"""

import json
import os
from flask import Flask, request, jsonify
from agent import AIAgent
from config import Config

app = Flask(__name__)

# Un agente por número (sesiones independientes)
_agents: dict[str, AIAgent] = {}


def get_agent(phone_number: str) -> AIAgent:
    if phone_number not in _agents:
        _agents[phone_number] = AIAgent(session_id=phone_number)
    return _agents[phone_number]


# ── Verificación del webhook (requerido por Meta) ────────────────────────────

@app.route("/webhook", methods=["GET"])
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == Config.WHATSAPP_VERIFY_TOKEN:
        print("✅ Webhook verificado por Meta.")
        return challenge, 200
    return "Token inválido", 403


# ── Recepción de mensajes ────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def receive_message():
    data = request.json
    try:
        entry = data["entry"][0]["changes"][0]["value"]
        message = entry.get("messages", [None])[0]

        if not message or message.get("type") != "text":
            return jsonify({"status": "ignored"}), 200

        from_number = message["from"]
        text = message["text"]["body"]
        print(f"📩 Mensaje de {from_number}: {text}")

        agent = get_agent(from_number)
        reply = agent.chat(text)

        _send_whatsapp_reply(from_number, reply)
        return jsonify({"status": "ok"}), 200

    except (KeyError, IndexError, TypeError) as e:
        print(f"⚠️  Error procesando mensaje: {e}")
        return jsonify({"status": "error"}), 200


def _send_whatsapp_reply(to: str, message: str):
    """Envía una respuesta por WhatsApp."""
    import urllib.request
    import urllib.error

    token = Config.WHATSAPP_TOKEN
    phone_id = Config.WHATSAPP_PHONE_ID

    if not token or not phone_id:
        print("⚠️  WhatsApp no configurado. Respuesta:", message)
        return

    url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
    payload = json.dumps({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": message},
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        urllib.request.urlopen(req)
        print(f"✅ Respuesta enviada a {to}")
    except urllib.error.HTTPError as e:
        print(f"❌ Error enviando respuesta: {e.read().decode()}")


# ── Arranque ─────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    print(f"🚀 Webhook escuchando en puerto {port}")
    print(f"   Configura en Meta: https://TU-DOMINIO/webhook")
    print(f"   Verify Token: {Config.WHATSAPP_VERIFY_TOKEN}\n")
    app.run(host="0.0.0.0", port=port, debug=False)
