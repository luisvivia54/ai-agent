"""
Keycloak Token Manager
======================
Obtiene y renueva automáticamente el token JWT de Keycloak
usando el flujo Client Credentials (machine-to-machine).

Configura en .env:
  KEYCLOAK_URL           = https://auth.tu-dominio.com
  KEYCLOAK_REALM         = tu-realm
  KEYCLOAK_CLIENT_ID     = cliente-con-service-account-admin
  KEYCLOAK_CLIENT_SECRET = xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

Alternativa:
  TOCHO5_API_TOKEN       = Bearer <jwt-admin>
Si este bearer existe, las tools HTTP lo usarán directo y no pedirán token a Keycloak.
"""

import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error


class KeycloakTokenManager:
    """
    Maneja el ciclo de vida del token JWT de Keycloak.
    - Obtiene token nuevo al primer uso
    - Renueva automáticamente 30 segundos antes de que expire
    - Thread-safe para uso con FastAPI/uvicorn
    """

    def __init__(self):
        self.url          = os.getenv("KEYCLOAK_URL", "").rstrip("/")
        self.realm        = os.getenv("KEYCLOAK_REALM", "")
        self.client_id    = os.getenv("KEYCLOAK_CLIENT_ID", "")
        self.client_secret= os.getenv("KEYCLOAK_CLIENT_SECRET", "")

        self._token: str       = ""
        self._expires_at: float = 0.0   # timestamp unix cuando expira

        self._validate_config()

    def _validate_config(self):
        missing = []
        if not self.url:            missing.append("KEYCLOAK_URL")
        if not self.realm:          missing.append("KEYCLOAK_REALM")
        if not self.client_id:      missing.append("KEYCLOAK_CLIENT_ID")
        if not self.client_secret:  missing.append("KEYCLOAK_CLIENT_SECRET")
        if missing:
            print(f"⚠️  Keycloak: faltan variables en .env: {', '.join(missing)}")
            print("   El agente no podrá autenticarse con la API.")

    @property
    def is_configured(self) -> bool:
        return all([self.url, self.realm, self.client_id, self.client_secret])

    def get_token(self) -> str:
        """
        Retorna un token válido. Lo renueva automáticamente si está por expirar.
        """
        if not self.is_configured:
            return ""

        # Renueva si faltan menos de 30 segundos para expirar (o si no hay token)
        if time.time() >= self._expires_at - 30:
            self._refresh()

        return self._token

    def get_auth_header(self) -> str:
        """Retorna el header Authorization listo para usar."""
        token = self.get_token()
        return f"Bearer {token}" if token else ""

    def _refresh(self):
        """Solicita un nuevo token a Keycloak via Client Credentials."""
        token_url = f"{self.url}/realms/{self.realm}/protocol/openid-connect/token"

        payload = urllib.parse.urlencode({
            "grant_type":    "client_credentials",
            "client_id":     self.client_id,
            "client_secret": self.client_secret,
        }).encode("utf-8")

        req = urllib.request.Request(
            token_url,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())

            self._token      = data["access_token"]
            expires_in       = int(data.get("expires_in", 300))
            self._expires_at = time.time() + expires_in

            mins = expires_in // 60
            print(f"🔑 Token Keycloak renovado. Expira en {mins} min.")

        except urllib.error.HTTPError as e:
            body = e.read().decode()
            print(
                "❌ Keycloak error HTTP "
                f"{e.code}: {body[:200]} | "
                "Revisa KEYCLOAK_URL/REALM/CLIENT_ID/CLIENT_SECRET y que el cliente "
                "tenga service account con rol admin."
            )
            self._token      = ""
            self._expires_at = 0.0

        except Exception as e:
            print(f"❌ Keycloak error de conexión: {e}")
            self._token      = ""
            self._expires_at = 0.0


# ── Instancia global (singleton) ─────────────────────────────────────────────
# Se importa desde tocho5.py para obtener el token en cada request
token_manager = KeycloakTokenManager()
