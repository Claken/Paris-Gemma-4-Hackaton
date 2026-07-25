"""Pipeline local-first pour analyser une preuve de voyage aérien.

Usage:
    .venv/bin/python agent.py billet_avion_fictif.pdf
    .venv/bin/python agent.py billet_avion_fictif.pdf \
        --incident "Le vol est arrivé avec 3 h 25 de retard."
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from eu261 import assess_ticket_reimbursement, qualify_case
from tools import (
    RESEARCH_TOOL_DEFINITIONS,
    build_research_context,
    find_claim_channel,
    verify_air_passenger_rule,
)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat")
MODEL = os.getenv("DR_MODEL", "gemma4:12b")

NULLABLE_STRING = {"anyOf": [{"type": "string"}, {"type": "null"}]}
NULLABLE_INTEGER = {"anyOf": [{"type": "integer"}, {"type": "null"}]}
NULLABLE_BOOLEAN = {"anyOf": [{"type": "boolean"}, {"type": "null"}]}

FLIGHT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_type": {
            "type": "string",
            "enum": ["boarding_pass", "booking", "delay_notice", "other"],
        },
        "passenger_name": NULLABLE_STRING,
        "airline": NULLABLE_STRING,
        "flight_number": NULLABLE_STRING,
        "origin": NULLABLE_STRING,
        "destination": NULLABLE_STRING,
        "departure_date": NULLABLE_STRING,
        "scheduled_departure": NULLABLE_STRING,
        "scheduled_arrival": NULLABLE_STRING,
        "actual_arrival": NULLABLE_STRING,
        "boarding_time": NULLABLE_STRING,
        "booking_reference": NULLABLE_STRING,
        "seat": NULLABLE_STRING,
        "gate": NULLABLE_STRING,
        "disruption_type": {
            "type": "string",
            "enum": [
                "delay",
                "cancellation",
                "denied_boarding",
                "missed_connection",
                "none",
                "unknown",
            ],
        },
        "delay_minutes": NULLABLE_INTEGER,
        "arrival_delay_minutes": NULLABLE_INTEGER,
        "departure_delay_minutes": NULLABLE_INTEGER,
        "trip_completed": NULLABLE_BOOLEAN,
        "disruption_cause": NULLABLE_STRING,
        "evidence": {"type": "array", "items": {"type": "string"}},
        "uncertain_fields": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "document_type",
        "passenger_name",
        "airline",
        "flight_number",
        "origin",
        "destination",
        "departure_date",
        "scheduled_departure",
        "scheduled_arrival",
        "actual_arrival",
        "boarding_time",
        "booking_reference",
        "seat",
        "gate",
        "disruption_type",
        "delay_minutes",
        "arrival_delay_minutes",
        "departure_delay_minutes",
        "trip_completed",
        "disruption_cause",
        "evidence",
        "uncertain_fields",
    ],
}

CLAIM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "eligibility": {
            "type": "string",
            "enum": ["likely", "uncertain", "unlikely"],
        },
        "summary": {"type": "string"},
        "estimated_compensation_eur": NULLABLE_INTEGER,
        "reasoning": {"type": "array", "items": {"type": "string"}},
        "letter_subject": {"type": "string"},
        "letter_body": {"type": "string"},
        "checklist": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}},
        "source_indices": {"type": "array", "items": {"type": "integer"}},
    },
    "required": [
        "eligibility",
        "summary",
        "estimated_compensation_eur",
        "reasoning",
        "letter_subject",
        "letter_body",
        "checklist",
        "warnings",
        "source_indices",
    ],
}

EXTRACTION_SYSTEM = """Tu extrais des faits depuis des justificatifs de voyage.
Règles absolues :
- utilise uniquement ce qui est visible dans le document ou explicitement fourni ;
- n'invente jamais un retard, une annulation, une heure d'arrivée ou une cause ;
- distingue le retard au départ du retard à l'arrivée ; ne les déduis pas l'un
  de l'autre ;
- marque trip_completed uniquement si le voyageur dit explicitement avoir pris
  le vol ou, au contraire, avoir renoncé au voyage ;
- retourne null lorsqu'une valeur manque ;
- utilise le format ISO YYYY-MM-DD pour une date si elle est non ambiguë ;
- recopie dans evidence de courts éléments visibles qui justifient l'extraction ;
- marque dans uncertain_fields tout champ ambigu.
Le document peut être fictif. Cela ne change pas les règles d'extraction."""

CLAIM_SYSTEM = """Tu aides un passager à préparer une réclamation aérienne.
Tu ne fournis pas de conseil juridique et tu ne garantis jamais une indemnisation.
Utilise uniquement les faits et sources fournis. Cite les sources avec [n].
Les indices [n] désignent uniquement les sources juridiques de RECHERCHE :
ne cite pas un indice après un fait venant du billet ou du voyageur.
Si verified_live vaut false, eligibility doit être uncertain et
estimated_compensation_eur doit être null. Ne transforme jamais une source de
référence non vérifiée en règle confirmée. La lettre doit rester factuelle,
polie, demander confirmation à la compagnie et ne contenir aucun fait inventé.
INDEMNISATION_EU261 et REMBOURSEMENT_BILLET sont deux décisions indépendantes :
un refus d'indemnisation n'annule pas un remboursement indiqué likely ou
conditional. La lettre ne demande que les droits marqués likely ou conditional."""

RESEARCH_TOOL_SYSTEM = """Tu routes un dossier aérien vers des outils.
Tu dois demander les deux outils disponibles, une fois chacun :
1. verify_air_passenger_rule pour les règles officielles ;
2. find_claim_channel pour le canal de réclamation.
Recopie exactement les valeurs du CONTEXTE_MINIMISE dans les arguments.
N'ajoute aucune donnée, ne qualifie pas toi-même le dossier et ne réponds pas
en prose : utilise uniquement les appels d'outils."""

RESEARCH_TOOL_ORDER = (
    "verify_air_passenger_rule",
    "find_claim_channel",
)


class AgentError(RuntimeError):
    """Erreur attendue et présentable à l'utilisateur."""


def _render_pdf_first_page(source: Path, destination: Path) -> None:
    """Rend la première page d'un PDF en PNG avec Poppler."""
    executable = shutil.which("pdftoppm")
    if not executable:
        raise AgentError(
            "PDF non pris en charge : installe Poppler (`brew install poppler`) "
            "ou fournis une image PNG/JPEG."
        )
    prefix = destination.with_suffix("")
    environment = os.environ.copy()
    environment.setdefault("XDG_CACHE_HOME", str(destination.parent))
    completed = subprocess.run(
        [
            executable,
            "-f",
            "1",
            "-singlefile",
            "-png",
            "-r",
            "220",
            str(source),
            str(prefix),
        ],
        capture_output=True,
        check=False,
        env=environment,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0 or not destination.exists():
        detail = completed.stderr.strip().splitlines()[-1:] or ["erreur inconnue"]
        raise AgentError(f"Impossible de convertir le PDF : {detail[0]}")


def _image_bytes(document: Path) -> bytes:
    suffix = document.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return document.read_bytes()
    if suffix != ".pdf":
        raise AgentError("Formats acceptés : PDF, PNG, JPG, JPEG ou WEBP.")
    with tempfile.TemporaryDirectory(prefix="droit-retard-") as directory:
        image_path = Path(directory) / "page.png"
        _render_pdf_first_page(document, image_path)
        return image_path.read_bytes()


def _chat(payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    request = urllib.request.Request(
        OLLAMA_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.URLError as exc:
        raise AgentError(
            "Ollama est inaccessible. Vérifie qu'il est lancé et que "
            f"`{MODEL}` est installé."
        ) from exc


def extract_flight(
    document: Path, incident_text: str | None = None
) -> tuple[dict, float]:
    """Extrait un billet ou justificatif en JSON strict avec Gemma."""
    if not document.is_file():
        raise AgentError(f"Fichier introuvable : {document}")

    user_text = (
        "Analyse ce justificatif de voyage. Un billet seul ne prouve pas qu'un "
        "incident a eu lieu."
    )
    if incident_text:
        user_text += (
            "\nContexte déclaré par le voyageur, distinct du document : "
            f"{incident_text}"
        )

    started = time.perf_counter()
    response = _chat(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": EXTRACTION_SYSTEM},
                {
                    "role": "user",
                    "content": user_text,
                    "images": [
                        base64.b64encode(_image_bytes(document)).decode("ascii")
                    ],
                },
            ],
            "format": FLIGHT_SCHEMA,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
            "keep_alive": "10m",
        }
    )
    duration = time.perf_counter() - started
    try:
        extracted = json.loads(response["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AgentError("Gemma n'a pas renvoyé un JSON exploitable.") from exc
    # Un billet ou une inférence du modèle ne prouve jamais que le voyage a
    # été effectué ou abandonné. Seule une déclaration explicite peut fixer ce
    # fait via merge_incident_statement().
    extracted["trip_completed"] = None
    if extracted.get("booking_reference"):
        uncertain = extracted.setdefault("uncertain_fields", [])
        if "booking_reference_requires_confirmation" not in uncertain:
            uncertain.append("booking_reference_requires_confirmation")
    if incident_text:
        merge_incident_statement(extracted, incident_text)
    return extracted, duration


def merge_incident_statement(extracted: dict[str, Any], statement: str) -> None:
    """Normalise les faits simples déclarés sans ajouter un tour de modèle."""
    normalized = statement.casefold()
    extracted["trip_completed"] = None
    if "annul" in normalized:
        extracted["disruption_type"] = "cancellation"
    elif "refus" in normalized and "embarquement" in normalized:
        extracted["disruption_type"] = "denied_boarding"
    elif "correspondance" in normalized and (
        "rat" in normalized or "manqu" in normalized
    ):
        extracted["disruption_type"] = "missed_connection"
    elif "retard" in normalized:
        extracted["disruption_type"] = "delay"

    duration_pattern = re.compile(
        r"(?:(\d+)\s*h(?:eures?)?"
        r"(?:\s*(\d+)\s*(?:min(?:ute)?s?)?)?"
        r"|(\d+)\s*min(?:ute)?s?)"
    )
    duration_matches = list(duration_pattern.finditer(normalized))
    for match in duration_matches:
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or match.group(3) or 0)
        delay_minutes = hours * 60 + minutes
        if "retard" not in normalized or not 0 < delay_minutes < 24 * 60:
            continue

        before = normalized[max(0, match.start() - 45) : match.start()]
        after = normalized[match.end() : match.end() + 45]
        trailing_marker = re.match(
            r"\s*(?:de\s+retard\s*)?"
            r"(?:(?:au\s+)?(?:départ|depart|décoll\w*|decoll\w*)"
            r"|(?:à|a)\s+(?:l['’]\s*)?(?:arriv\w*|atterr\w*))",
            after,
        )
        trailing_text = trailing_marker.group(0) if trailing_marker else ""
        departure_markers = ("départ", "depart", "décoll", "decoll")
        if any(marker in trailing_text for marker in departure_markers):
            direction = "departure"
        elif "arriv" in trailing_text or "atterr" in trailing_text:
            direction = "arrival"
        else:
            departure_position = max(
                before.rfind("départ"),
                before.rfind("depart"),
                before.rfind("décoll"),
                before.rfind("decoll"),
            )
            arrival_position = max(
                before.rfind("arriv"),
                before.rfind("atterr"),
            )
            if departure_position > arrival_position:
                direction = "departure"
            elif arrival_position >= 0:
                direction = "arrival"
            elif len(duration_matches) == 1:
                direction = "arrival"
            else:
                direction = "unknown"

        if direction == "departure":
            extracted["departure_delay_minutes"] = delay_minutes
        elif direction == "arrival":
            extracted["delay_minutes"] = delay_minutes
            extracted["arrival_delay_minutes"] = delay_minutes

    known_causes = {
        "problème technique": "problème technique déclaré par le voyageur",
        "probleme technique": "problème technique déclaré par le voyageur",
        "météo": "météo déclarée par le voyageur",
        "meteo": "météo déclarée par le voyageur",
        "grève": "grève déclarée par le voyageur",
        "greve": "grève déclarée par le voyageur",
    }
    for marker, cause in known_causes.items():
        if marker in normalized:
            extracted["disruption_cause"] = cause
            break

    abandoned_trip_markers = (
        "je n'ai pas pris le vol",
        "je n’ai pas pris le vol",
        "je n'ai pas voyagé",
        "je n’ai pas voyagé",
        "je n'ai pas voyage",
        "je n’ai pas voyage",
        "j'ai renoncé",
        "j’ai renoncé",
        "j'ai renonce",
        "j’ai renonce",
        "voyage abandonné",
        "voyage abandonne",
    )
    completed_trip_markers = (
        "j'ai pris le vol",
        "j’ai pris le vol",
        "j'ai voyagé",
        "j’ai voyagé",
        "j'ai voyage",
        "j’ai voyage",
        "je suis arrivé",
        "je suis arrivée",
        "je suis arrive",
        "je suis arrivee",
    )
    if any(marker in normalized for marker in abandoned_trip_markers):
        extracted["trip_completed"] = False
    elif any(marker in normalized for marker in completed_trip_markers):
        extracted["trip_completed"] = True

    evidence = extracted.setdefault("evidence", [])
    evidence.append(f"Déclaration du voyageur (non vérifiée) : {statement}")


def route_case(extracted: dict[str, Any]) -> dict[str, Any]:
    """Choisit la prochaine étape sans laisser le modèle inventer des faits."""
    questions: list[str] = []
    missing_identity = [
        field
        for field in ("flight_number", "origin", "destination", "departure_date")
        if not extracted.get(field)
    ]
    if missing_identity:
        questions.append(
            "Le document ne permet pas d'identifier complètement le vol : "
            + ", ".join(missing_identity)
            + "."
        )

    disruption = extracted.get("disruption_type")
    if disruption in {None, "none", "unknown"}:
        questions.append(
            "Que s'est-il passé : retard, annulation, refus d'embarquement "
            "ou correspondance manquée ?"
        )
    elif (
        disruption == "delay"
        and extracted.get("arrival_delay_minutes") is None
        and extracted.get("delay_minutes") is None
    ):
        questions.append(
            "Quelle était l'heure d'arrivée réelle, ou combien de minutes de "
            "retard y avait-il à l'arrivée ?"
        )

    if questions:
        return {
            "status": "needs_information",
            "message": (
                "Le trajet est identifiable, mais les preuves sont insuffisantes "
                "pour évaluer une réclamation sans inventer."
            ),
            "questions": questions,
            "next_tool": None,
        }

    return {
        "status": "ready_for_research",
        "message": (
            "Les faits minimaux sont présents ; les règles doivent être vérifiées."
        ),
        "questions": [],
        "next_tool": "verify_air_passenger_rule",
        "search_query": (
            "official air passenger rights "
            f"{extracted.get('disruption_type')} "
            f"{extracted.get('origin')} {extracted.get('destination')}"
        ),
    }


def _expected_tool_arguments(
    tool_name: str, context: dict[str, Any]
) -> dict[str, Any]:
    """Construit les seuls arguments autorisés pour chaque outil."""
    if tool_name == "verify_air_passenger_rule":
        return {
            "disruption_type": context["disruption_type"],
            "origin": context["origin"],
            "destination": context["destination"],
            "arrival_delay_minutes": context["arrival_delay_minutes"],
            "departure_delay_minutes": context["departure_delay_minutes"],
        }
    if tool_name == "find_claim_channel":
        return {"airline": context["airline"]}
    raise ValueError("outil non autorisé")


def _validate_tool_call(
    tool_call: Any, context: dict[str, Any]
) -> tuple[str, dict[str, Any]]:
    """Valide nom et arguments sans jamais résoudre un nom arbitraire."""
    if not isinstance(tool_call, dict):
        raise ValueError("appel d'outil non structuré")
    function = tool_call.get("function")
    if not isinstance(function, dict):
        raise ValueError("fonction absente")
    name = function.get("name")
    if name not in RESEARCH_TOOL_ORDER:
        raise ValueError("outil hors liste blanche")
    arguments = function.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except json.JSONDecodeError as exc:
            raise ValueError("arguments JSON invalides") from exc
    if not isinstance(arguments, dict):
        raise ValueError("arguments non structurés")
    expected = _expected_tool_arguments(name, context)
    if set(arguments) != set(expected):
        raise ValueError("champs d'arguments invalides")
    if arguments != expected:
        raise ValueError("arguments différents du contexte minimisé")
    return name, expected


def _execute_research_tool(
    tool_name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    """Dispatche uniquement vers les deux fonctions explicitement autorisées."""
    if tool_name == "verify_air_passenger_rule":
        return verify_air_passenger_rule(arguments)
    if tool_name == "find_claim_channel":
        return find_claim_channel(arguments)
    raise ValueError("outil non autorisé")


def research_case(extracted: dict[str, Any]) -> tuple[dict[str, Any], list[dict]]:
    """Laisse Gemma choisir les outils, puis sécurise et exécute chaque appel."""
    context = build_research_context(extracted)
    selector_started = time.perf_counter()
    selector_error: str | None = None
    executed: dict[str, dict[str, Any]] = {}
    selection_source: dict[str, str] = {}
    invalid_calls = 0
    requested_calls = 0
    result_round_trips = 0
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": RESEARCH_TOOL_SYSTEM},
        {
            "role": "user",
            "content": (
                "CONTEXTE_MINIMISE:\n"
                + json.dumps(context, ensure_ascii=False)
            ),
        },
    ]
    for _round in range(2):
        try:
            response = _chat(
                {
                    "model": MODEL,
                    "messages": messages,
                    "tools": RESEARCH_TOOL_DEFINITIONS,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0},
                    "keep_alive": "10m",
                },
                timeout=120,
            )
        except AgentError:
            selector_error = "sélection Gemma indisponible"
            break
        candidate_calls = response.get("message", {}).get("tool_calls", [])
        if not isinstance(candidate_calls, list):
            selector_error = "tool_calls non structuré"
            break
        if not candidate_calls:
            if requested_calls == 0:
                selector_error = "Gemma n'a demandé aucun outil"
            break

        valid_round_calls: list[tuple[str, dict[str, Any]]] = []
        requested_calls += len(candidate_calls)
        for tool_call in candidate_calls:
            try:
                name, arguments = _validate_tool_call(tool_call, context)
            except ValueError:
                invalid_calls += 1
                continue
            if name in executed:
                invalid_calls += 1
                continue
            executed[name] = _execute_research_tool(name, arguments)
            selection_source[name] = "gemma_tool_call"
            valid_round_calls.append((name, arguments))

        if len(executed) == len(RESEARCH_TOOL_ORDER) or not valid_round_calls:
            break

        messages.append(
            {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {"name": name, "arguments": arguments},
                    }
                    for name, arguments in valid_round_calls
                ],
            }
        )
        for name, _arguments in valid_round_calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_name": name,
                    "content": json.dumps(
                        executed[name],
                        ensure_ascii=False,
                    ),
                }
            )
        result_round_trips += 1

    fallback_reason: str | None = None
    if selector_error:
        fallback_reason = selector_error
    elif invalid_calls:
        fallback_reason = f"{invalid_calls} appel(s) Gemma rejeté(s)"

    for name in RESEARCH_TOOL_ORDER:
        if name in executed:
            continue
        arguments = _expected_tool_arguments(name, context)
        executed[name] = _execute_research_tool(name, arguments)
        selection_source[name] = "deterministic_fallback"
        if fallback_reason is None:
            fallback_reason = "outil manquant dans les appels Gemma"

    rights = executed["verify_air_passenger_rule"]
    channel = executed["find_claim_channel"]
    selector_outcome = (
        "gemma_tool_calls"
        if all(
            selection_source[name] == "gemma_tool_call"
            for name in RESEARCH_TOOL_ORDER
        )
        else "deterministic_fallback"
    )
    trace = [
        {
            "step": "select_research_tools",
            "state": "SELECTION_OUTILS_GEMMA",
            "tool": "ollama.chat.tools",
            "duration_seconds": round(time.perf_counter() - selector_started, 2),
            "outcome": selector_outcome,
            "details": fallback_reason,
            "requested_tool_calls": requested_calls,
            "rejected_tool_calls": invalid_calls,
            "tool_result_round_trips": result_round_trips,
        },
        {
            "step": "verify_rule",
            "state": (
                "RECHERCHE_REGLES"
                if rights["status"] == "online"
                else "MODE_DEGRADE"
            ),
            "tool": "verify_air_passenger_rule",
            "selected_by": selection_source["verify_air_passenger_rule"],
            "outcome": rights["status"],
            "details": rights.get("reason"),
        },
        {
            "step": "find_claim_channel",
            "state": "RECHERCHE_CANAL",
            "tool": "find_claim_channel",
            "selected_by": selection_source["find_claim_channel"],
            "outcome": channel["status"],
            "details": channel.get("message"),
        },
    ]
    return {"rights": rights, "claim_channel": channel}, trace


def draft_claim(
    extracted: dict[str, Any],
    research: dict[str, Any],
    qualification: dict[str, Any],
    reimbursement: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    """Génère un dossier prudent à partir des faits et recherches contrôlés."""
    facts_for_claim = dict(extracted)
    if "booking_reference_requires_confirmation" in extracted.get(
        "uncertain_fields", []
    ):
        facts_for_claim["booking_reference"] = None
    prompt = (
        "Prépare le dossier au format demandé.\n\n"
        f"FAITS:\n{json.dumps(facts_for_claim, ensure_ascii=False, indent=2)}\n\n"
        f"RECHERCHE:\n{json.dumps(research, ensure_ascii=False, indent=2)}\n\n"
        "INDEMNISATION_EU261:\n"
        f"{json.dumps(qualification, ensure_ascii=False, indent=2)}\n\n"
        "REMBOURSEMENT_BILLET:\n"
        f"{json.dumps(reimbursement, ensure_ascii=False, indent=2)}"
    )
    started = time.perf_counter()
    response = _chat(
        {
            "model": MODEL,
            "messages": [
                {"role": "system", "content": CLAIM_SYSTEM},
                {"role": "user", "content": prompt},
            ],
            "format": CLAIM_SCHEMA,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
            "keep_alive": "10m",
        }
    )
    duration = time.perf_counter() - started
    try:
        claim = json.loads(response["message"]["content"])
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise AgentError("Gemma n'a pas produit un dossier JSON exploitable.") from exc
    return claim, duration


def process(
    document: Path,
    incident_text: str | None = None,
    confirmed_booking_reference: str | None = None,
) -> dict[str, Any]:
    """Exécute l'extraction et le routage du dossier."""
    extracted, duration = extract_flight(document, incident_text)
    if confirmed_booking_reference:
        extracted["booking_reference"] = confirmed_booking_reference.strip().upper()
        extracted["uncertain_fields"] = [
            field
            for field in extracted.get("uncertain_fields", [])
            if field != "booking_reference_requires_confirmation"
        ]
    route = route_case(extracted)
    result = {
        "model": MODEL,
        "document": str(document),
        "extraction": extracted,
        "decision": route,
        "research": None,
        "qualification": None,
        "reimbursement": None,
        "refusal": None,
        "claim": None,
        "trace": [
            {
                "step": "extract_flight",
                "state": "EXTRACTION",
                "tool": "ollama.chat",
                "duration_seconds": round(duration, 2),
                "outcome": "ok",
            },
            {
                "step": "route_case",
                "state": "VALIDATION_CHAMPS",
                "tool": "deterministic_router",
                "duration_seconds": 0,
                "outcome": route["status"],
            },
        ],
    }
    if route["status"] != "ready_for_research":
        return result

    research, tool_trace = research_case(extracted)
    result["research"] = research
    result["trace"].extend(tool_trace)
    qualification = qualify_case(
        extracted,
        verified_live=bool(research["rights"].get("verified_live")),
    )
    result["qualification"] = qualification
    reimbursement = assess_ticket_reimbursement(
        extracted,
        verified_live=bool(research["rights"].get("verified_live")),
    )
    result["reimbursement"] = reimbursement
    result["trace"].append(
        {
            "step": "qualify_eu261",
            "state": "QUALIFICATION_EU261",
            "tool": "deterministic_rules",
            "duration_seconds": 0,
            "outcome": qualification["status"],
        }
    )
    result["trace"].append(
        {
            "step": "assess_ticket_reimbursement",
            "state": "REMBOURSEMENT_BILLET",
            "tool": "deterministic_rules",
            "duration_seconds": 0,
            "outcome": reimbursement["status"],
        }
    )
    reimbursement_actionable = reimbursement["status"] in {
        "likely",
        "conditional",
    }
    if (
        qualification["status"] == "non_eligible"
        and reimbursement["status"] == "needs_information"
    ):
        result["decision"] = {
            "status": "needs_information",
            "message": (
                "L'indemnisation forfaitaire n'est pas retenue, mais une "
                "information manque pour évaluer le remboursement du billet."
            ),
            "questions": [
                reimbursement.get("question") or reimbursement["reason"]
            ],
            "next_tool": None,
        }
        return result
    if qualification["status"] == "non_eligible" and not reimbursement_actionable:
        result["decision"] = {
            "status": "non_eligible",
            "message": "Le dossier n'atteint pas le seuil d'indemnisation retenu.",
            "questions": [],
            "next_tool": None,
        }
        result["refusal"] = {
            "title": "Aucune lettre de réclamation générée",
            "explanation": qualification["reason"],
            "rule": qualification.get("rule"),
        }
        return result
    if qualification["status"] == "non_eligible" and reimbursement_actionable:
        result["decision"] = {
            "status": "ready_for_claim",
            "message": (
                "Pas d'indemnisation forfaitaire sur les faits déclarés, mais "
                "le remboursement du billet peut être demandé."
            ),
            "questions": [],
            "next_tool": None,
        }
    if qualification["status"] == "needs_information":
        result["decision"] = {
            "status": "needs_information",
            "message": "Une information manque avant la qualification EU261.",
            "questions": [qualification["reason"]],
            "next_tool": None,
        }
        return result

    claim, claim_duration = draft_claim(
        extracted,
        research,
        qualification,
        reimbursement,
    )
    result["claim"] = claim
    if result["decision"]["status"] == "ready_for_research":
        result["decision"] = {
            "status": "ready_for_claim",
            "message": (
                "L'indemnisation a été qualifiée et le dossier de réclamation "
                "est préparé."
            ),
            "questions": (
                [reimbursement.get("question") or reimbursement["reason"]]
                if reimbursement["status"] == "needs_information"
                else []
            ),
            "next_tool": None,
        }
    result["trace"].append(
        {
            "step": "draft_claim",
            "state": (
                "REDACTION"
                if qualification["status"] == "likely"
                else "REDACTION_CONDITIONNELLE"
            ),
            "tool": "ollama.chat",
            "duration_seconds": round(claim_duration, 2),
            "outcome": "ok",
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analyse locale d'un justificatif de voyage aérien."
    )
    parser.add_argument("document", type=Path)
    parser.add_argument(
        "--incident",
        help="Contexte déclaré par le voyageur, par exemple le retard à l'arrivée.",
    )
    parser.add_argument(
        "--booking-reference",
        help="Référence confirmée manuellement pour éviter une erreur de lecture.",
    )
    args = parser.parse_args()
    try:
        result = process(
            args.document,
            args.incident,
            confirmed_booking_reference=args.booking_reference,
        )
    except AgentError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
