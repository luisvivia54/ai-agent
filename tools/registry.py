"""
Registro de herramientas
========================
Sistema central para registrar, gestionar y ejecutar herramientas del agente.
"""

import importlib
import pkgutil
import traceback
from typing import Any
from tools.base import BaseTool


class ToolRegistry:
    """Registro dinámico de herramientas. Auto-descubre herramientas en el paquete tools/."""

    def __init__(self):
        self._tools: dict[str, BaseTool] = {}
        self._auto_discover()

    # ── Registro ────────────────────────────────────────────────────────────

    def register(self, tool: BaseTool):
        """Registra una herramienta manualmente."""
        self._tools[tool.name] = tool
        print(f"  ✅ Herramienta registrada: {tool.name}")

    def unregister(self, name: str):
        """Elimina una herramienta del registro."""
        if name in self._tools:
            del self._tools[name]
            print(f"  🗑️  Herramienta eliminada: {name}")

    # ── Descubrimiento automático ────────────────────────────────────────────

    def _auto_discover(self):
        """Busca e importa automáticamente todas las herramientas en tools/."""
        import tools as tools_pkg

        for _, module_name, _ in pkgutil.iter_modules(tools_pkg.__path__):
            if module_name in ("base", "registry", "__init__"):
                continue
            try:
                module = importlib.import_module(f"tools.{module_name}")
                # Busca clases que hereden de BaseTool
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (
                        isinstance(attr, type)
                        and issubclass(attr, BaseTool)
                        and attr is not BaseTool
                    ):
                        instance = attr()
                        if instance.enabled:
                            self._tools[instance.name] = instance
            except Exception as e:
                print(f"  ⚠️  No se pudo cargar tools/{module_name}: {e}")

    # ── Ejecución ────────────────────────────────────────────────────────────

    def execute(self, name: str, args: dict) -> str:
        """Ejecuta una herramienta por nombre."""
        if name not in self._tools:
            return f"Error: herramienta '{name}' no encontrada."
        try:
            return str(self._tools[name].run(**args))
        except Exception:
            return f"Error ejecutando {name}:\n{traceback.format_exc()}"

    # ── Consultas ────────────────────────────────────────────────────────────

    def get_openai_tools(self) -> list[dict]:
        """Devuelve el schema de herramientas en el formato que espera OpenAI."""
        return [t.to_openai_schema() for t in self._tools.values()]

    def get_tool_names(self) -> list[str]:
        return list(self._tools.keys())

    def get_all_tools(self) -> dict[str, Any]:
        return {name: {"description": t.description} for name, t in self._tools.items()}
