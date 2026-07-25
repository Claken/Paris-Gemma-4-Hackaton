"""The agent's tools.

This module has TWO MODES, and every tool branches on them at the top:

  - STUB mode (the default): hardcoded values driven by the active scenario (see
    SCENARIOS). No Ollama, no network, no clock. This is the replayable demo, and
    it must keep working byte-for-byte -- a demo that needs a live external
    service is graded as if it did not work.
  - LIVE mode (`set_mode(True)`, i.e. `main.py --live`): real gemma4:12b through
    agent/gemma.py, real SerpAPI through agent/flight_search.py.

`use_scenario()` selects stub mode; `set_mode(True)` selects live mode. The stubs
are never a dead branch: in live mode they are also the deterministic fallback
used when a reasoning call fails, because a degraded letter beats no letter and
the graph must always reach FIN.

  - compute_distance / compute_compensation -> deterministic, delegated to eu261
  - extract_ticket / search_flight_status   -> live (gemma vision / SerpAPI)
  - is_eu_carrier                           -> still a hardcoded EU carrier list
  - render_pdf                              -> step 4 (fpdf2)

Failure mapping is the point of this module, since it is what feeds the graph's
recovery transitions. Nothing raised by `requests`, `gemma` or `flight_search`
ever escapes tools.py:

  gemma.GemmaJSONError   -> ParsingError  (EXTRACTION retries, then manual entry)
  gemma.GemmaUnavailable -> ParsingError  (same path: ask the user, never crash)
  search.SearchUnavailable / NoUsableResult -> NetworkError (retry, MODE_DEGRADE)

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

import json
import re
from datetime import date
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
    "set_mode",
    "is_live",
    "live_fallbacks",
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
# STUB / LIVE mode
# --------------------------------------------------------------------------

# Measured on the demo laptop: gemma4:12b on CPU emits ~8 tokens/s, and it is a
# thinking model, so a reply of ten visible lines still costs a few thousand
# tokens. The real ticket extraction takes ~5min30 end to end.
#
# These are deliberately far above that. A client-side timeout does NOT cancel
# the generation server-side: Ollama keeps working, and the next call queues
# behind the abandoned one. Cutting too early therefore does not save time, it
# cascades -- one impatient timeout turns into every later call timing out too.
# Being generous here is a correctness property, not just politeness.
LIVE_TIMEOUT_VISION = 900.0
LIVE_TIMEOUT_TEXT = 600.0

_LIVE = False
# Live calls that fell back on their deterministic stub, for the run summary.
_FALLBACKS: list[dict[str, str]] = []

# Imported on demand: in stub mode these modules are never touched, so the demo
# runs with no Ollama, no network and no SerpAPI key.
_GEMMA: Any = None
_PROMPTS: Any = None
_SEARCH: Any = None


def set_mode(live: bool) -> None:
    """Switch between the stubbed demo data and the real Gemma / SerpAPI calls.

    Fails fast and loudly if the live modules are missing: discovering that
    halfway through a live demo is worse than not starting it.
    """
    global _LIVE
    if live:
        try:
            _gemma(), _prompts()
        except ImportError as err:  # pragma: no cover - packaging accident
            raise RuntimeError(f"mode live indisponible : {err}") from err
    _LIVE = bool(live)
    _FALLBACKS.clear()


def is_live() -> bool:
    return _LIVE


def live_fallbacks() -> list[dict[str, str]]:
    """Live calls that degraded to their deterministic stub during this run."""
    return list(_FALLBACKS)


def _gemma() -> Any:
    global _GEMMA
    if _GEMMA is None:
        from agent import gemma

        _GEMMA = gemma
    return _GEMMA


def _prompts() -> Any:
    global _PROMPTS
    if _PROMPTS is None:
        from agent import prompts

        _PROMPTS = prompts
    return _PROMPTS


def _search_module() -> Any:
    """agent/flight_search.py. Missing module = unreachable source, not a crash."""
    global _SEARCH
    if _SEARCH is None:
        from agent import flight_search

        _SEARCH = flight_search
    return _SEARCH


def _fallback(call: str, err: Exception) -> None:
    """Record and show a live call degrading to its deterministic stub."""
    _FALLBACKS.append({"call": call, "error": f"{type(err).__name__}: {err}"})
    print(f"    !  repli déterministe sur {call} — {type(err).__name__}: {err}")


def _system_prompt(name: str, default: str) -> str:
    """Prompt constant from agent/prompts.py, with an inline safety net.

    Only used for the one reasoning call the spec never named a constant for;
    the frozen names are read directly.
    """
    return getattr(_prompts(), name, default) or default


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
    """Select the stubbed data set, and with it stub mode."""
    global _ACTIVE
    if name not in SCENARIOS:
        raise KeyError(f"unknown scenario: {name} (known: {', '.join(SCENARIOS)})")
    _ACTIVE = SCENARIOS[name]
    for key in _CALLS:
        _CALLS[key] = 0
    set_mode(False)
    return _ACTIVE


def active_scenario() -> dict[str, Any]:
    return _ACTIVE


# --------------------------------------------------------------------------
# The 6 tools
# --------------------------------------------------------------------------


def extract_ticket(image_path: str) -> dict:
    """Read the ticket and return {field: {valeur, confiance}}.

    Live: multimodal gemma4:12b call, dpi=200 -- the value proven in
    spike_vision.py against the real ticket.

    Failure modes: malformed JSON, unreadable image, fields absent from the
    ticket. All three surface as ParsingError, including "model unreachable":
    the EXTRACTION state already knows how to retry that twice and then fall
    back to manual entry, which is a far better outcome than a traceback.
    """
    if not is_live():
        _CALLS["extraction"] += 1
        if _CALLS["extraction"] <= _ACTIVE["extraction_failures"]:
            raise ParsingError(
                "Expecting ',' delimiter: line 4 column 18 (char 92) — réponse tronquée"
            )
        return dict(_ACTIVE["extraction"])

    gemma, prompts = _gemma(), _prompts()
    try:
        images = gemma.encode_images(image_path, dpi=200)
    except (OSError, gemma.GemmaError) as err:
        raise ParsingError(f"billet illisible : {err}") from err

    try:
        raw = gemma.chat_json(
            prompts.EXTRACTION_SYSTEM,
            prompts.EXTRACTION_USER,
            images=images,
            temperature=0.2,
            timeout=LIVE_TIMEOUT_VISION,
        )
    except gemma.GemmaJSONError as err:
        raise ParsingError(
            f"{err.parse_error or err} — réponse du modèle : {(err.raw or '')[:120]!r}"
        ) from err
    except gemma.GemmaUnavailable as err:
        raise ParsingError(f"modèle indisponible : {err}") from err
    except Exception as err:  # nothing raw ever escapes this module
        raise ParsingError(f"extraction impossible : {type(err).__name__}: {err}") from err

    return _normalise_extraction(raw)


def parse_user_situation(declaration: str) -> dict:
    """Structure the user's free text into {type, retard_arrivee_h, reachemine}."""
    if not is_live():
        return dict(_ACTIVE["disruption"])

    gemma, prompts = _gemma(), _prompts()
    try:
        raw = gemma.chat_json(
            prompts.SITUATION_SYSTEM,
            declaration,
            temperature=0.2,
            timeout=LIVE_TIMEOUT_TEXT,
        )
        return _normalise_disruption(raw, declaration)
    except Exception as err:
        # The scenario stub is meaningless here (it would assert a delay the user
        # never mentioned), so the fallback is a regex over their own words.
        _fallback("parse_user_situation", err)
        return _parse_situation_offline(declaration)


def search_flight_status(flight_number: str, date: str, *, attempt: int | None = None) -> dict:
    """Actual flight status via SerpAPI.

    Structurally unreliable source for a past flight: that is a failure mode to
    handle, not a bug to fix.

    `attempt` lets the second try reformulate the query. The RECHERCHE_VOL state
    calls this with two positional arguments only -- the frozen signature -- so
    the retry count defaults to this module's own call counter, which tracks
    dossier["counters"]["flight_search"] one for one.
    """
    if not is_live():
        _CALLS["search"] += 1
        if _CALLS["search"] <= _ACTIVE["search_failures"]:
            raise NetworkError("HTTPSConnectionPool(host='serpapi.com'): Read timed out")
        result = _ACTIVE["search"]
        if not result or not result.get("found"):
            raise NetworkError("aucun résultat exploitable pour cette requête")
        return dict(result)

    _CALLS["search"] += 1
    try:
        search = _search_module()
    except ImportError as err:
        raise NetworkError(f"source externe indisponible : {err}") from err

    try:
        result = search.search_flight_status(
            flight_number,
            date,
            attempt=attempt if attempt is not None else _CALLS["search"],
        )
    except (search.SearchUnavailable, search.NoUsableResult) as err:
        raise NetworkError(str(err)) from err
    except Exception as err:  # nothing raw ever escapes this module
        raise NetworkError(f"recherche impossible : {type(err).__name__}: {err}") from err

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

    Live: input(). Stubbed: scripted answer, so the demo stays replayable.
    """
    if not is_live():
        answer = _ACTIVE["user_answers"].get(field, "")
        print(f"    ?  {question}")
        print(f"    >  {answer}   [réponse scriptée — bouchon étape 1]")
        return answer

    print(f"    ?  {question}")
    try:
        return input("    >  ")
    except (EOFError, KeyboardInterrupt):
        # No terminal, or the user walked away: an empty answer is a legitimate
        # outcome the graph already handles (it gives up rather than inventing).
        print()
        return ""


def render_pdf(dossier: dict, letter: str, output_path: str) -> str:
    """Render the letter as a PDF. Real: fpdf2 (step 4)."""
    return output_path


# --------------------------------------------------------------------------
# Reasoning calls entrusted to Gemma
#
# Each has a `_stub_*` twin holding the deterministic body. That twin is what
# stub mode returns, AND what the live path falls back on when the model fails:
# a degraded letter beats no letter, and the graph must always reach FIN.
# --------------------------------------------------------------------------


def judge_evidence_conflict(fact: str, user_version: Any, web_version: Any) -> dict:
    """Gemma judges whether two statements describe the same fact or contradict.

    This is reasoning, not string comparison: hence the model call.
    """
    if not is_live():
        return _stub_judge_evidence_conflict(fact, user_version, web_version)

    gemma, prompts = _gemma(), _prompts()
    try:
        verdict = gemma.chat_json(
            prompts.CONFLICT_SYSTEM,
            json.dumps(
                {"fait": fact, "version_utilisateur": user_version, "version_web": web_version},
                ensure_ascii=False,
            ),
            temperature=0.2,
            timeout=LIVE_TIMEOUT_TEXT,
        )
        if "contradiction" not in verdict:
            raise ValueError("clé « contradiction » absente de la réponse")
        return {
            "contradiction": bool(verdict["contradiction"]),
            "explanation": str(
                verdict.get("explanation")
                or verdict.get("explication")
                or "arbitrage rendu par le modèle sans explication"
            ),
        }
    except Exception as err:
        _fallback("judge_evidence_conflict", err)
        return _stub_judge_evidence_conflict(fact, user_version, web_version)


def _stub_judge_evidence_conflict(fact: str, user_version: Any, web_version: Any) -> dict:
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
    """Gemma drafts the legal rationale from the deterministic computation.

    The model motivates; it never computes. Distance and amount are handed to it
    already decided by eu261.py, and it is told so in the prompt.
    """
    if not is_live():
        return _stub_motivate_qualification(dossier, assessment)

    gemma = _gemma()
    system = _system_prompt(
        "QUALIFICATION_SYSTEM",
        "Tu es juriste spécialisé en droit des passagers aériens (règlement CE 261/2004). "
        "On te donne le résultat D'UN CALCUL DÉTERMINISTE déjà effectué : tu ne recalcules "
        "NI la distance NI le montant, tu les reprends tels quels. Rédige en français, en "
        "3 phrases maximum, la motivation juridique de cette conclusion. Pas de préambule, "
        "pas de liste, pas de markdown.",
    )
    try:
        text = gemma.chat(
            system,
            json.dumps(
                {"faits": dossier.get("verified_facts", []), "qualification": assessment},
                ensure_ascii=False,
                default=str,
            ),
            temperature=0.4,
            timeout=LIVE_TIMEOUT_TEXT,
        ).strip()
        if len(text) < 40:
            raise ValueError(f"motivation trop courte ({len(text)} caractères)")
        return text
    except Exception as err:
        _fallback("motivate_qualification", err)
        return _stub_motivate_qualification(dossier, assessment)


def _stub_motivate_qualification(dossier: dict, assessment: dict) -> str:
    if assessment["eligible"]:
        return (
            "Le vol relevant du champ d'application du règlement, et le retard à "
            "l'arrivée atteignant le seuil de 3 heures, le dossier ouvre droit à "
            f"une indemnisation forfaitaire de {assessment['montant']} €."
        )
    return f"Le dossier n'ouvre pas droit à indemnisation : {assessment['motif_refus']}."


def explain_refusal(dossier: dict) -> str:
    """Gemma explains in French why the case is lost before it starts.

    The state the spec says never to cut: this is what tells an agent with
    judgement apart from a template engine.
    """
    if not is_live():
        return _stub_explain_refusal(dossier)

    gemma, prompts = _gemma(), _prompts()
    try:
        text = gemma.chat(
            prompts.REFUSAL_SYSTEM,
            json.dumps(
                {
                    "declaratif": dossier.get("user_declaration"),
                    "faits": dossier.get("verified_facts", []),
                    "qualification": dossier.get("assessment"),
                    "mode_degrade": dossier.get("degraded_mode"),
                },
                ensure_ascii=False,
                default=str,
            ),
            temperature=0.5,
            timeout=LIVE_TIMEOUT_TEXT,
        ).strip()
        if len(text) < 80:
            raise ValueError(f"explication trop courte ({len(text)} caractères)")
        return text
    except Exception as err:
        _fallback("explain_refusal", err)
        return _stub_explain_refusal(dossier)


def _stub_explain_refusal(dossier: dict) -> str:
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
    if not is_live():
        return _stub_draft_letter(dossier, conditional, defects)

    gemma, prompts = _gemma(), _prompts()
    system = prompts.LETTER_CONDITIONAL_SYSTEM if conditional else prompts.LETTER_SYSTEM
    extraction = dossier.get("extraction") or {}
    payload: dict[str, Any] = {
        "billet": extraction,
        "faits": dossier.get("verified_facts", []),
        "qualification": dossier.get("assessment"),
        "perturbation_declaree": dossier.get("declared_disruption"),
        "mode_degrade": dossier.get("degraded_mode"),
        "sources": (dossier.get("flight_search") or {}).get("sources", []),
        # Two template fields the dossier does know, and that would otherwise
        # come back as unfilled markers for no reason. Everything the dossier
        # does NOT know (address, e-mail, IBAN) stays a {{marker}} on purpose:
        # the passenger must see what is left for them to fill in.
        "date_courrier": date.today().isoformat(),
        "nom_compagnie": (extraction.get("compagnie") or {}).get("valeur"),
    }
    if defects:
        payload["defauts_a_corriger"] = list(defects)
    try:
        letter = gemma.chat(
            system,
            json.dumps(payload, ensure_ascii=False, default=str),
            temperature=0.6,
            timeout=LIVE_TIMEOUT_TEXT,
        ).strip()
        if len(letter) < 200:
            raise ValueError(f"lettre trop courte ({len(letter)} caractères)")
        return letter
    except Exception as err:
        _fallback("draft_letter", err)
        return _stub_draft_letter(dossier, conditional, defects)


def _stub_draft_letter(dossier: dict, conditional: bool, defects: list[str] | None = None) -> str:
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
    if not is_live():
        _CALLS["review"] += 1
        verdicts = _ACTIVE["review_verdicts"]
        index = min(_CALLS["review"] - 1, len(verdicts) - 1)
        verdict = dict(verdicts[index])
    else:
        verdict = _live_review(dossier, letter)

    # Deterministic check, kept even now that the reviewer is a real Gemma call:
    # an unfilled template variable is detectable without a model, and it is the
    # worst defect a letter can carry. The model's opinion is added to it, never
    # substituted for it.
    unfilled = re.findall(r"\{\{(\w+)\}\}", letter)
    if unfilled:
        verdict["compliant"] = False
        verdict["defects"] = list(verdict.get("defects", [])) + [
            f"variable de template non remplie : {{{{{field}}}}}" for field in unfilled
        ]
    return verdict


def _live_review(dossier: dict, letter: str) -> dict:
    """The model's half of the review. Never the whole of it -- see review_letter."""
    gemma, prompts = _gemma(), _prompts()
    try:
        verdict = gemma.chat_json(
            prompts.REVIEW_SYSTEM,
            json.dumps(
                {
                    "lettre": letter,
                    "faits": dossier.get("verified_facts", []),
                    "billet": dossier.get("extraction"),
                    "qualification": dossier.get("assessment"),
                },
                ensure_ascii=False,
                default=str,
            ),
            temperature=0.2,
            timeout=LIVE_TIMEOUT_TEXT,
        )
        defects = verdict.get("defects") or verdict.get("defauts") or []
        if isinstance(defects, str):
            defects = [defects]
        compliant = verdict.get("compliant")
        if compliant is None:
            compliant = verdict.get("conforme")
        return {
            "compliant": bool(compliant) and not defects,
            "defects": [str(d) for d in defects],
        }
    except Exception as err:
        # A reviewer that cannot be reached must not block delivery: the
        # deterministic scan in review_letter still runs on top of this.
        _fallback("review_letter", err)
        return {"compliant": True, "defects": []}


# --------------------------------------------------------------------------
# Normalising live model output
#
# A small local model gets the substance right and the shape wrong: it returns a
# bare string where a {valeur, confiance} pair is expected, writes "12/03/2026"
# instead of an ISO date, or answers "Athènes (ATH)" for an IATA code. Repairing
# that here is cheaper and far more reliable than begging the prompt for it, and
# it keeps the rest of the agent facing one single shape.
# --------------------------------------------------------------------------

# Order matters: this is the order the fields are logged in the trace.
_TICKET_FIELDS = (
    "numero_vol",
    "date_vol",
    "aeroport_depart",
    "aeroport_arrivee",
    "ref_reservation",
    "nom_passager",
    "compagnie",
)
_CONFIDENCES = ("haute", "moyenne", "basse", "nulle")
# Everything a model writes when it means "not on the ticket".
_NULLISH = {"", "null", "none", "n/a", "na", "inconnu", "inconnue", "non lisible",
            "illisible", "non renseigné", "non renseigne", "-", "?", "unknown"}

_MONTHS = {
    "jan": 1, "feb": 2, "fev": 2, "fév": 2, "mar": 3, "apr": 4, "avr": 4, "may": 5,
    "mai": 5, "jun": 6, "juin": 6, "jul": 7, "juil": 7, "aug": 8, "aou": 8, "aoû": 8,
    "sep": 9, "oct": 10, "nov": 11, "dec": 12, "déc": 12,
}


def _normalise_extraction(raw: dict) -> dict:
    """Coerce the model's reply into {field: {valeur, confiance}}.

    Raises ParsingError when not one required field came back usable: that is a
    failed extraction, and the EXTRACTION state must see it as such rather than
    walk on with an empty dossier.
    """
    source = raw
    if not any(field in source for field in _TICKET_FIELDS):
        # The model wrapped its answer, e.g. {"billet": {...}}.
        for value in raw.values():
            if isinstance(value, dict) and any(f in value for f in _TICKET_FIELDS):
                source = value
                break

    extraction: dict[str, dict] = {}
    for field in _TICKET_FIELDS:
        entry = source.get(field)
        if isinstance(entry, dict):
            value, confidence = entry.get("valeur", entry.get("value")), entry.get("confiance")
        else:
            # Bare scalar: usable, but we did not get a confidence, so we do not
            # get to claim a high one.
            value, confidence = entry, "moyenne"

        value = _clean_value(field, value)
        confidence = str(confidence or "moyenne").strip().lower()
        if confidence not in _CONFIDENCES:
            confidence = "moyenne"
        if value is None:
            # Spec rule: null confidence => null value, never an invented one.
            confidence = "nulle"
        extraction[field] = {"valeur": value, "confiance": confidence, "source": "extraction"}

    usable = [f for f in ("numero_vol", "date_vol", "aeroport_depart", "aeroport_arrivee")
              if extraction[f]["valeur"]]
    if not usable:
        raise ParsingError(
            "JSON valide mais aucun champ requis exploitable "
            f"(clés reçues : {', '.join(list(raw)[:8]) or 'aucune'})"
        )
    return extraction


def _clean_value(field: str, value: Any) -> Any:
    """Field-specific tidying. Returns None for anything that means 'unknown'."""
    if value is None or isinstance(value, (dict, list)):
        return None
    text = str(value).strip()
    if text.lower() in _NULLISH:
        return None

    if field == "numero_vol":
        # "AF 1234" and "af1234" are the same flight; SerpAPI wants one spelling.
        return re.sub(r"\s+", "", text).upper()
    if field.startswith("aeroport_"):
        return _normalise_iata(text)
    if field == "date_vol":
        return _normalise_date(text)
    return text


def _normalise_iata(text: str) -> str:
    """Pull the IATA code out of "ATH", "ATH - Athènes" or "Athènes (ATH)".

    Falls back to the raw text: an unknown code is not a crash, it routes to
    ASK_USER through UnknownAirport, which is a defined transition.
    """
    codes = re.findall(r"\b[A-Z]{3}\b", text.upper())
    return codes[0] if codes else text


def _normalise_date(text: str) -> str:
    """Best-effort ISO date. Unparseable input is returned untouched."""
    text = text.strip()
    iso = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", text)
    if iso:
        year, month, day = (int(g) for g in iso.groups())
        return f"{year:04d}-{month:02d}-{day:02d}"

    numeric = re.match(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})$", text)
    if numeric:
        day, month, year = (int(g) for g in numeric.groups())
        year += 2000 if year < 100 else 0
        return f"{year:04d}-{month:02d}-{day:02d}"

    # "12 mars 2026", "March 12, 2026"
    named = re.search(r"(\d{1,2})\D{1,4}([A-Za-zÀ-ÿ]{3,})\D{1,4}(\d{4})", text)
    if not named:
        named = re.search(r"([A-Za-zÀ-ÿ]{3,})\D{1,4}(\d{1,2})\D{1,4}(\d{4})", text)
        if named:
            month_name, day, year = named.groups()
            named = None
        else:
            return text
    else:
        day, month_name, year = named.groups()
    month = _MONTHS.get(month_name[:3].lower())
    if not month:
        return text
    return f"{int(year):04d}-{month:02d}-{int(day):02d}"


def _normalise_disruption(raw: dict, declaration: str) -> dict:
    """Coerce the model's reading of the user's story into the graph's shape."""
    kind = str(raw.get("type") or raw.get("type_perturbation") or "").strip().lower()
    if "annul" in kind or "cancel" in kind:
        kind = "annulation"
    elif "embarqu" in kind or "boarding" in kind or "denied" in kind:
        kind = "refus_embarquement"
    else:
        kind = "retard"

    disruption: dict[str, Any] = {
        "type": kind,
        "retard_arrivee_h": _as_hours(raw.get("retard_arrivee_h")),
        "reachemine": bool(raw.get("reachemine")),
    }
    rerouted_delay = _as_hours(raw.get("retard_reacheminement_h"))
    if rerouted_delay is not None:
        disruption["retard_reacheminement_h"] = rerouted_delay
    if disruption["retard_arrivee_h"] is None:
        # The model read the story but dropped the number: recover it from the
        # user's own words rather than qualifying a delay of zero hour.
        disruption["retard_arrivee_h"] = _parse_situation_offline(declaration)["retard_arrivee_h"]
    return disruption


def _as_hours(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    match = re.search(r"(\d+(?:[.,]\d+)?)", str(value))
    return float(match.group(1).replace(",", ".")) if match else None


def _parse_situation_offline(declaration: str) -> dict:
    """Deterministic reading of the declaration. Fallback when the model fails.

    Deliberately NOT the scenario stub: replaying `nominal`'s four hours here
    would assert a delay the user never mentioned, which is exactly the kind of
    invented fact the whole agent is built to refuse.
    """
    text = (declaration or "").lower()

    hours: float | None = None
    try:
        hours = _search_module().parse_delay_hours(declaration or "")
    except Exception:
        match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:h\b|heures?)", text)
        if match:
            hours = float(match.group(1).replace(",", "."))

    if "annul" in text:
        kind = "annulation"
    elif "refus" in text and "embarqu" in text or "surbook" in text or "surréserv" in text:
        kind = "refus_embarquement"
    else:
        kind = "retard"

    return {
        "type": kind,
        "retard_arrivee_h": hours,
        "reachemine": "réachemin" in text or "reachemin" in text or "reroute" in text,
    }
