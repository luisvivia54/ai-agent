"""
Punto de entrada principal
==========================
Ejecuta: python main.py

Comandos especiales en el chat:
  /reset    → limpia el historial
  /tools    → muestra herramientas disponibles
  /exit     → cierra el agente
"""

import sys
from agent import AIAgent
from config import Config


def check_config():
    """Valida que las variables de entorno esenciales estén configuradas."""
    if not Config.OPENAI_API_KEY:
        print("❌ ERROR: Falta OPENAI_API_KEY en el archivo .env")
        print("   Crea un archivo .env con: OPENAI_API_KEY=sk-...")
        sys.exit(1)


def main():
    print("=" * 55)
    print("  🤖  Agente de IA con OpenAI + Herramientas")
    print("=" * 55)
    print("  Comandos: /reset | /tools | /exit")
    print("=" * 55)

    check_config()
    agent = AIAgent()

    while True:
        try:
            user_input = input("Tú: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n👋 ¡Hasta luego!")
            break

        if not user_input:
            continue

        # Comandos especiales
        if user_input.lower() == "/exit":
            print("👋 ¡Hasta luego!")
            break
        elif user_input.lower() == "/reset":
            agent.reset()
            continue
        elif user_input.lower() == "/tools":
            agent.show_tools()
            continue

        # Respuesta del agente
        print("\nAgente: ", end="", flush=True)
        reply = agent.chat(user_input)
        print(reply)
        print()


if __name__ == "__main__":
    main()
