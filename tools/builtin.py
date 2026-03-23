"""
Herramientas de ejemplo: Calculadora y Fecha/Hora
==================================================
Ejemplos simples para mostrar cómo crear herramientas propias.
"""

import math
import datetime
from tools.base import BaseTool


class CalculatorTool(BaseTool):
    name = "calculator"
    description = (
        "Evalúa expresiones matemáticas. Soporta operaciones básicas, "
        "potencias, raíces y funciones matemáticas comunes."
    )
    parameters = {
        "expression": {
            "type": "string",
            "description": "Expresión matemática a evaluar, ej: '2 ** 10', 'math.sqrt(144)'",
        }
    }
    required = ["expression"]

    # Funciones permitidas en la expresión
    _SAFE_GLOBALS = {
        "__builtins__": {},
        "math": math,
        "abs": abs,
        "round": round,
        "min": min,
        "max": max,
        "sum": sum,
        "pow": pow,
    }

    def run(self, expression: str) -> str:
        try:
            result = eval(expression, self._SAFE_GLOBALS)  # noqa: S307
            return f"Resultado: {result}"
        except Exception as e:
            return f"Error al evaluar '{expression}': {e}"


class DateTimeTool(BaseTool):
    name = "get_datetime"
    description = "Obtiene la fecha y hora actual en la zona horaria especificada."
    parameters = {
        "timezone": {
            "type": "string",
            "description": "Zona horaria, ej: 'America/Mexico_City', 'UTC', 'America/New_York'",
        }
    }
    required = []

    def run(self, timezone: str = "America/Mexico_City") -> str:
        try:
            import zoneinfo
            tz = zoneinfo.ZoneInfo(timezone)
            now = datetime.datetime.now(tz)
            return f"Fecha y hora en {timezone}: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        except Exception:
            now = datetime.datetime.utcnow()
            return f"Fecha y hora UTC: {now.strftime('%Y-%m-%d %H:%M:%S')} (zona horaria no encontrada)"
