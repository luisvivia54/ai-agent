"""
Herramienta: WhatsApp (Meta Cloud API)
======================================
Permite al agente enviar mensajes de WhatsApp.
Requiere: WHATSAPP_TOKEN y WHATSAPP_PHONE_ID en .env
"""

import json
import os
import urllib.request
import urllib.error
from tools.base import BaseTool


class WhatsAppTool(BaseTool):
    name = "whatsapp_send_message"
    description = (
        "Envía un mensaje de WhatsApp a un número de teléfono. "
        "Úsala cuando el usuario quiera mandar un mensaje por WhatsApp."
    )
    parameters = {
        "to": {
            "type": "string",
            "description": "Número de teléfono destino en formato internacional, ej: 525512345678",
        },
        "message": {
            "type": "string",
            "description": "Texto del mensaje a enviar",
        },
    }
    required = ["to", "message"]

    # ── Activa la herramienta sólo si las credenciales están configuradas ──
    @property
    def enabled(self) -> bool:
        return bool(os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_ID"))

    def run(self, to: str, message: str) -> str:
        token = os.getenv("WHATSAPP_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_ID")

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
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                msg_id = data.get("messages", [{}])[0].get("id", "N/A")
                return f"✅ Mensaje enviado a {to}. ID: {msg_id}"
        except urllib.error.HTTPError as e:
            body = e.read().decode()
            return f"❌ Error HTTP {e.code}: {body}"
        except Exception as e:
            return f"❌ Error: {e}"


class WhatsAppTemplateTool(BaseTool):
    """Envía un template pre-aprobado de WhatsApp (útil para notificaciones)."""

    name = "whatsapp_send_template"
    description = (
        "Envía un mensaje template de WhatsApp. Útil para notificaciones y mensajes "
        "estructurados que deben seguir un formato pre-aprobado por Meta."
    )
    parameters = {
        "to": {
            "type": "string",
            "description": "Número destino en formato internacional",
        },
        "template_name": {
            "type": "string",
            "description": "Nombre del template aprobado en Meta Business",
        },
        "language_code": {
            "type": "string",
            "description": "Código de idioma del template, ej: es_MX, en_US",
        },
    }
    required = ["to", "template_name", "language_code"]

    @property
    def enabled(self) -> bool:
        return bool(os.getenv("WHATSAPP_TOKEN") and os.getenv("WHATSAPP_PHONE_ID"))

    def run(self, to: str, template_name: str, language_code: str = "es_MX") -> str:
        token = os.getenv("WHATSAPP_TOKEN")
        phone_id = os.getenv("WHATSAPP_PHONE_ID")

        url = f"https://graph.facebook.com/v19.0/{phone_id}/messages"
        payload = json.dumps({
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=payload,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(req) as resp:
                data = json.loads(resp.read())
                msg_id = data.get("messages", [{}])[0].get("id", "N/A")
                return f"✅ Template '{template_name}' enviado a {to}. ID: {msg_id}"
        except urllib.error.HTTPError as e:
            return f"❌ Error HTTP {e.code}: {e.read().decode()}"
        except Exception as e:
            return f"❌ Error: {e}"
