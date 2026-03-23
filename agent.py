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

# Límite de mensajes en el historial (últimos N mensajes)
MAX_HISTORY = 10
# Límite de caracteres por resultado de herramienta
MAX_TOOL_RESULT = 4000


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
        self._trim_history()

        try:
            response = self._call_openai()

            # Loop de herramientas: ejecuta hasta que no haya más tool_calls
            while response.choices[0].finish_reason == "tool_calls":
                assistant_msg = response.choices[0].message
                self.conversation_history.append(assistant_msg)

                tool_results = self._execute_tool_calls(assistant_msg.tool_calls)
                self.conversation_history.extend(tool_results)
                self._trim_history()

                response = self._call_openai()

            final_reply = response.choices[0].message.content
            self.conversation_history.append({"role": "assistant", "content": final_reply})
            return final_reply

        except Exception as e:
            error_msg = str(e)
            if "context_length_exceeded" in error_msg:
                # Limpia el historial y reintenta solo con el mensaje actual
                print("⚠️  Context length exceeded — limpiando historial y reintentando...")
                self.conversation_history = [{"role": "user", "content": user_message}]
                try:
                    response = self._call_openai()
                    final_reply = response.choices[0].message.content
                    self.conversation_history.append({"role": "assistant", "content": final_reply})
                    return final_reply
                except Exception as e2:
                    return f"⚠️ Error al procesar tu mensaje: {e2}"
            return f"⚠️ Error inesperado: {e}"

    def _trim_history(self):
        """
        Mantiene el historial dentro del límite.
        Conserva los últimos MAX_HISTORY mensajes.
        Nunca corta en medio de un par tool_call / tool_result.
        """
        if len(self.conversation_history) <= MAX_HISTORY:
            return

        # Recorta a los últimos MAX_HISTORY mensajes
        self.conversation_history = self.conversation_history[-MAX_HISTORY:]

        # Si el primer mensaje es un tool_result sin su tool_call, lo elimina
        # para no enviar un historial inválido a OpenAI
        while self.conversation_history and self.conversation_history[0].get("role") == "tool":
            self.conversation_history.pop(0)

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

            # Trunca resultados muy largos para no saturar el contexto
            if len(result) > MAX_TOOL_RESULT:
                result = result[:MAX_TOOL_RESULT] + f"\n... [respuesta truncada a {MAX_TOOL_RESULT} chars]"

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