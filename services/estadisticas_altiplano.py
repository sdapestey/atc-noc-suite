"""Estadísticas Altiplano INP — conteos por estado RN / alineación (tarjetas en dashboard)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from altiplano import contar_ont_connection_inp_search_intents, obtener_token_entorno_nbi
from config import get_altiplano_credentials, get_altiplano_inp_search_http_timeout_s
from services.dashboard_cache import get_cached_estadisticas_altiplano

_SECTIONS: tuple[dict, ...] = (
    {
        "id": "required_network_state",
        "title": "Required Network State",
        "cards": (
            {
                "id": "rn_active",
                "title": "Active",
                "foot": "intents",
                "theme": "rn",
                "required_network_state": ["active"],
                "alignment_state": None,
            },
            {
                "id": "rn_suspended",
                "title": "Suspended",
                "foot": "intents",
                "theme": "rn",
                "required_network_state": ["suspended"],
                "alignment_state": None,
            },
            {
                "id": "rn_not_present",
                "title": "Not present",
                "foot": "intents",
                "theme": "rn",
                "required_network_state": ["not-present"],
                "alignment_state": None,
            },
        ),
    },
    {
        "id": "alignment_state",
        "title": "Alignment State",
        "cards": (
            {
                "id": "al_aligned",
                "title": "Aligned",
                "foot": "intents",
                "theme": "al",
                "required_network_state": None,
                "alignment_state": ["aligned"],
            },
            {
                "id": "al_misaligned",
                "title": "Misaligned",
                "foot": "intents",
                "theme": "al",
                "required_network_state": None,
                "alignment_state": ["misaligned"],
            },
        ),
    },
    {
        "id": "combinaciones",
        "title": "Combinaciones frecuentes",
        "cards": (
            {
                "id": "preset_misaligned",
                "title": "Solo Misaligned",
                "foot": "intents",
                "theme": "misaligned",
                "required_network_state": None,
                "alignment_state": ["misaligned"],
            },
            {
                "id": "preset_not_present_misaligned",
                "title": "Not present + Misaligned",
                "foot": "intents",
                "theme": "misaligned",
                "required_network_state": ["not-present"],
                "alignment_state": ["misaligned"],
            },
            {
                "id": "preset_not_present_aligned",
                "title": "Not present + Aligned",
                "foot": "intents",
                "theme": "aligned",
                "required_network_state": ["not-present"],
                "alignment_state": ["aligned"],
            },
            {
                "id": "combo_active_misaligned",
                "title": "Active + Misaligned",
                "foot": "intents",
                "theme": "misaligned",
                "required_network_state": ["active"],
                "alignment_state": ["misaligned"],
            },
            {
                "id": "combo_suspended_misaligned",
                "title": "Suspended + Misaligned",
                "foot": "intents",
                "theme": "misaligned",
                "required_network_state": ["suspended"],
                "alignment_state": ["misaligned"],
            },
        ),
    },
)


def _inp_bearer_token() -> tuple[str | None, str | None]:
    """Token INP para estadísticas: siempre ``ALTIPLANO_USER`` / ``ALTIPLANO_PASSWORD`` del entorno."""
    user, pwd = get_altiplano_credentials()
    if not user or not pwd:
        return None, "Credenciales no configuradas (ALTIPLANO_USER / ALTIPLANO_PASSWORD)"
    token = obtener_token_entorno_nbi("INP", user, pwd)
    if not token:
        return None, "No se pudo autenticar contra Altiplano INP"
    return token, None


def _count_one(
    token: str,
    *,
    required_network_state: list[str] | None,
    alignment_state: list[str] | None,
    timeout_s: float,
) -> dict:
    return contar_ont_connection_inp_search_intents(
        token,
        filter_required_network_state=required_network_state,
        filter_alignment_state=alignment_state,
        timeout_s=timeout_s,
    )


def _compute_estadisticas_altiplano() -> dict:
    token, auth_err = _inp_bearer_token()
    if not token:
        return {
            "ok": False,
            "message": auth_err or "Sin token INP",
            "sections": [],
        }

    timeout_s = float(get_altiplano_inp_search_http_timeout_s())
    flat_cards: list[tuple[dict, dict]] = []
    for section in _SECTIONS:
        for card_def in section["cards"]:
            flat_cards.append((section, card_def))

    counts: dict[str, dict] = {}
    max_workers = min(6, max(1, len(flat_cards)))
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {}
        for _section, card_def in flat_cards:
            fut = pool.submit(
                _count_one,
                token,
                required_network_state=card_def.get("required_network_state"),
                alignment_state=card_def.get("alignment_state"),
                timeout_s=timeout_s,
            )
            futures[fut] = card_def["id"]
        for fut in as_completed(futures):
            card_id = futures[fut]
            try:
                counts[card_id] = fut.result()
            except Exception as ex:
                counts[card_id] = {"ok": False, "count": None, "message": str(ex)}

    sections_out: list[dict] = []
    any_ok = False
    errors: list[str] = []
    for section in _SECTIONS:
        cards_out: list[dict] = []
        for card_def in section["cards"]:
            result = counts.get(card_def["id"]) or {}
            ok = bool(result.get("ok"))
            if ok:
                any_ok = True
            msg = (result.get("message") or "").strip()
            if msg and msg not in errors:
                errors.append(msg)
            cards_out.append(
                {
                    "id": card_def["id"],
                    "title": card_def["title"],
                    "foot": card_def.get("foot") or "intents",
                    "theme": card_def.get("theme") or "rn",
                    "count": result.get("count") if ok else None,
                    "ok": ok,
                    "error": msg or None,
                    "filters": {
                        "required_network_state": card_def.get("required_network_state"),
                        "alignment_state": card_def.get("alignment_state"),
                    },
                }
            )
        sections_out.append(
            {
                "id": section["id"],
                "title": section["title"],
                "cards": cards_out,
            }
        )

    return {
        "ok": any_ok,
        "source": "altiplano-inp",
        "intent_type": "ont-connection",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": sections_out,
        "message": errors[0] if errors and not any_ok else None,
        "notes": [
            "Conteos vía ibn:search-intents (INP). Active + Aligned no se muestra: demasiados resultados.",
            "Los mismos filtros están disponibles en Orquestador → Altiplano → INP → búsqueda avanzada.",
        ],
    }


def dashboard_estadisticas_altiplano_inp(
    *,
    cache_seconds: int = 300,
    refresh: bool = False,
) -> dict:
    """Payload JSON para la pestaña Altiplano en Estadísticas."""
    if refresh or cache_seconds <= 0:
        return _compute_estadisticas_altiplano()
    return get_cached_estadisticas_altiplano(
        cache_seconds,
        "env",
        lambda: _compute_estadisticas_altiplano(),
    )
