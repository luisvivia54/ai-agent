"""
Herramientas: API Tocho5 (Spring Boot)
=======================================
Conecta el agente con el backend de la liga de futbol.
Configura BASE_URL en tu .env: TOCHO5_API_URL=https://tu-api.com
Configura el token si tu API requiere auth: TOCHO5_API_TOKEN=Bearer xxxxx

GET  → responden directo
POST / PUT / PATCH / DELETE → piden confirmación antes de ejecutar
"""

import contextvars
import json
import os
import re
import sys
from typing import Any, Optional, Set
import urllib.request
import urllib.error
import urllib.parse
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from keycloak import token_manager
from tools.base import BaseTool

# ── Config ───────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("TOCHO5_API_URL", "http://localhost:8080").rstrip("/")
STATIC_API_TOKEN = os.getenv("TOCHO5_API_TOKEN", "").strip()
# Pendientes por session_id → {session_id: {key: op}}
_PENDING_STORE: dict = {}

def get_pending(session_id: str = "default") -> dict:
    if session_id not in _PENDING_STORE:
        _PENDING_STORE[session_id] = {}
    return _PENDING_STORE[session_id]

# Sesión activa (se setea desde el agente antes de cada llamada)
_current_session: contextvars.ContextVar[str] = contextvars.ContextVar(
    "tocho5_current_session",
    default="default",
)

def set_session(session_id: str):
    _current_session.set(session_id)

def PENDING() -> dict:
    return get_pending(_current_session.get())


def _normalize_tool_id(value: Optional[str]) -> str:
    return (value or "").strip().lower().replace("-", "_")


def _normalize_auth_token(raw: str) -> str:
    token = (raw or "").strip()
    if not token:
        return ""
    return token if token.lower().startswith("bearer ") else f"Bearer {token}"


def _extract_numeric_hints(value: Optional[str]) -> Set[str]:
    return set(re.findall(r"\d+", value or ""))


def _operation_matches_hint(op_key: str, op: dict, hint: str) -> bool:
    hint_norm = (hint or "").strip().lower()
    if not hint_norm:
        return False

    if hint_norm == op_key.lower():
        return True

    tool_hint = _normalize_tool_id(hint_norm.split(":", 1)[0])
    pending_tool = _normalize_tool_id(op.get("tool_id") or op_key.split(":", 1)[0])
    if tool_hint and tool_hint == pending_tool:
        return True

    hint_numbers = _extract_numeric_hints(hint_norm)
    path_numbers = _extract_numeric_hints(op.get("path"))
    if hint_numbers and path_numbers and hint_numbers.issubset(path_numbers):
        if not tool_hint or tool_hint == pending_tool:
            return True

    path_lower = str(op.get("path", "")).lower()
    if hint_norm in path_lower:
        return True

    return False


def _resolve_pending_key(operation_key: Optional[str]) -> Optional[str]:
    pending = PENDING()
    if not pending:
        return None

    hint = (operation_key or "").strip()
    if hint in pending:
        return hint

    matches = [
        key for key, op in pending.items()
        if _operation_matches_hint(key, op, hint)
    ]
    if len(matches) == 1:
        return matches[0]

    if len(pending) == 1:
        return next(iter(pending))

    return None


def _headers() -> dict:
    """Headers con token Keycloak renovado automáticamente."""
    h = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "Mozilla/5.0 (AI-Agent/1.0)",
        "Cache-Control": "no-cache",
    }
    auth = _normalize_auth_token(STATIC_API_TOKEN) or token_manager.get_auth_header()
    if auth:
        h["Authorization"] = auth
    return h


def _build_url(path: str, params: dict = None) -> str:
    url = BASE_URL + path
    if params:
        clean = {k: str(v) for k, v in params.items() if v is not None}
        if clean:
            url += "?" + urllib.parse.urlencode(clean)
    return url


def _get(path: str, params: dict = None) -> str:
    try:
        url = _build_url(path, params)
        req = urllib.request.Request(url, headers=_headers())
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode()
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code == 403:
            return (
                f"❌ HTTP 403 Acceso denegado.\n"
                f"Posibles causas:\n"
                f"  1. Falta TOCHO5_API_TOKEN en tu .env\n"
                f"  2. El token expiró — genera uno nuevo en tu app\n"
                f"  3. Cloudflare bloquea la IP. Intenta con la IP local si el backend corre local.\n"
                f"Detalle: {body[:300]}"
            )
        if e.code == 401:
            return "❌ HTTP 401 No autorizado. Revisa TOCHO5_API_TOKEN en .env"
        return f"❌ HTTP {e.code}: {body[:300]}"
    except Exception as e:
        return f"❌ Error de conexión: {e}"


def _request(method: str, path: str, body: dict = None) -> str:
    url = BASE_URL + path
    data = json.dumps(body).encode() if body else None
    req = urllib.request.Request(url, data=data, headers=_headers(), method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.read().decode() or f"✅ {method} exitoso"
    except urllib.error.HTTPError as e:
        return f"❌ HTTP {e.code}: {e.read().decode()}"
    except Exception as e:
        return f"❌ Error: {e}"


def _safe_json_loads(raw: str) -> Optional[Any]:
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_games(payload: Any) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]

    if isinstance(payload, dict):
        for key in ("content", "items", "data", "results", "games"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]

        if any(key in payload for key in ("game_id", "gameId", "id")):
            return [payload]

    return []


def _game_matches_id(game: dict, game_id: int) -> bool:
    wanted = str(game_id)
    for key in ("game_id", "gameId", "id"):
        value = game.get(key)
        if value is not None and str(value) == wanted:
            return True
    return False


def _find_game_in_raw_response(raw: str, game_id: int) -> Optional[dict]:
    payload = _safe_json_loads(raw)
    if payload is None:
        return None

    for game in _extract_games(payload):
        if _game_matches_id(game, game_id):
            return game

    return None


def _confirm_or_execute(tool_id: str, summary: str, method: str, path: str, body: dict = None) -> str:
    """
    Primera llamada  → guarda la operación pendiente y devuelve resumen para confirmar.
    Segunda llamada con confirmed=True → ejecuta.
    """
    key = f"{tool_id}:{path}"
    pending = PENDING()
    if key not in pending:
        pending[key] = {
            "tool_id": tool_id,
            "method": method,
            "path": path,
            "body": body,
        }
        lines = [
            f"⚠️  **Confirmación requerida**",
            f"",
            f"  Operación : {method} {path}",
            f"  Acción    : {summary}",
        ]
        if body:
            lines.append(f"  Datos     : {json.dumps(body, ensure_ascii=False, indent=2)}")
        lines += [
            f"",
            f"¿Confirmas esta operación? Responde **sí** para ejecutar o **no** para cancelar.",
        ]
        return "\n".join(lines)

    # Segunda llamada con confirmed=True → ejecutar
    op = PENDING().pop(key)
    result = _request(op["method"], op["path"], op["body"])
    return f"✅ Ejecutado:\n{result}"


# ════════════════════════════════════════════════════════════════════════
#  GET — EQUIPOS
# ════════════════════════════════════════════════════════════════════════

class GetTeamsTool(BaseTool):
    name = "get_teams"
    description = "Obtiene la lista de equipos. Filtra por leagueId, categoryCode o gender."
    parameters = {
        "leagueId":     {"type": "number",  "description": "ID de la liga (opcional)"},
        "categoryCode": {"type": "string",  "description": "Código de categoría (opcional)"},
        "gender":       {"type": "string",  "description": "Género: M, F (opcional)"},
    }
    required = []

    def run(self, leagueId=None, categoryCode=None, gender=None, **kwargs) -> str:
        return _get("/api/teams", {"leagueId": leagueId, "categoryCode": categoryCode, "gender": gender})


class GetTeamByIdTool(BaseTool):
    name = "get_team_by_id"
    description = "Obtiene el detalle de un equipo por su ID."
    parameters = {"teamId": {"type": "number", "description": "ID del equipo"}}
    required = ["teamId"]

    def run(self, teamId: int, **kwargs) -> str:
        return _get(f"/api/teams/{teamId}")


class GetTeamDetailTool(BaseTool):
    name = "get_team_detail"
    description = "Obtiene el detalle público completo de un equipo (jugadores, fotos, stats)."
    parameters = {"teamId": {"type": "number", "description": "ID del equipo"}}
    required = ["teamId"]

    def run(self, teamId: int, **kwargs) -> str:
        return _get(f"/api/teams/{teamId}/detail")


class GetTeamPlayersTool(BaseTool):
    name = "get_team_players"
    description = "Lista todos los jugadores de un equipo."
    parameters = {"teamId": {"type": "number", "description": "ID del equipo"}}
    required = ["teamId"]

    def run(self, teamId: int, **kwargs) -> str:
        return _get(f"/api/teams/{teamId}/players")


# ════════════════════════════════════════════════════════════════════════
#  GET — PARTIDOS
# ════════════════════════════════════════════════════════════════════════

class GetScheduledGamesTool(BaseTool):
    name = "get_scheduled_games"
    description = (
        "Lista los partidos programados (SCHEDULED). Filtra por liga, categoría, género o jornada. "
        "No la uses para buscar un partido por ID exacto; para eso usa get_game_by_id."
    )
    parameters = {
        "leagueId":   {"type": "number", "description": "ID de la liga (opcional)"},
        "code":       {"type": "string", "description": "Código de categoría (opcional)"},
        "gender":     {"type": "string", "description": "Género M/F (opcional)"},
        "roundLabel": {"type": "string", "description": "Etiqueta de jornada (opcional)"},
    }
    required = []

    def run(self, leagueId=None, code=None, gender=None, roundLabel=None, **kwargs) -> str:
        return _get("/api/games", {"leagueId": leagueId, "code": code, "gender": gender, "roundLabel": roundLabel})


class GetFinalGamesTool(BaseTool):
    name = "get_final_games"
    description = (
        "Lista los partidos finalizados (FINAL) con marcadores. Filtra por liga, categoría, etc. "
        "No la uses para buscar un partido por ID exacto; para eso usa get_game_by_id."
    )
    parameters = {
        "leagueId":   {"type": "number", "description": "ID de la liga (opcional)"},
        "code":       {"type": "string", "description": "Código de categoría (opcional)"},
        "gender":     {"type": "string", "description": "Género M/F (opcional)"},
        "roundLabel": {"type": "string", "description": "Etiqueta de jornada (opcional)"},
        "size":       {"type": "number", "description": "Límite de resultados (default 500)"},
        "all":        {"type": "boolean", "description": "true para traer todos sin paginación"},
    }
    required = []

    def run(self, leagueId=None, code=None, gender=None, roundLabel=None, size=500, all=False, **kwargs) -> str:
        return _get("/api/gamesFinal", {
            "leagueId": leagueId, "code": code, "gender": gender,
            "roundLabel": roundLabel, "size": size, "all": str(all).lower()
        })


class GetGameByIdTool(BaseTool):
    name = "get_game_by_id"
    description = (
        "Busca un partido por su ID global sin asumir liga. "
        "Si no se especifica estado, busca primero en programados y luego en finalizados."
    )
    parameters = {
        "gameId": {"type": "number", "description": "ID global del partido"},
        "status": {"type": "string", "description": "Estado opcional: SCHEDULED o FINAL"},
    }
    required = ["gameId"]

    def run(self, gameId: int, status=None, **kwargs) -> str:
        wanted_status = (status or "").strip().upper()

        searches: list[tuple[str, str, dict | None]] = []
        if wanted_status == "SCHEDULED":
            searches.append(("SCHEDULED", "/api/games", None))
        elif wanted_status == "FINAL":
            searches.append(("FINAL", "/api/gamesFinal", {"size": 1000, "all": "true"}))
        else:
            searches.append(("SCHEDULED", "/api/games", None))
            searches.append(("FINAL", "/api/gamesFinal", {"size": 1000, "all": "true"}))

        checked_sources = []
        errors = []

        for source_status, path, params in searches:
            raw = _get(path, params)
            checked_sources.append(source_status)

            if raw.startswith("❌"):
                errors.append({"status": source_status, "error": raw})
                continue

            game = _find_game_in_raw_response(raw, gameId)
            if game:
                return json.dumps({
                    "found": True,
                    "requestedGameId": gameId,
                    "status": source_status,
                    "game": game,
                }, ensure_ascii=False)

        return json.dumps({
            "found": False,
            "requestedGameId": gameId,
            "checkedStatuses": checked_sources,
            "errors": errors,
        }, ensure_ascii=False)


# ════════════════════════════════════════════════════════════════════════
#  GET — TABLA / STATS / CATEGORÍAS / TEMPORADAS
# ════════════════════════════════════════════════════════════════════════

class GetStandingsTool(BaseTool):
    name = "get_standings"
    description = "Obtiene la tabla de posiciones (puntos) de la liga."
    parameters = {
        "leagueId":     {"type": "number", "description": "ID de la liga (opcional)"},
        "categoryCode": {"type": "string", "description": "Código de categoría (opcional)"},
        "gender":       {"type": "string", "description": "Género M/F (opcional)"},
    }
    required = []

    def run(self, leagueId=None, categoryCode=None, gender=None, **kwargs) -> str:
        return _get("/api/points", {"leagueId": leagueId, "categoryCode": categoryCode, "gender": gender})


class GetPlayerStatsTool(BaseTool):
    name = "get_player_stats"
    description = "Obtiene el leaderboard de estadísticas de jugadores por temporada."
    parameters = {
        "leagueId": {"type": "number", "description": "ID de la liga (requerido)"},
        "seasonId": {"type": "number", "description": "ID de la temporada (opcional)"},
    }
    required = ["leagueId"]

    def run(self, leagueId: int, seasonId=None, **kwargs) -> str:
        return _get("/api/stats/players", {"leagueId": leagueId, "seasonId": seasonId})


class GetCategoriesTool(BaseTool):
    name = "get_categories"
    description = "Lista las categorías disponibles en la liga."
    parameters = {
        "leagueId": {"type": "number", "description": "ID de la liga (opcional)"},
        "gender":   {"type": "string", "description": "Género M/F (opcional)"},
    }
    required = []

    def run(self, leagueId=None, gender=None, **kwargs) -> str:
        return _get("/api/categories", {"leagueId": leagueId, "gender": gender})


class GetSeasonsTool(BaseTool):
    name = "get_seasons"
    description = "Lista las temporadas disponibles para una liga."
    parameters = {"leagueId": {"type": "number", "description": "ID de la liga (opcional)"}}
    required = []

    def run(self, leagueId=None, **kwargs) -> str:
        return _get("/api/seasons", {"leagueId": leagueId})


class GetCurrentSeasonTool(BaseTool):
    name = "get_current_season"
    description = "Obtiene el ID de la temporada activa de una liga."
    parameters = {"leagueId": {"type": "number", "description": "ID de la liga"}}
    required = ["leagueId"]

    def run(self, leagueId: int, **kwargs) -> str:
        return _get("/api/seasons/current", {"leagueId": leagueId})


# ════════════════════════════════════════════════════════════════════════
#  ✋ CONFIRMACIÓN MANUAL — usado por el agente para validar POST/PATCH
# ════════════════════════════════════════════════════════════════════════

class ConfirmActionTool(BaseTool):
    name = "confirm_action"
    description = (
        "Confirma o cancela una operación POST/PUT/PATCH/DELETE pendiente. "
        "Úsala cuando el usuario responda 'sí' o 'no' a una confirmación previa."
    )
    parameters = {
        "operation_key": {
            "type": "string",
            "description": "Clave de la operación pendiente. Acepta la clave exacta o una referencia aproximada como tool_id:gameId si solo hay una coincidencia pendiente.",
        },
        "confirmed": {
            "type": "boolean",
            "description": "true = ejecutar, false = cancelar",
        },
    }
    required = ["operation_key", "confirmed"]

    def run(self, operation_key: str, confirmed: bool, **kwargs) -> str:
        resolved_key = _resolve_pending_key(operation_key)
        if not confirmed:
            if resolved_key:
                PENDING().pop(resolved_key, None)
                return "❌ Operación cancelada."
            return "❌ Operación cancelada."
        if not resolved_key:
            return "⚠️ No hay operación pendiente con esa clave. Intenta de nuevo."
        op = PENDING().pop(resolved_key)
        result = _request(op["method"], op["path"], op["body"])
        return f"✅ Operación ejecutada:\n{result}"


# ════════════════════════════════════════════════════════════════════════
#  POST — CREAR PARTIDO PROGRAMADO
# ════════════════════════════════════════════════════════════════════════

class CreateGameTool(BaseTool):
    name = "create_game"
    description = (
        "Crea un partido programado nuevo. "
        "Solicita confirmación antes de guardar mostrando todos los datos del partido."
    )
    parameters = {
        "homeTeamId":  {"type": "number", "description": "ID del equipo local"},
        "awayTeamId":  {"type": "number", "description": "ID del equipo visitante"},
        "leagueId":    {"type": "number", "description": "ID de la liga"},
        "categoryId":  {"type": "number", "description": "ID de la categoría"},
        "roundLabel":  {"type": "string", "description": "Etiqueta de la jornada, ej: 'Jornada 5'"},
        "scheduledAt": {"type": "string", "description": "Fecha/hora ISO8601, ej: 2025-08-10T18:00:00"},
        "field":       {"type": "string", "description": "Campo o cancha donde se juega (opcional)"},
    }
    required = ["homeTeamId", "awayTeamId", "leagueId", "categoryId", "roundLabel", "scheduledAt"]

    def run(self, homeTeamId: int, awayTeamId: int, leagueId: int, categoryId: int,
            roundLabel: str, scheduledAt: str, field: str = None, **kwargs) -> str:

        body = {
            "homeTeamId": homeTeamId, "awayTeamId": awayTeamId,
            "leagueId": leagueId, "categoryId": categoryId,
            "roundLabel": roundLabel, "scheduledAt": scheduledAt,
        }
        if field:
            body["field"] = field

        summary = (
            f"Crear partido: equipo local #{homeTeamId} vs visitante #{awayTeamId} | "
            f"Liga #{leagueId} · Cat #{categoryId} · {roundLabel} · {scheduledAt}"
            + (f" · Campo: {field}" if field else "")
        )
        return _confirm_or_execute(self.name, summary, "POST", "/api/games", body)


# ════════════════════════════════════════════════════════════════════════
#  POST — FINALIZAR PARTIDO (marcar resultado)
# ════════════════════════════════════════════════════════════════════════

class FinalizeGameTool(BaseTool):
    name = "finalize_game"
    description = (
        "Finaliza un partido registrando el marcador. "
        "Cambia el estado a FINAL y actualiza la tabla de posiciones. "
        "Pide confirmación mostrando el marcador exacto antes de guardar."
    )
    parameters = {
        "gameId":     {"type": "number", "description": "ID del partido a finalizar"},
        "homeScore":  {"type": "number", "description": "Goles del equipo local"},
        "awayScore":  {"type": "number", "description": "Goles del equipo visitante"},
        "status":     {"type": "string", "description": "Estado final, normalmente 'FINAL'"},
    }
    required = ["gameId", "homeScore", "awayScore"]

    def run(self, gameId: int, homeScore: int, awayScore: int, status: str = "FINAL", **kwargs) -> str:
        body = {"game_id": gameId, "home_score": homeScore, "away_score": awayScore, "status": status}

        result_label = "Empate" if homeScore == awayScore else (
            f"Gana local ({homeScore}-{awayScore})" if homeScore > awayScore
            else f"Gana visitante ({homeScore}-{awayScore})"
        )

        summary = (
            f"Finalizar partido #{gameId} con marcador {homeScore} - {awayScore} "
            f"({result_label}). Esto actualizará la tabla de posiciones."
        )
        return _confirm_or_execute(self.name, summary, "POST", "/api/partido/update", body)


# ════════════════════════════════════════════════════════════════════════
#  PATCH — EDITAR MARCADOR DE PARTIDO YA FINALIZADO (admin)
# ════════════════════════════════════════════════════════════════════════

class AdminEditScoreTool(BaseTool):
    name = "admin_edit_game_score"
    description = (
        "Corrige el marcador de un partido ya finalizado (solo admin). "
        "Pide confirmación mostrando el marcador nuevo antes de guardar."
    )
    parameters = {
        "gameId":    {"type": "number", "description": "ID del partido"},
        "homeScore": {"type": "number", "description": "Nuevo marcador local"},
        "awayScore": {"type": "number", "description": "Nuevo marcador visitante"},
    }
    required = ["gameId", "homeScore", "awayScore"]

    def run(self, gameId: int, homeScore: int, awayScore: int, **kwargs) -> str:
        body = {"homeScore": homeScore, "awayScore": awayScore}
        summary = (
            f"Corregir marcador del partido #{gameId} → nuevo resultado: "
            f"{homeScore} - {awayScore}. ⚠️ Esto sobreescribe el marcador existente."
        )
        return _confirm_or_execute(self.name, summary, "PATCH",
                                   f"/api/admin/games/{gameId}/score", body)


# ════════════════════════════════════════════════════════════════════════
#  DELETE — ELIMINAR / REVERTIR PARTIDO (admin)
# ════════════════════════════════════════════════════════════════════════

class AdminDeleteGameTool(BaseTool):
    name = "admin_delete_game"
    description = (
        "Elimina un partido programado o revierte uno finalizado (solo admin). "
        "Si el partido es FINAL, revierte los standings y lo marca como CANCELLED. "
        "Pide confirmación antes de ejecutar."
    )
    parameters = {
        "gameId": {"type": "number", "description": "ID del partido a eliminar/revertir"},
    }
    required = ["gameId"]

    def run(self, gameId: int, **kwargs) -> str:
        summary = (
            f"Eliminar/revertir partido #{gameId}. "
            f"Si está FINALIZADO, se revertirán los puntos de la tabla. "
            f"⚠️ Esta acción no se puede deshacer fácilmente."
        )
        return _confirm_or_execute(self.name, summary, "DELETE",
                                   f"/api/admin/games/{gameId}")


# ════════════════════════════════════════════════════════════════════════
#  PUT — ESTADÍSTICAS DE JUGADORES POR PARTIDO
# ════════════════════════════════════════════════════════════════════════

class UpsertPlayerStatsTool(BaseTool):
    name = "upsert_player_game_stats"
    description = (
        "Registra o actualiza las estadísticas de jugadores para un partido específico "
        "(goles, asistencias, tarjetas, etc.). Pide confirmación antes de guardar."
    )
    parameters = {
        "gameId": {"type": "number", "description": "ID del partido"},
        "stats":  {
            "type": "string",
            "description": (
                "JSON string con array de stats, ej: "
                '[{"playerId":1,"goals":2,"assists":1,"yellowCards":0,"redCards":0}]'
            ),
        },
    }
    required = ["gameId", "stats"]

    def run(self, gameId: int, stats: str, **kwargs) -> str:
        try:
            body = json.loads(stats)
        except json.JSONDecodeError:
            return "❌ El parámetro 'stats' debe ser un JSON válido."

        n = len(body) if isinstance(body, list) else 1
        summary = (
            f"Registrar/actualizar estadísticas de {n} jugador(es) "
            f"para el partido #{gameId}."
        )
        return _confirm_or_execute(self.name, summary, "PUT",
                                   f"/api/games/{gameId}/player-stats", body)


# ════════════════════════════════════════════════════════════════════════
#  PATCH — ACTIVAR / DESACTIVAR EQUIPO
# ════════════════════════════════════════════════════════════════════════

class SetTeamActiveTool(BaseTool):
    name = "set_team_active"
    description = "Activa o desactiva un equipo. Pide confirmación antes de ejecutar."
    parameters = {
        "teamId":   {"type": "number",  "description": "ID del equipo"},
        "isActive": {"type": "boolean", "description": "true = activar, false = desactivar"},
    }
    required = ["teamId", "isActive"]

    def run(self, teamId: int, isActive: bool, **kwargs) -> str:
        action = "ACTIVAR" if isActive else "DESACTIVAR"
        summary = f"{action} el equipo #{teamId}. Esto afecta su visibilidad en la plataforma."
        return _confirm_or_execute(self.name, summary, "PATCH",
                                   f"/api/teams/{teamId}/active", {"isActive": isActive})
