"""The agent's tools.

STEP 1: most implementations are STUBBED. Values are hardcoded and driven by the
active scenario (see SCENARIOS). The signatures are frozen: they will not change
when the real implementations land.

  - compute_distance / compute_compensation -> DONE, delegated to agent/eu261.py
  - extract_ticket / search_flight_status   -> step 3 (gemma vision / SerpAPI)
  - is_eu_carrier                           -> step 3 (carrier reference table)
  - render_pdf                              -> step 4 (fpdf2)

The reasoning calls entrusted to Gemma (conflict arbitration, drafting, self
review, refusal explanation) are declared here with the same discipline: final
signature, stubbed body.

No state ever calls a model, an API or agent/eu261.py directly -- everything goes
through this module. That is what makes the whole graph testable with stubs.

Naming note: identifiers, comments and docstrings are English. Stay French,
because the spec fixes them as data contracts or because the end user reads them:
  - the ticket field names (numero_vol, date_vol, ...) and their valeur /
    confiance keys, plus the haute/moyenne/basse/nulle confidence scale;
  - the compute_compensation parameter and result names (type_perturbation,
    retard_arrivee_h, reachemine, eligible, montant, ...), frozen by eu261.py;
  - every string printed to the user or written into the letter.
"""

from __future__ import annotations

import re
from typing import Any

from agent import eu261
from agent.eu261 import UnknownAirport  # re-exported: the states catch tools.UnknownAirport

__all__ = [
    "ToolError",
    "ParsingError",
    "NetworkError",
    "UnknownAirport",
    "SCENARIOS",
    "use_scenario",
    "active_scenario",
    "extract_ticket",
    "parse_user_situation",
    "search_flight_status",
    "compute_distance",
    "compute_compensation",
    "check_scope",
    "is_intra_eu",
    "airport_is_known",
    "is_eu_carrier",
    "ask_user",
    "render_pdf",
    "judge_evidence_conflict",
    "motivate_qualification",
    "explain_refusal",
    "draft_letter",
    "review_letter",
]


class ToolError(Exception):
    """A tool failed. Every subtype has a defined transition in the graph."""


class ParsingError(ToolError):
    """The model returned something unusable (malformed JSON)."""


class NetworkError(ToolError):
    """External source unreachable: timeout, quota, zero results."""


# --------------------------------------------------------------------------
# Stubs: hardcoded data, one set per demo scenario
# --------------------------------------------------------------------------

_TICKET_CDG_ATH = {
    "numero_vol": {"valeur": "AF1234", "confiance": "haute"},
    "date_vol": {"valeur": "2026-03-12", "confiance": "haute"},
    "aeroport_depart": {"valeur": "CDG", "confiance": "haute"},
    "aeroport_arrivee": {"valeur": "ATH", "confiance": "moyenne"},
    "ref_reservation": {"valeur": "XKD91P", "confiance": "haute"},
    "nom_passager": {"valeur": "MARTIN/JEAN", "confiance": "haute"},
    "compagnie": {"valeur": "Air France", "confiance": "haute"},
}

# Ticket cropped in the photo: the date is unreadable -> triggers ASK_USER.
_BLURRY_TICKET = dict(
    _TICKET_CDG_ATH,
    date_vol={"valeur": None, "confiance": "nulle"},
)

_WEB_SOURCES = [
    {"title": "AF1234 flight status — 12 Mar 2026", "url": "https://example.org/af1234"},
]

SCENARIOS: dict[str, dict[str, Any]] = {
    "nominal": {
        "label": "Nominal — billet propre, source web disponible, 4 h de retard",
        "declaration": "Mon vol Paris-Athènes est arrivé avec 4 heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 4.0, "reachemine": False},
        "extraction": _TICKET_CDG_ATH,
        "extraction_failures": 0,
        "search": {
            "found": True,
            "retard_arrivee_h": 4.0,
            "cancelled": False,
            "sources": _WEB_SOURCES,
        },
        "search_failures": 0,
        "user_answers": {},
        "review_verdicts": [{"compliant": True, "defects": []}],
    },
    "source_failure": {
        "label": "Panne de source — réseau coupé, bascule en mode dégradé",
        "declaration": "Mon vol Paris-Athènes est arrivé avec 4 heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 4.0, "reachemine": False},
        "extraction": _TICKET_CDG_ATH,
        "extraction_failures": 0,
        "search": None,
        "search_failures": 99,  # fails systematically
        "user_answers": {},
        # First letter non-compliant: proves the correction loop.
        "review_verdicts": [
            {"compliant": False, "defects": ["variable {{montant}} non remplie"]},
            {"compliant": True, "defects": []},
        ],
    },
    "not_eligible": {
        "label": "Non éligible — retard de 2 h 10 à l'arrivée, sous le seuil des 3 h",
        "declaration": "Mon vol est arrivé avec un peu plus de deux heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 2.17, "reachemine": False},
        "extraction": _TICKET_CDG_ATH,
        "extraction_failures": 0,
        "search": {
            "found": True,
            "retard_arrivee_h": 2.17,
            "cancelled": False,
            "sources": _WEB_SOURCES,
        },
        "search_failures": 0,
        "user_answers": {},
        "review_verdicts": [{"compliant": True, "defects": []}],
    },
    "conflicting_evidence": {
        "label": "Preuves contradictoires — utilisateur 4 h, source web 2 h",
        "declaration": "Mon vol est arrivé avec 4 heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 4.0, "reachemine": False},
        "extraction": _TICKET_CDG_ATH,
        "extraction_failures": 0,
        "search": {
            "found": True,
            "retard_arrivee_h": 2.0,
            "cancelled": False,
            "sources": _WEB_SOURCES,
        },
        "search_failures": 0,
        # The user stands by their version when arbitrating.
        "user_answers": {"retard_arrivee_h": "4"},
        "review_verdicts": [{"compliant": True, "defects": []}],
    },
    "blurry_ticket": {
        "label": "Billet illisible — la date manque, l'agent la demande au lieu de l'inventer",
        "declaration": "Mon vol est arrivé avec 4 heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 4.0, "reachemine": False},
        "extraction": _BLURRY_TICKET,
        "extraction_failures": 0,
        "search": {
            "found": True,
            "retard_arrivee_h": 4.0,
            "cancelled": False,
            "sources": _WEB_SOURCES,
        },
        "search_failures": 0,
        "user_answers": {"date_vol": "2026-03-12"},
        "review_verdicts": [{"compliant": True, "defects": []}],
    },
    "malformed_json": {
        "label": "JSON malformé — 2 tentatives échouées, bascule en saisie manuelle",
        "declaration": "Mon vol est arrivé avec 4 heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 4.0, "reachemine": False},
        "extraction": _TICKET_CDG_ATH,
        "extraction_failures": 2,  # the model never returns valid JSON
        "search": {
            "found": True,
            "retard_arrivee_h": 4.0,
            "cancelled": False,
            "sources": _WEB_SOURCES,
        },
        "search_failures": 0,
        "user_answers": {
            "numero_vol": "AF1234",
            "date_vol": "2026-03-12",
            "aeroport_depart": "CDG",
            "aeroport_arrivee": "ATH",
        },
        "review_verdicts": [{"compliant": True, "defects": []}],
    },
    "user_gives_up": {
        "label": "Utilisateur muet — l'agent renonce proprement au lieu d'inventer",
        "declaration": "Mon vol est arrivé avec 4 heures de retard.",
        "disruption": {"type": "retard", "retard_arrivee_h": 4.0, "reachemine": False},
        "extraction": _BLURRY_TICKET,
        "extraction_failures": 0,
        "search": None,
        "search_failures": 0,
        "user_answers": {},  # no answer at all: the date stays out of reach
        "review_verdicts": [{"compliant": True, "defects": []}],
    },
}

_ACTIVE: dict[str, Any] = SCENARIOS["nominal"]
_CALLS = {"extraction": 0, "search": 0, "review": 0}


def use_scenario(name: str) -> dict[str, Any]:
    """Select the stubbed data set. Disappears at step 3."""
    global _ACTIVE
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario: {name} (known: {', '.join(SCENARIOS)})")
    _ACTIVE = SCENARIOS[name]
    for key in _CALLS:
        _CALLS[key] = 0
    return _ACTIVE


def active_scenario() -> dict[str, Any]:
    return _ACTIVE


# --------------------------------------------------------------------------
# The 6 tools
# --------------------------------------------------------------------------


def extract_ticket(image_path: str) -> dict:
    """Read the ticket and return {field: {valeur, confiance}}.

    Real: multimodal gemma4:12b call (step 3).
    Failure modes: malformed JSON, unreadable image, fields absent from the ticket.
    """
    _CALLS["extraction"] += 1
    if _CALLS["extraction"] <= _ACTIVE["extraction_failures"]:
        raise ParsingError(
            "Expecting ',' delimiter: line 4 column 18 (char 92) — réponse tronquée"
        )
    return dict(_ACTIVE["extraction"])


def parse_user_situation(declaration: str) -> dict:
    """Structure the user's free text into {type, retard_arrivee_h, reachemine}.

    Real: Gemma text-mode call (step 3).
    """
    return dict(_ACTIVE["disruption"])


def search_flight_status(flight_number: str, date: str) -> dict:
    """Actual flight status via SerpAPI.

    Structurally unreliable source for a past flight: that is a failure mode to
    handle, not a bug to fix.
    """
    _CALLS["search"] += 1
    if _CALLS["search"] <= _ACTIVE["search_failures"]:
        raise NetworkError("HTTPSConnectionPool(host='serpapi.com'): Read timed out")
    result = _ACTIVE["search"]
    if not result or not result.get("found"):
        raise NetworkError("aucun résultat exploitable pour cette requête")
    return dict(result)


def compute_distance(iata_dep: str, iata_arr: str) -> float:
    """Great-circle distance in km. DETERMINISTIC, never computed by the LLM.

    Thin delegation to eu261 (haversine over data/airports.csv). Raises
    UnknownAirport when an IATA code is missing from the reference table.
    """
    return eu261.compute_distance(iata_dep, iata_arr)


def compute_compensation(
    distance_km: float,
    type_perturbation: str,
    retard_arrivee_h: float,
    reachemine: bool,
    retard_reacheminement_h: float | None,
    *,
    intra_eu: bool = True,
    in_scope: bool = True,
    out_of_scope_reason: str | None = None,
    cancellation_notice_days: int | None = None,
    extraordinary_circumstance: bool = False,
    extraordinary_reason: str | None = None,
) -> dict:
    """EU261 decision table. DETERMINISTIC, pure Python, never the LLM.

    Thin delegation to eu261.compute_compensation. The parameter names are the
    contract frozen by the spec, hence French.

    Returns {eligible, montant, reduction_50, regle_appliquee, motif_refus}.
    """
    return eu261.compute_compensation(
        distance_km,
        type_perturbation,
        retard_arrivee_h,
        reachemine,
        retard_reacheminement_h,
        intra_eu=intra_eu,
        in_scope=in_scope,
        out_of_scope_reason=out_of_scope_reason,
        cancellation_notice_days=cancellation_notice_days,
        extraordinary_circumstance=extraordinary_circumstance,
        extraordinary_reason=extraordinary_reason,
    )


def check_scope(iata_dep: str, iata_arr: str, eu_carrier: bool) -> tuple[bool, str]:
    """Geographic scope of the regulation (art. 3). Deterministic, delegated."""
    return eu261.check_scope(iata_dep, iata_arr, eu_carrier)


def is_intra_eu(iata_dep: str, iata_arr: str) -> bool:
    """True when both endpoints are inside the EU261 area. Delegated."""
    return eu261.is_intra_eu(iata_dep, iata_arr)


def airport_is_known(iata: str) -> bool:
    """True when the IATA code is present in the local reference table.

    Lets a state name the offending airport field without catching a second
    UnknownAirport.
    """
    try:
        eu261.airport(iata)
    except UnknownAirport:
        return False
    return True


# Short EU-carrier list. STUB: step 3 replaces it with a real lookup (ICAO
# operating-licence country). Anything absent is treated as non-EU, which is the
# conservative choice: it only ever narrows the scope of the regulation.
_EU_CARRIERS = frozenset(
    {
        "air france",
        "klm",
        "lufthansa",
        "iberia",
        "vueling",
        "ryanair",
        "easyjet europe",
        "tap",
        "ita airways",
        "brussels airlines",
        "sas",
        "finnair",
        "lot",
        "aegean",
    }
)


def is_eu_carrier(company_name: str) -> bool:
    """Is the operating carrier a Community carrier? (art. 3 §1 b)

    STUB, step 3: hardcoded list. Needed because an EU-arriving flight is only
    in scope when operated by an EU carrier.
    """
    return (company_name or "").strip().lower() in _EU_CARRIERS


def ask_user(question: str, field: str) -> str:
    """Ask ONE targeted question on the CLI.

    Real: input(). Stubbed: scripted answer, so the demo stays replayable.
    """
    answer = _ACTIVE["user_answers"].get(field, "")
    print(f"    ?  {question}")
    print(f"    >  {answer}   [réponse scriptée — bouchon étape 1]")
    return answer


def render_pdf(dossier: dict, letter: str, output_path: str) -> str:
    """Render the letter as a PDF. Real: fpdf2 (step 4)."""
    return output_path


# --------------------------------------------------------------------------
# Reasoning calls entrusted to Gemma (stubbed)
# --------------------------------------------------------------------------


def judge_evidence_conflict(fact: str, user_version: Any, web_version: Any) -> dict:
    """Gemma judges whether two statements describe the same fact or contradict.

    This is reasoning, not string comparison: hence the model call.
    """
    if isinstance(user_version, (int, float)) and isinstance(web_version, (int, float)):
        # 30-minute tolerance: two sources saying "3h" and "3h20" do not
        # contradict each other, they round.
        contradiction = abs(user_version - web_version) > 0.5
    else:
        contradiction = user_version != web_version
    return {
        "contradiction": contradiction,
        "explanation": (
            f"Le déclaratif indique {user_version} et la source web {web_version} : "
            "l'écart dépasse la tolérance d'arrondi, les deux versions ne peuvent pas "
            "décrire le même fait."
            if contradiction
            else "Les deux formulations décrivent le même fait à l'arrondi près."
        ),
    }


def motivate_qualification(dossier: dict, assessment: dict) -> str:
    """Gemma drafts the legal rationale from the deterministic computation."""
    if assessment["eligible"]:
        return (
            "Le vol relevant du champ d'application du règlement, et le retard à "
            "l'arrivée atteignant le seuil de 3 heures, le dossier ouvre droit à "
            f"une indemnisation forfaitaire de {assessment['montant']} €."
        )
    return f"Le dossier n'ouvre pas droit à indemnisation : {assessment['motif_refus']}."


def explain_refusal(dossier: dict) -> str:
    """Gemma explains in French why the case is lost before it starts."""
    assessment = dossier["assessment"]

    if assessment.get("code") == "dossier_incomplet":
        return (
            "Je ne peux pas instruire votre dossier.\n\n"
            f"Motif : {assessment['motif_refus']}.\n\n"
            "Sans cette information, toute demande d'indemnisation serait rejetée par "
            "le transporteur. Je préfère vous le dire plutôt que de produire un courrier "
            "reposant sur une donnée que j'aurais inventée.\n\n"
            "Reprenez la démarche avec une photo lisible du billet ou la confirmation "
            "de réservation reçue par e-mail."
        )

    return (
        "Votre dossier n'ouvre pas droit à indemnisation.\n\n"
        f"Règle appliquée : {assessment['regle_appliquee']}.\n"
        f"Motif : {assessment['motif_refus']}.\n\n"
        "Le règlement (CE) n° 261/2004 ne prévoit d'indemnisation forfaitaire qu'à "
        "partir de trois heures de retard constatées à l'ARRIVÉE, et non au départ. "
        "Aucun courrier de réclamation n'a donc été généré : l'envoyer vous exposerait "
        "à un refus motivé du transporteur.\n\n"
        "Vous conservez en revanche le droit à la prise en charge (restauration, "
        "communications) si elle ne vous a pas été proposée."
    )


def draft_letter(dossier: dict, conditional: bool, defects: list[str] | None = None) -> str:
    """Gemma fills the letter template from the dossier.

    conditional=True: degraded mode, the letter asks the carrier to confirm
    instead of asserting an unverified delay.
    """
    extraction = dossier["extraction"]
    assessment = dossier["assessment"]

    def v(field):
        entry = extraction.get(field) or {}
        return entry.get("valeur") or f"{{{{{field}}}}}"

    if conditional:
        body = (
            f"D'après les éléments en ma possession, le vol {v('numero_vol')} du "
            f"{v('date_vol')} aurait subi un retard significatif à l'arrivée. "
            "N'ayant pu obtenir confirmation de l'heure d'arrivée effective auprès "
            "d'une source indépendante, je vous demande de bien vouloir me confirmer "
            "cette donnée. Si le retard constaté atteint trois heures, je sollicite "
            f"le versement de l'indemnité forfaitaire de {assessment['montant']} €."
        )
    else:
        delay = dossier["declared_disruption"].get("retard_arrivee_h")
        body = (
            f"Le vol {v('numero_vol')} du {v('date_vol')}, reliant "
            f"{v('aeroport_depart')} à {v('aeroport_arrivee')}, est arrivé avec un "
            f"retard de {delay} heures. "
            f"La distance de ce vol étant de {assessment['distance_km']:.0f} km, je vous "
            f"demande le versement d'une indemnité forfaitaire de {assessment['montant']} €."
        )

    if defects:
        # Braces are stripped: without this the correction note would re-inject
        # into the letter the very patterns the reviewer looks for.
        cleaned = [d.replace("{{", "").replace("}}", "") for d in defects]
        body += "\n\n[correction appliquée : " + " ; ".join(cleaned) + "]"

    return (
        f"Objet : Réclamation — règlement (CE) n° 261/2004 — vol {v('numero_vol')} "
        f"du {v('date_vol')} — Réf. {v('ref_reservation')}\n\n"
        "Madame, Monsieur,\n\n"
        f"{body}\n\n"
        "Je vous prie d'agréer, Madame, Monsieur, l'expression de mes salutations "
        "distinguées.\n\n"
        f"{v('nom_passager')}"
    )


def review_letter(dossier: dict, letter: str) -> dict:
    """Second Gemma call, in the posture of a critical reviewer.

    Looks for unfilled variables, facts absent from the dossier (hallucinations),
    amount/distance inconsistencies, tone.
    """
    _CALLS["review"] += 1
    verdicts = _ACTIVE["review_verdicts"]
    index = min(_CALLS["review"] - 1, len(verdicts) - 1)
    verdict = dict(verdicts[index])

    # Deterministic check, kept even once the reviewer becomes a real Gemma
    # call: an unfilled template variable is detectable without a model, and it
    # is the worst defect a letter can carry.
    unfilled = re.findall(r"\{\{(\w+)\}\}", letter)
    if unfilled:
        verdict["compliant"] = False
        verdict["defects"] = list(verdict.get("defects", [])) + [
            f"variable de template non remplie : {{{{{field}}}}}" for field in unfilled
        ]
    return verdict
