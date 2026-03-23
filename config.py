"""
Configuración del agente
========================
Edita este archivo para ajustar el comportamiento del agente.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # ── OpenAI ──────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    MODEL: str = os.getenv("MODEL", "gpt-4o")          # gpt-4o | gpt-4o-mini | gpt-4-turbo

    # ── WhatsApp (Meta Cloud API) ────────────────────────────────────────────
    WHATSAPP_TOKEN: str = os.getenv("WHATSAPP_TOKEN", "")
    WHATSAPP_PHONE_ID: str = os.getenv("WHATSAPP_PHONE_ID", "")
    WHATSAPP_VERIFY_TOKEN: str = os.getenv("WHATSAPP_VERIFY_TOKEN", "mi_token_secreto")

    # ── Personalidad del agente ──────────────────────────────────────────────
    SYSTEM_PROMPT: str = """
Eres el asistente oficial de la liga de futbol americano Tochero5.
Tienes acceso a herramientas para consultar equipos, partidos, tabla de posiciones y estadísticas.

Reglas de comportamiento:
- Usa herramientas cuando sea necesario para dar respuestas precisas y actualizadas.
- Responde siempre en español.
- Nunca muestres JSON crudo al usuario, siempre interpreta y formatea los datos.
- Si una herramienta falla, explica el problema con claridad y sugiere alternativas.
- Si hay más de 15 resultados en una lista, muestra solo los primeros 10 y pregunta si quiere ver más.

Reglas de formato:
- Equipos en tabla: columnas Nombre e ID. Si tiene logo, menciona que existe.
- Partidos: formato "Local vs Visitante · Fecha · Jornada · Estado"
- Tabla de posiciones: ordenada por puntos de mayor a menor, con columnas Pos | Equipo | PJ | PG | PP | Pts
- Estadísticas de jugadores: tabla con Pos | Jugador | Equipo | Goles | Asistencias
- Usa emojis con moderación para hacer la respuesta más legible: 🏈 partidos, 🏆 tabla, 👥 equipos, ⚽ goles
""".strip()