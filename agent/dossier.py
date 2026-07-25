"""The dossier: the agent's central object.

Non-negotiable rule of this project: every fact entering the dossier carries a
source and a confidence level. Nothing is asserted without provenance.

The dossier is serializable and journalled after every transition -- it is the
trace the jury reads.

Naming note: identifiers, comments and docstrings are English. Three families of
strings stay French because the spec fixes them as data contracts:
  - the 13 state ids (INIT, EXTRACTION, ...), which appear in the trace;
  - the ticket field names (numero_vol, date_vol, ...), which map one-to-one to
    the letter template placeholders;
  - the confidence scale (haute/moyenne/basse/nulle), imposed on Gemma's output.
Everything shown to the end user is French by design.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

# Confidence scale imposed by the extraction schema.
CONFIDENCE_LEVELS = ("haute", "moyenne", "basse", "nulle")
# Below this, a field cannot be used without asking the user.
RELIABLE_CONFIDENCE = ("haute", "moyenne")

# Without these four fields no EU261 assessment is possible.
REQUIRED_FIELDS = ("numero_vol", "date_vol", "aeroport_depart", "aeroport_arrivee")

# French labels: these are read out loud to the user in the questions.
FIELD_LABELS = {
    "numero_vol": "le numéro de vol",
    "date_vol": "la date du vol",
    "aeroport_depart": "l'aéroport de départ (code IATA)",
    "aeroport_arrivee": "l'aéroport d'arrivée (code IATA)",
}


def new_dossier(ticket_path: str, declaration: str) -> dict[str, Any]:
    """Create an empty dossier."""
    return {
        "ticket_path": ticket_path,
        "user_declaration": declaration,
        # Output of extract_ticket: {field: {valeur, confiance}}
        "extraction": {},
        # The disruption as described by the user, structured.
        "declared_disruption": {},
        # Raw output of search_flight_status.
        "flight_search": None,
        # Consolidated facts: [{fact, value, source, confidence}]
        "verified_facts": [],
        # Detected contradictions: [{fact, user_version, web_version, arbitrated}]
        "conflicts": [],
        # Output of compute_compensation plus the rationale drafted by Gemma.
        "assessment": None,
        "letter": None,
        # True when no external source could be reached.
        "degraded_mode": False,
        # Question put to the user, consumed by the ASK_USER state.
        "pending_question": None,
        # Attempt counters: every loop in the graph is bounded.
        "counters": {
            "extraction": 0,
            "flight_search": 0,
            "self_review": 0,
            # Questions asked per field. An agent that re-asks the same question
            # forever has not survived failure, it has succumbed to it.
            "questions": {},
        },
        # Transition journal: timestamp, state, action, outcome.
        "history": [],
    }


def log_action(dossier: dict, state: str, action: str, outcome: str) -> None:
    """Record an action taken within a state. Called by the states themselves."""
    dossier["history"].append(
        {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "state": state,
            "action": action,
            "outcome": outcome,
        }
    )


def add_fact(dossier: dict, fact: str, value: Any, source: str, confidence: str) -> None:
    """Add a consolidated fact to the dossier, with its provenance."""
    assert confidence in CONFIDENCE_LEVELS, f"unknown confidence level: {confidence}"
    dossier["verified_facts"] = [f for f in dossier["verified_facts"] if f["fact"] != fact]
    dossier["verified_facts"].append(
        {"fact": fact, "value": value, "source": source, "confidence": confidence}
    )


def get_fact(dossier: dict, fact: str) -> dict | None:
    for entry in dossier["verified_facts"]:
        if entry["fact"] == fact:
            return entry
    return None


def field_value(dossier: dict, field: str) -> Any:
    """Value of an extracted field, or None if absent / zero confidence."""
    entry = dossier["extraction"].get(field)
    if not entry:
        return None
    return entry.get("valeur")


def missing_required_field(dossier: dict) -> str | None:
    """First required field that is absent or insufficiently trusted, else None.

    This function feeds the ASK_USER branch. It is deliberately strict: a
    low-confidence field triggers a question rather than an assumption.
    """
    for field in REQUIRED_FIELDS:
        entry = dossier["extraction"].get(field)
        if not entry or entry.get("valeur") in (None, ""):
            return field
        if entry.get("confiance") not in RELIABLE_CONFIDENCE:
            return field
    return None


def unresolved_conflict(dossier: dict) -> dict | None:
    for conflict in dossier["conflicts"]:
        if not conflict.get("arbitrated"):
            return conflict
    return None


def lowest_confidence(dossier: dict) -> str:
    """Lowest confidence among consolidated facts.

    Drives the choice between REDACTION and REDACTION_CONDITIONNELLE.
    """
    if not dossier["verified_facts"]:
        return "nulle"
    # CONFIDENCE_LEVELS runs from most to least reliable, so the highest index
    # is the lowest confidence.
    return max(
        (f["confidence"] for f in dossier["verified_facts"]),
        key=CONFIDENCE_LEVELS.index,
    )
