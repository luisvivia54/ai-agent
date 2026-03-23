"""
Plantilla para crear una nueva herramienta
==========================================
Copia este archivo a tools/mi_herramienta.py y personalízalo.
La herramienta se registrará automáticamente al iniciar el agente.
"""

import os
from tools.base import BaseTool


class MiHerramienta(BaseTool):
    # ── Metadatos (OpenAI los lee para decidir cuándo usar la herramienta) ──
    name = "mi_herramienta"                          # Snake_case, único
    description = (
        "Describe claramente qué hace esta herramienta y cuándo usarla. "
        "OpenAI usa esta descripción para decidir si invocarla."
    )

    # ── Parámetros que acepta la herramienta ────────────────────────────────
    parameters = {
        "param1": {
            "type": "string",
            "description": "Descripción del primer parámetro",
        },
        "param2": {
            "type": "number",
            "description": "Descripción del segundo parámetro (opcional)",
        },
        "param3": {
            "type": "string",
            "enum": ["opcion_a", "opcion_b", "opcion_c"],
            "description": "Parámetro con valores permitidos",
        },
    }
    required = ["param1"]          # Lista de parámetros obligatorios

    # ── Descomenta para desactivar la herramienta sin borrar el archivo ─────
    # enabled = False

    # ── Activa condicionalmente según config (buena práctica) ───────────────
    # @property
    # def enabled(self) -> bool:
    #     return bool(os.getenv("MI_API_KEY"))

    # ── Lógica principal ────────────────────────────────────────────────────
    def run(self, param1: str, param2: float = 0.0, param3: str = "opcion_a") -> str:
        """
        Implementa aquí la lógica de tu herramienta.
        Siempre retorna un string descriptivo del resultado.
        """
        # Ejemplo de llamada a una API externa:
        # import urllib.request, json
        # url = f"https://api.ejemplo.com/endpoint?q={param1}"
        # with urllib.request.urlopen(url) as r:
        #     data = json.loads(r.read())
        # return f"Resultado: {data['resultado']}"

        return f"Herramienta ejecutada con param1={param1}, param2={param2}, param3={param3}"
