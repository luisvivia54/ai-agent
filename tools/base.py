"""
Clase base para herramientas
=============================
Todas las herramientas deben heredar de BaseTool.
"""

from abc import ABC, abstractmethod


class BaseTool(ABC):
    """
    Clase base para todas las herramientas del agente.

    Para crear una herramienta nueva:
    1. Crea un archivo en tools/
    2. Hereda de BaseTool
    3. Define name, description, parameters y el método run()
    4. Se registrará automáticamente al iniciar el agente.

    Ejemplo mínimo:
    ---------------
    class MiHerramienta(BaseTool):
        name = "mi_herramienta"
        description = "Hace algo útil"
        parameters = {
            "texto": {
                "type": "string",
                "description": "Texto de entrada",
            }
        }
        required = ["texto"]

        def run(self, texto: str) -> str:
            return texto.upper()
    """

    name: str = ""
    description: str = ""
    parameters: dict = {}      # Propiedades de los parámetros (OpenAI format)
    required: list[str] = []   # Parámetros obligatorios
    enabled: bool = True       # Pon False para desactivar sin borrar el archivo

    @abstractmethod
    def run(self, **kwargs) -> str:
        """Lógica principal de la herramienta. Siempre retorna str."""
        ...

    def to_openai_schema(self) -> dict:
        """Convierte la herramienta al formato JSON Schema de OpenAI."""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": self.required,
                },
            },
        }
