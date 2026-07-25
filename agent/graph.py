"""Orchestration loop and state machine.

No agent framework: the loop is hand-written, fits on one page, and the whole
graph can be read in this single file.

    INIT
     |
     v
    EXTRACTION <--------+ (invalid JSON, max 2 attempts)
     |  |               |
     |  +---------------+
     |  \--(definitive failure)--> ASK_USER
     v
    VALIDATION_CHAMPS <-----------------+
     |  \--(field missing / unreliable)--> ASK_USER
     v                                   |
    RECHERCHE_VOL <---+ (network down, max 2 retries)
     |  |             |
     |  +-------------+
     |  \--(definitive failure)--> MODE_DEGRADE --+
     v                                            |
    CONSOLIDATION_PREUVES                         |
     |  \--(contradiction)--> ASK_USER -----------+
     v                                            |
    QUALIFICATION_EU261 <-------------------------+
     |  \--(unknown IATA code)--> ASK_USER
     |  \--(not eligible)--> EXPLICATION_REFUS --> FIN   [no letter]
     |  \--(eligible, weak evidence)--> REDACTION_CONDITIONNELLE --+
     v                                                             |
    REDACTION <------------------------------------------------+   |
     |                                                         |   |
     v                                                         |   |
    AUTO_VERIFICATION --(non-compliant, max 2 loops)-----------+<--+
     |
     v
    GENERATION_PDF --> FIN

Invariants:
  - every tool call that can fail has a defined failure transition;
  - no loop is unbounded (bounded counters + the MAX_TRANSITIONS guard);
  - the dossier is journalled after every transition.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agent.dossier import new_dossier
from agent.states import STATES

INITIAL_STATE = "INIT"
FINAL_STATE = "FIN"
MAX_TRANSITIONS = 40  # guard: beyond this the graph is looping and we want to know


def run(dossier: dict, verbose: bool = True) -> dict:
    """Run the graph until FIN and return the instructed dossier."""
    state = INITIAL_STATE
    transitions = 0

    while state != FINAL_STATE:
        if transitions >= MAX_TRANSITIONS:
            raise RuntimeError(
                f"guard: {MAX_TRANSITIONS} transitions reached, probable loop "
                f"(current state: {state})"
            )
        handler = STATES[state]
        journal_cursor = len(dossier["history"])

        if verbose:
            print(f"\n[{transitions + 1:02d}] {state}")

        next_state, dossier = handler(dossier)

        if verbose:
            for entry in dossier["history"][journal_cursor:]:
                print(f"     · {entry['action']}")
                print(f"       -> {entry['outcome']}")
            arrow = "==>" if next_state == state else "-->"
            print(f"     {arrow} {next_state}")

        dossier["history"].append(
            {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "transition": f"{state} -> {next_state}",
            }
        )
        state = next_state
        transitions += 1

    dossier["total_transitions"] = transitions
    return dossier


def instruct(ticket_path: str, declaration: str, verbose: bool = True) -> dict:
    """Entry point: create a blank dossier and walk it through the graph."""
    return run(new_dossier(ticket_path, declaration), verbose=verbose)


def write_journal(dossier: dict, path: str | Path) -> Path:
    """Serialize the full dossier next to the letter. This is the jury's trace."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dossier, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def print_verdict(dossier: dict) -> None:
    """Print the case conclusion, in French."""
    assessment: dict[str, Any] = dossier.get("assessment") or {}
    print("\n" + "=" * 72)

    if not assessment.get("eligible"):
        print("VERDICT : dossier NON ÉLIGIBLE — aucune lettre générée")
        print("=" * 72)
        print("\n" + dossier.get("refusal_explanation", ""))
    else:
        header = f"VERDICT : ÉLIGIBLE — {assessment['montant']} €"
        if dossier["degraded_mode"]:
            header += "  [mode dégradé : preuves non vérifiées]"
        print(header)
        print("=" * 72)
        print(f"\nRègle appliquée : {assessment['regle_appliquee']}")
        print(f"Distance        : {assessment['distance_km']:.0f} km (calcul déterministe)")
        if assessment.get("scope"):
            print(f"Champ d'applic. : {assessment['scope']}")
        print(f"Motivation      : {assessment['rationale']}")

        # An imperfect letter is never delivered silently.
        residual = dossier.get("residual_defects")
        if residual:
            print("\n/!\\ ATTENTION — l'auto-vérification n'a pas pu corriger :")
            for defect in dict.fromkeys(residual):
                print(f"      - {defect}")
            print("    Relisez et complétez ces éléments avant tout envoi.")

        print("\n--- LETTRE ---")
        print(dossier["letter"])

    if dossier["conflicts"]:
        print("\n--- CONFLITS DE PREUVES ---")
        for conflict in dossier["conflicts"]:
            status = (
                f"arbitré par l'utilisateur -> {conflict['retained_value']}"
                if conflict.get("arbitrated")
                else "NON RÉSOLU"
            )
            print(
                f"  {conflict['fact']} : utilisateur={conflict['user_version']} "
                f"web={conflict['web_version']} ({status})"
            )

    print("\n--- FAITS RETENUS (source / confiance) ---")
    for entry in dossier["verified_facts"]:
        print(
            f"  {entry['fact']:<20} {str(entry['value']):<10} "
            f"{entry['source']:<22} {entry['confidence']}"
        )
