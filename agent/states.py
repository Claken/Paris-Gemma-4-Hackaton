"""One function per state. Uniform signature: (dossier) -> (next_state, dossier).

None of these functions calls a model or an API directly: they all go through
agent/tools.py. That is what makes it possible to validate the 4 demo paths with
stubbed tools before wiring anything real.

Every tool call that can fail has an explicit failure transition. No loop is
unbounded: the dossier counters bound them.

Naming note: identifiers, comments and docstrings are English. The 13 state ids
stay French-cased as the spec fixes them (they appear in the demo trace), as do
the ticket field names and everything the user reads.
"""

from __future__ import annotations

from agent import tools
from agent.dossier import (
    FIELD_LABELS,
    add_fact,
    field_value,
    get_fact,
    log_action,
    lowest_confidence,
    missing_required_field,
)

# Recovery bounds, imposed by the spec.
MAX_EXTRACTION_ATTEMPTS = 2
MAX_SEARCH_RETRIES = 2
MAX_DRAFTING_LOOPS = 2
# Beyond this, the agent gives up cleanly rather than re-asking the same question.
MAX_QUESTIONS_PER_FIELD = 2


def state_init(dossier: dict) -> tuple[str, dict]:
    """Load the ticket image and structure the user's prompt."""
    dossier["declared_disruption"] = tools.parse_user_situation(dossier["user_declaration"])
    log_action(
        dossier,
        "INIT",
        "chargement du billet + déclaratif",
        f"perturbation déclarée : {dossier['declared_disruption']}",
    )
    return "EXTRACTION", dossier


def state_extraction(dossier: dict) -> tuple[str, dict]:
    """Gemma reads the ticket and returns JSON with a confidence per field."""
    dossier["counters"]["extraction"] += 1
    attempt = dossier["counters"]["extraction"]
    try:
        dossier["extraction"] = tools.extract_ticket(dossier["ticket_path"])
    except tools.ParsingError as err:
        log_action(dossier, "EXTRACTION", f"tentative {attempt}", f"JSON invalide : {err}")
        if attempt < MAX_EXTRACTION_ATTEMPTS:
            # Reprompt with the parsing error message.
            return "EXTRACTION", dossier
        # Definitive failure: fall back to manual entry rather than give up.
        dossier["extraction"] = {}
        dossier["pending_question"] = {
            "field": "numero_vol",
            "target": "extraction",
            "question": (
                "Je n'ai pas réussi à lire le billet après deux tentatives. "
                "Quel est le numéro de vol ?"
            ),
            "reason": "sans numéro de vol, aucune vérification ni qualification n'est possible",
        }
        log_action(
            dossier,
            "EXTRACTION",
            "abandon de l'extraction automatique",
            f"{MAX_EXTRACTION_ATTEMPTS} tentatives échouées, bascule en saisie manuelle",
        )
        return "ASK_USER", dossier

    fields = ", ".join(f"{k}={v.get('confiance')}" for k, v in dossier["extraction"].items())
    log_action(dossier, "EXTRACTION", f"tentative {attempt}", f"JSON parsé ({fields})")
    return "VALIDATION_CHAMPS", dossier


def state_field_validation(dossier: dict) -> tuple[str, dict]:
    """Check presence AND confidence of required fields. Pure code, no model."""
    field = missing_required_field(dossier)
    if field is None:
        log_action(
            dossier,
            "VALIDATION_CHAMPS",
            "contrôle des champs requis",
            "tous présents et de confiance suffisante",
        )
        return "RECHERCHE_VOL", dossier

    entry = dossier["extraction"].get(field) or {}
    confidence = entry.get("confiance", "absente")
    dossier["pending_question"] = {
        "field": field,
        "target": "extraction",
        "question": f"Pouvez-vous me préciser {FIELD_LABELS[field]} ?",
        "reason": (
            f"ce champ est nécessaire pour qualifier le dossier et je le lis avec une "
            f"confiance « {confidence} » : je préfère vous le demander plutôt que de l'inventer"
        ),
    }
    log_action(
        dossier,
        "VALIDATION_CHAMPS",
        "contrôle des champs requis",
        f"champ « {field} » insuffisant (confiance : {confidence})",
    )
    return "ASK_USER", dossier


def state_ask_user(dossier: dict) -> tuple[str, dict]:
    """Ask ONE targeted question, explaining why it is necessary."""
    question = dossier["pending_question"]
    if question is None:
        # Guard: never stay stuck in this state without a question to ask.
        log_action(dossier, "ASK_USER", "aucune question en attente", "retour à la validation")
        return "VALIDATION_CHAMPS", dossier

    field = question["field"]
    asked = dossier["counters"]["questions"]
    if asked.get(field, 0) >= MAX_QUESTIONS_PER_FIELD:
        # The user is not providing the information: give up cleanly. Inventing
        # the value and re-asking forever are the two wrong answers.
        return _give_up_on_case(dossier, field)

    asked[field] = asked.get(field, 0) + 1
    print(f"    i  {question['reason']}")
    answer = (tools.ask_user(question["question"], field) or "").strip()

    if question["target"] == "arbitration":
        _apply_arbitration(dossier, question, answer)
    elif answer:
        dossier["extraction"][field] = {
            "valeur": answer,
            "confiance": "haute",
            "source": "utilisateur",
        }
        log_action(
            dossier,
            "ASK_USER",
            f"saisie du champ « {field} »",
            f"valeur « {answer} » (source : utilisateur, confiance : haute)",
        )
    else:
        # Empty answer: we do not fabricate a value, confidence stays "nulle".
        dossier["extraction"][field] = {
            "valeur": None,
            "confiance": "nulle",
            "source": "utilisateur",
        }
        log_action(
            dossier,
            "ASK_USER",
            f"saisie du champ « {field} »",
            f"réponse vide (tentative {asked[field]}/{MAX_QUESTIONS_PER_FIELD})",
        )

    dossier["pending_question"] = None
    return "VALIDATION_CHAMPS", dossier


def _give_up_on_case(dossier: dict, field: str) -> tuple[str, dict]:
    """Clean exit when an indispensable piece of information stays out of reach."""
    dossier["pending_question"] = None
    dossier["assessment"] = {
        "code": "dossier_incomplet",
        "eligible": False,
        "montant": 0,
        "reduction_50": False,
        "distance_km": 0.0,
        "regle_appliquee": "instruction impossible : information indispensable manquante",
        "motif_refus": (
            f"le champ « {field} » n'a pas pu être obtenu après "
            f"{MAX_QUESTIONS_PER_FIELD} demandes"
        ),
        "rationale": "",
    }
    log_action(
        dossier,
        "ASK_USER",
        f"abandon de l'instruction sur « {field} »",
        f"{MAX_QUESTIONS_PER_FIELD} demandes sans réponse exploitable",
    )
    return "EXPLICATION_REFUS", dossier


def _apply_arbitration(dossier: dict, question: dict, answer: str) -> None:
    """The user settles an evidence conflict. The agent never settles it alone."""
    fact = question["field"]
    try:
        value: object = float(answer)
    except (TypeError, ValueError):
        value = answer
    for conflict in dossier["conflicts"]:
        if conflict["fact"] == fact and not conflict.get("arbitrated"):
            conflict["arbitrated"] = True
            conflict["retained_value"] = value
            break
    add_fact(dossier, fact, value, source="arbitrage_utilisateur", confidence="haute")
    log_action(
        dossier,
        "ASK_USER",
        f"arbitrage du conflit sur « {fact} »",
        f"valeur retenue : {value} (source : arbitrage_utilisateur)",
    )


def state_flight_search(dossier: dict) -> tuple[str, dict]:
    """Query SerpAPI to recover the flight's actual status."""
    if dossier["flight_search"] is not None:
        # We come back here after an arbitration: no point replaying the search.
        log_action(dossier, "RECHERCHE_VOL", "recherche déjà effectuée", "non rejouée")
        return "CONSOLIDATION_PREUVES", dossier

    dossier["counters"]["flight_search"] += 1
    attempt = dossier["counters"]["flight_search"]
    try:
        dossier["flight_search"] = tools.search_flight_status(
            field_value(dossier, "numero_vol"), field_value(dossier, "date_vol")
        )
    except tools.NetworkError as err:
        log_action(dossier, "RECHERCHE_VOL", f"essai {attempt}", f"échec : {err}")
        if attempt <= MAX_SEARCH_RETRIES:
            # Backoff; on the 2nd attempt the query would be reworded (step 3).
            return "RECHERCHE_VOL", dossier
        log_action(
            dossier,
            "RECHERCHE_VOL",
            "abandon de la source externe",
            f"{attempt} essais échoués, bascule en mode dégradé",
        )
        return "MODE_DEGRADE", dossier

    log_action(
        dossier,
        "RECHERCHE_VOL",
        f"essai {attempt}",
        f"résultat exploitable : {dossier['flight_search']}",
    )
    return "CONSOLIDATION_PREUVES", dossier


def state_degraded_mode(dossier: dict) -> tuple[str, dict]:
    """No external source. Fall back on the user's account alone, flagged as such.

    The agent carries on instead of crashing -- but it does not forget that its
    evidence is weak.
    """
    dossier["degraded_mode"] = True
    disruption = dossier["declared_disruption"]
    add_fact(dossier, "type_perturbation", disruption.get("type"), "declaratif", "basse")
    add_fact(
        dossier,
        "retard_arrivee_h",
        disruption.get("retard_arrivee_h"),
        source="declaratif",
        confidence="basse",
    )
    log_action(
        dossier,
        "MODE_DEGRADE",
        "repli sur le déclaratif utilisateur",
        "tous les faits marqués source=declaratif, confiance=basse",
    )
    return "QUALIFICATION_EU261", dossier


def state_evidence_consolidation(dossier: dict) -> tuple[str, dict]:
    """Confront the user's account with the web sources. Gemma judges conflicts."""
    declared = dossier["declared_disruption"].get("retard_arrivee_h")
    web = (dossier["flight_search"] or {}).get("retard_arrivee_h")

    add_fact(
        dossier,
        "type_perturbation",
        dossier["declared_disruption"].get("type"),
        source="declaratif",
        confidence="haute",
    )

    # Conflict already arbitrated by the user: keep their value, do not re-judge.
    already_arbitrated = next(
        (
            c
            for c in dossier["conflicts"]
            if c["fact"] == "retard_arrivee_h" and c.get("arbitrated")
        ),
        None,
    )
    if already_arbitrated is not None:
        log_action(
            dossier,
            "CONSOLIDATION_PREUVES",
            "reprise après arbitrage",
            f"valeur retenue : {already_arbitrated['retained_value']} h",
        )
        return "QUALIFICATION_EU261", dossier

    verdict = tools.judge_evidence_conflict("retard_arrivee_h", declared, web)
    if verdict["contradiction"]:
        dossier["conflicts"].append(
            {
                "fact": "retard_arrivee_h",
                "user_version": declared,
                "web_version": web,
                "explanation": verdict["explanation"],
                "arbitrated": False,
            }
        )
        dossier["pending_question"] = {
            "field": "retard_arrivee_h",
            "target": "arbitration",
            "question": (
                f"Vous indiquez {declared} h de retard à l'arrivée, la source web indique "
                f"{web} h. Quelle valeur retenez-vous ? (en heures)"
            ),
            "reason": (
                "je ne tranche pas seul entre deux sources qui se contredisent : "
                f"{verdict['explanation']}"
            ),
        }
        log_action(
            dossier,
            "CONSOLIDATION_PREUVES",
            "confrontation déclaratif / source web",
            f"contradiction détectée ({declared} h vs {web} h), arbitrage demandé",
        )
        return "ASK_USER", dossier

    add_fact(dossier, "retard_arrivee_h", web, source="serpapi", confidence="haute")
    log_action(
        dossier,
        "CONSOLIDATION_PREUVES",
        "confrontation déclaratif / source web",
        f"preuves cohérentes ({declared} h vs {web} h)",
    )
    return "QUALIFICATION_EU261", dossier


def state_eu261_qualification(dossier: dict) -> tuple[str, dict]:
    """Gemma motivates, the code computes. Distance and amount are never generated."""
    dep = field_value(dossier, "aeroport_depart")
    arr = field_value(dossier, "aeroport_arrivee")

    try:
        distance = tools.compute_distance(dep, arr)
        intra_eu = tools.is_intra_eu(dep, arr)
        in_scope, scope_reason = tools.check_scope(
            dep, arr, tools.is_eu_carrier(field_value(dossier, "compagnie"))
        )
    except tools.UnknownAirport as err:
        # An IATA code absent from the local table must not crash the agent: ask
        # the user, exactly as for any other unusable field.
        return _ask_for_airport(dossier, dep, arr, err)

    delay_fact = get_fact(dossier, "retard_arrivee_h") or {}
    type_fact = get_fact(dossier, "type_perturbation") or {}
    disruption = dossier["declared_disruption"]

    assessment = tools.compute_compensation(
        distance_km=distance,
        type_perturbation=type_fact.get("value") or "retard",
        retard_arrivee_h=delay_fact.get("value") or 0.0,
        reachemine=disruption.get("reachemine", False),
        retard_reacheminement_h=disruption.get("retard_reacheminement_h"),
        intra_eu=intra_eu,
        in_scope=in_scope,
        out_of_scope_reason=None if in_scope else scope_reason,
    )
    assessment["distance_km"] = distance
    assessment["scope"] = scope_reason
    assessment["rationale"] = tools.motivate_qualification(dossier, assessment)
    dossier["assessment"] = assessment

    log_action(
        dossier,
        "QUALIFICATION_EU261",
        f"calcul déterministe ({dep}-{arr}, {distance:.0f} km, "
        f"{'intra-UE' if intra_eu else 'hors intra-UE'})",
        f"champ d'application : {scope_reason} | eligible={assessment['eligible']} "
        f"montant={assessment['montant']} EUR [{assessment['regle_appliquee']}]",
    )

    if not assessment["eligible"]:
        return "EXPLICATION_REFUS", dossier
    if dossier["degraded_mode"] or lowest_confidence(dossier) in ("basse", "nulle"):
        return "REDACTION_CONDITIONNELLE", dossier
    return "REDACTION", dossier


def _ask_for_airport(dossier: dict, dep: str, arr: str, err: Exception) -> tuple[str, dict]:
    """Route an unknown IATA code to ASK_USER instead of crashing.

    Reuses the pending-question mechanism, so MAX_QUESTIONS_PER_FIELD still
    bounds the loop and the agent eventually exits via EXPLICATION_REFUS.
    """
    field = "aeroport_depart" if not tools.airport_is_known(dep) else "aeroport_arrivee"
    unknown_code = dep if field == "aeroport_depart" else arr
    # Drop the unusable value: otherwise VALIDATION_CHAMPS sends us straight back
    # here with the same code.
    dossier["extraction"][field] = {"valeur": None, "confiance": "nulle", "source": "extraction"}
    dossier["pending_question"] = {
        "field": field,
        "target": "extraction",
        "question": (
            f"Le code IATA « {unknown_code} » ne figure pas dans ma table de référence. "
            f"Pouvez-vous me confirmer {FIELD_LABELS[field]} ?"
        ),
        "reason": (
            "sans un code d'aéroport connu je ne peux ni calculer la distance ni "
            "déterminer si le règlement s'applique, et je ne vais pas deviner"
        ),
    }
    log_action(
        dossier,
        "QUALIFICATION_EU261",
        "résolution des aéroports",
        f"aéroport inconnu ({err}), demande de confirmation à l'utilisateur",
    )
    return "ASK_USER", dossier


def state_refusal_explanation(dossier: dict) -> tuple[str, dict]:
    """Explain why the case gives no right to compensation. NO letter.

    Critical state for the demo: this is what tells the agent apart from a
    template generator.
    """
    dossier["refusal_explanation"] = tools.explain_refusal(dossier)
    log_action(
        dossier,
        "EXPLICATION_REFUS",
        "rédaction de l'explication de refus",
        "aucune lettre générée",
    )
    return "FIN", dossier


def state_drafting(dossier: dict) -> tuple[str, dict]:
    return _draft(dossier, conditional=False)


def state_conditional_drafting(dossier: dict) -> tuple[str, dict]:
    """Letter in the conditional: asks for confirmation instead of asserting."""
    return _draft(dossier, conditional=True)


def _draft(dossier: dict, conditional: bool) -> tuple[str, dict]:
    state = "REDACTION_CONDITIONNELLE" if conditional else "REDACTION"
    dossier["drafting_state"] = state
    defects = dossier.get("defects_to_fix") or []
    dossier["letter"] = tools.draft_letter(dossier, conditional=conditional, defects=defects)
    dossier["defects_to_fix"] = []
    log_action(
        dossier,
        state,
        "rédaction de la lettre" + (" (au conditionnel)" if conditional else ""),
        f"{len(dossier['letter'])} caractères"
        + (f", {len(defects)} défaut(s) corrigé(s)" if defects else ""),
    )
    return "AUTO_VERIFICATION", dossier


def state_self_review(dossier: dict) -> tuple[str, dict]:
    """Second Gemma call, critically reviewing its own letter."""
    dossier["counters"]["self_review"] += 1
    loop = dossier["counters"]["self_review"]
    verdict = tools.review_letter(dossier, dossier["letter"])

    log_action(
        dossier,
        "AUTO_VERIFICATION",
        f"relecture critique (boucle {loop})",
        f"conforme={verdict['compliant']} défauts={verdict['defects']}",
    )

    if not verdict["compliant"] and loop < MAX_DRAFTING_LOOPS:
        dossier["defects_to_fix"] = verdict["defects"]
        return dossier["drafting_state"], dossier

    if not verdict["compliant"]:
        # We exit anyway, but the dossier keeps a trace of the residual defects.
        dossier["residual_defects"] = verdict["defects"]
        log_action(
            dossier,
            "AUTO_VERIFICATION",
            "sortie forcée",
            f"{MAX_DRAFTING_LOOPS} boucles atteintes, défauts résiduels conservés",
        )
    return "GENERATION_PDF", dossier


def state_pdf_generation(dossier: dict) -> tuple[str, dict]:
    """Render the letter as a PDF. The JSON journal is written by the graph."""
    path = tools.render_pdf(dossier, dossier["letter"], "out/reclamation.pdf")
    dossier["pdf"] = path
    log_action(dossier, "GENERATION_PDF", "rendu PDF", path)
    return "FIN", dossier


# State table: this is the graph, readable at a glance.
STATES = {
    "INIT": state_init,
    "EXTRACTION": state_extraction,
    "VALIDATION_CHAMPS": state_field_validation,
    "ASK_USER": state_ask_user,
    "RECHERCHE_VOL": state_flight_search,
    "MODE_DEGRADE": state_degraded_mode,
    "CONSOLIDATION_PREUVES": state_evidence_consolidation,
    "QUALIFICATION_EU261": state_eu261_qualification,
    "EXPLICATION_REFUS": state_refusal_explanation,
    "REDACTION": state_drafting,
    "REDACTION_CONDITIONNELLE": state_conditional_drafting,
    "AUTO_VERIFICATION": state_self_review,
    "GENERATION_PDF": state_pdf_generation,
}
