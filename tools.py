"""Outils réseau compacts avec récupération explicite hors ligne."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

SERPAPI_URL = "https://serpapi.com/search.json"
OFFICIAL_RIGHTS_URL = (
    "https://europa.eu/youreurope/citizens/travel/"
    "passenger-rights/air/index_fr.htm"
)
REGULATION_URL = (
    "https://eur-lex.europa.eu/legal-content/FR/TXT/"
    "?uri=CELEX%3A32004R0261"
)


class SerpUnavailable(RuntimeError):
    """La recherche temps réel ne peut pas être exécutée."""


RESEARCH_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "verify_air_passenger_rule",
            "description": (
                "Vérifie les règles officielles de droits des passagers "
                "applicables au type d'incident, sans envoyer de donnée personnelle."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "disruption_type": {
                        "type": "string",
                        "enum": [
                            "delay",
                            "cancellation",
                            "denied_boarding",
                            "missed_connection",
                        ],
                    },
                    "origin": {"type": "string", "maxLength": 80},
                    "destination": {"type": "string", "maxLength": 80},
                    "arrival_delay_minutes": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}]
                    },
                    "departure_delay_minutes": {
                        "anyOf": [{"type": "integer"}, {"type": "null"}]
                    },
                },
                "required": [
                    "disruption_type",
                    "origin",
                    "destination",
                    "arrival_delay_minutes",
                    "departure_delay_minutes",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_claim_channel",
            "description": (
                "Trouve le canal officiel de réclamation de la compagnie, "
                "sans envoyer les données du passager ou de sa réservation."
            ),
            "parameters": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "airline": {"type": "string", "maxLength": 100},
                },
                "required": ["airline"],
            },
        },
    },
]

ALLOWED_DISRUPTIONS = {
    "delay",
    "cancellation",
    "denied_boarding",
    "missed_connection",
}


def _dotenv_value(path: Path, names: tuple[str, ...]) -> str | None:
    """Lit une valeur autorisée d'un .env sans modifier ni afficher l'environnement."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError):
        return None
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        key, separator, value = stripped.partition("=")
        if not separator or key.strip() not in names:
            continue
        value = value.strip()
        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]
        return value or None
    return None


def _api_key() -> str | None:
    """Privilégie l'environnement, puis le .env local non versionné."""
    environment_value = os.getenv("SERPAPI_KEY") or os.getenv("SERPAPI_API_KEY")
    if environment_value:
        return environment_value
    return _dotenv_value(
        Path(__file__).resolve().parent / ".env",
        ("SERPAPI_KEY", "SERPAPI_API_KEY"),
    )


def build_research_context(extracted: dict[str, Any]) -> dict[str, Any]:
    """Expose à Gemma uniquement les champs nécessaires aux outils de recherche."""
    disruption = extracted.get("disruption_type")
    if disruption not in ALLOWED_DISRUPTIONS:
        disruption = ""

    def limited_string(field: str, limit: int) -> str:
        value = extracted.get(field)
        return value.strip()[:limit] if isinstance(value, str) else ""

    def limited_minutes(field: str) -> int | None:
        value = extracted.get(field)
        if isinstance(value, int) and not isinstance(value, bool):
            return value if 0 <= value < 24 * 60 else None
        return None

    arrival_delay = limited_minutes("arrival_delay_minutes")
    if arrival_delay is None:
        arrival_delay = limited_minutes("delay_minutes")
    return {
        "disruption_type": disruption,
        "origin": limited_string("origin", 80),
        "destination": limited_string("destination", 80),
        "arrival_delay_minutes": arrival_delay,
        "departure_delay_minutes": limited_minutes("departure_delay_minutes"),
        "airline": limited_string("airline", 100),
    }


def web_search(query: str, num: int = 5) -> list[dict[str, str]]:
    """Recherche Google via SerpApi et limite le contexte aux champs utiles."""
    api_key = _api_key()
    if not api_key:
        raise SerpUnavailable("clé SerpApi absente")
    params = {
        "engine": "google_light",
        "q": query,
        "num": max(1, min(num, 5)),
        "hl": "fr",
        "gl": "fr",
        "api_key": api_key,
    }
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "Droit-de-Retard/0.1"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload: dict[str, Any] = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise SerpUnavailable("quota SerpApi épuisé") from exc
        raise SerpUnavailable(f"SerpApi HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise SerpUnavailable("recherche temps réel indisponible") from exc

    error = payload.get("error")
    if error:
        raise SerpUnavailable(str(error)[:160])
    return [
        {
            "title": result.get("title", ""),
            "link": result.get("link", ""),
            "snippet": result.get("snippet", ""),
        }
        for result in payload.get("organic_results", [])[:num]
    ]


def build_rule_query(extracted: dict[str, Any]) -> str:
    """Construit une requête sans identité ni référence de réservation."""
    context = build_research_context(extracted)
    disruption_terms = {
        "delay": "retard",
        "cancellation": "annulation",
        "denied_boarding": "refus embarquement",
        "missed_connection": "correspondance manquée",
    }
    disruption = disruption_terms.get(context["disruption_type"], "incident")
    return (
        "site:europa.eu/youreurope/citizens/travel/passenger-rights/air "
        f"droits passagers aériens {disruption}"
    ).strip()


def _filter_official_rule_sources(
    sources: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Conserve uniquement le référentiel aérien officiel de Your Europe."""
    official_path = "/youreurope/citizens/travel/passenger-rights/air/"
    filtered = []
    for source in sources:
        parsed = urllib.parse.urlparse(source.get("link", ""))
        if (
            parsed.hostname == "europa.eu"
            and parsed.path.startswith(official_path)
            and parsed.path.endswith("/index_fr.htm")
        ):
            filtered.append(source)
    return filtered


def verify_air_passenger_rule(extracted: dict[str, Any]) -> dict[str, Any]:
    """Cherche uniquement des sources institutionnelles sur le cas extrait."""
    query = build_rule_query(extracted)
    try:
        sources = _filter_official_rule_sources(web_search(query, num=5))
        if not sources:
            raise SerpUnavailable("aucune source officielle pertinente retournée")
    except SerpUnavailable as exc:
        return {
            "status": "offline",
            "reason": str(exc),
            "verified_live": False,
            "sources": [
                {
                    "title": "Droits des passagers aériens - Your Europe",
                    "link": OFFICIAL_RIGHTS_URL,
                    "snippet": (
                        "Source institutionnelle de référence à vérifier dès que "
                        "la connexion revient."
                    ),
                },
                {
                    "title": "Règlement (CE) no 261/2004",
                    "link": REGULATION_URL,
                    "snippet": (
                        "Texte réglementaire de référence ; aucune conclusion "
                        "automatique n'est tirée hors ligne."
                    ),
                },
            ],
        }
    return {
        "status": "online",
        "reason": None,
        "verified_live": True,
        "sources": sources,
    }


def find_claim_channel(extracted: dict[str, Any]) -> dict[str, Any]:
    """Cherche le canal officiel de réclamation de la compagnie."""
    airline = build_research_context(extracted)["airline"]
    if airline.casefold() == "aurora airlines":
        return {
            "status": "demo_carrier",
            "channel": None,
            "message": (
                "Aurora Airlines est fictive : aucun formulaire de réclamation "
                "réel ne sera inventé."
            ),
        }
    try:
        results = web_search(
            f"{airline} site officiel formulaire réclamation retard vol",
            num=3,
        )
    except SerpUnavailable as exc:
        return {
            "status": "offline",
            "channel": None,
            "message": str(exc),
        }
    return {
        "status": "online",
        "channel": results[0]["link"] if results else None,
        "results": results,
    }
