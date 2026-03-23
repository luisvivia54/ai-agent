"""
AI Agent con OpenAI - Sistema modular de herramientas
"""

import json
from openai import OpenAI
from tools.registry import ToolRegistry
from config import Config

MAX_HISTORY      = 10
MAX_TOOL_RESULT  = 4000


class AIAgent:
    def __init__(self):
        self.client = OpenAI(api_key=Config.OPENAI_API_KEY)
        self.registry = ToolRegistry()
        self.conversation_history = []
        self.model = Config.MODEL
        print(f"\n🤖 Agente iniciado con modelo: {self.model}")
        print(f"🔧 Herramientas cargadas: {', '.join(self.registry.get_tool_names()) or 'ninguna'}\n")

    def chat(self, user_message: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_message})
        self._trim_history()

        try:
            response = self._call_openai()

            while response.choices[0].finish_reason == "tool_calls":
                assistant_msg = response.choices[0].message
                # ✅ Guardamos como dict siempre, nunca como objeto Pydantic
                self.conversation_history.append(self._msg_to_dict(assistant_msg))

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
                print("⚠️  Context too long — limpiando historial y reintentando...")
                self.conversation_history = [{"role": "user", "content": user_message}]
                try:
                    response = self._call_openai()
                    final_reply = response.choices[0].message.content
                    self.conversation_history.append({"role": "assistant", "content": final_reply})
                    return final_reply
                except Exception as e2:
                    return f"⚠️ Error: {e2}"
            return f"⚠️ Error inesperado: {e}"

    def _msg_to_dict(self, msg) -> dict:
        """Convierte ChatCompletionMessage a dict serializable."""
        d = {"role": msg.role, "content": msg.content}
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        return d

    def _trim_history(self):
        """Mantiene el historial en MAX_HISTORY mensajes, sin cortar pares tool_call/tool_result."""
        if len(self.conversation_history) <= MAX_HISTORY:
            return
        self.conversation_history = self.conversation_history[-MAX_HISTORY:]
        # Elimina tool_results huérfanos al inicio
        while self.conversation_history:
            first = self.conversation_history[0]
            role = first.get("role") if isinstance(first, dict) else getattr(first, "role", None)
            if role == "tool":
                self.conversation_history.pop(0)
            else:
                break

    def _call_openai(self):
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
        results = []
        for tc in tool_calls:
            tool_name = tc.function.name
            args = json.loads(tc.function.arguments)
            print(f"  ⚙️  Ejecutando herramienta: {tool_name}({args})")
            result = self.registry.execute(tool_name, args)
            if len(result) > MAX_TOOL_RESULT:
                result = result[:MAX_TOOL_RESULT] + f"\n...[truncado a {MAX_TOOL_RESULT} chars]"
            print(f"  ✅ Resultado: {result[:80]}{'...' if len(result) > 80 else ''}\n")
            results.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": tool_name,
                "content": result,
            })
        return results

    def reset(self):
        self.conversation_history = []
        print("🔄 Historial limpiado.\n")

    def show_tools(self):
        tools = self.registry.get_all_tools()
        if not tools:
            print("⚠️  No hay herramientas registradas.")
            return
        print("\n📦 Herramientas disponibles:")
        for name, info in tools.items():
            print(f"  • {name}: {info['description']}")
        print()