"""
AI Agent con OpenAI - Sistema modular de herramientas
======================================================
Agente principal que maneja la conversación y ejecuta herramientas.
"""

import json
import os
from openai import OpenAI
from tools.registry import ToolRegistry
from config import Config


class AIAgent:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.registry = ToolRegistry()
        self.conversation_history = []
        self.model = Config.MODEL

        print(f"\n🤖 Agente iniciado con modelo: {self.model}")
        print(f"🔧 Herramientas cargadas: {', '.join(self.registry.get_tool_names()) or 'ninguna'}\n")

    def chat(self, user_message: str) -> str:
        """Envía un mensaje y obtiene respuesta, ejecutando herramientas si es necesario."""
        self.conversation_history.append({"role": "user", "content": user_message})

        response = self._call_openai()

        # Loop de herramientas: ejecuta hasta que no haya más tool_calls
        while response.choices[0].finish_reason == "tool_calls":
            assistant_msg = response.choices[0].message
            self.conversation_history.append(assistant_msg)

            tool_results = self._execute_tool_calls(assistant_msg.tool_calls)
            self.conversation_history.extend(tool_results)

            response = self._call_openai()

        final_reply = response.choices[0].message.content
        self.conversation_history.append({"role": "assistant", "content": final_reply})
        return final_reply

    def _call_openai(self):
        """Llama a la API de OpenAI con las herramientas registradas."""
        tools = self.registry.get_openai_tools()
        kwargs = {
            "model": self.model,
            "messages": [{"role": "system", "content": Config.SYSTEM_PROMPT}]
            + self.conversation_history,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        return self.client.chat.completions.create(**kwargs)

    def _execute_tool_calls(self, tool_calls) -> list:
        """Ejecuta todas las herramientas solicitadas y retorna los resultados."""
        results = []
        for tc in tool_calls:
            tool_name = tc.function.name
            args = json.loads(tc.function.arguments)

            print(f"  ⚙️  Ejecutando herramienta: {tool_name}({args})")
            result = self.registry.execute(tool_name, args)
            print(f"  ✅ Resultado: {result[:80]}{'...' if len(result) > 80 else ''}\n")

            results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tool_name,
                "content": result,
            })
        return results

    def reset(self):
        """Limpia el historial de conversación."""
        self.conversation_history = []
        print("🔄 Historial limpiado.\n")

    def show_tools(self):
        """Muestra las herramientas disponibles."""
        tools = self.registry.get_all_tools()
        if not tools:
            print("⚠️  No hay herramientas registradas.")
            return
        print("\n📦 Herramientas disponibles:")
        for name, info in tools.items():
            print(f"  • {name}: {info['description']}")
        print()
