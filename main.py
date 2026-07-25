"""CLI entry point of the EU261 Claim Agent.

    python main.py --ticket billet.png --situation "retard de 4h a l'arrivee"
    python main.py --scenario not_eligible     # replay a demo scenario

STEP 1: the model/API tools are stubbed and --scenario drives the fake data.
The graph itself is the real thing, and so is the EU261 decision table.
"""

from __future__ import annotations

import argparse

from agent import tools
from agent.graph import instruct, print_verdict, write_journal


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Instruit un dossier d'indemnisation EU261 à partir d'un billet."
    )
    parser.add_argument("--ticket", default="billet_avion_fictif.pdf",
                        help="chemin de la photo ou du PDF du billet")
    parser.add_argument("--situation", default=None,
                        help="description libre de la perturbation subie")
    parser.add_argument("--scenario", default="nominal", choices=sorted(tools.SCENARIOS),
                        help="jeu de données bouchonnées (étape 1)")
    parser.add_argument("--quiet", action="store_true", help="masque la trace des transitions")
    parser.add_argument("--journal", default=None,
                        help="chemin du journal JSON (défaut : out/dossier_<scenario>.json)")
    args = parser.parse_args()

    scenario = tools.use_scenario(args.scenario)
    declaration = args.situation or scenario["declaration"]

    print("=" * 72)
    print(f"EU261 CLAIM AGENT — scénario « {args.scenario} »")
    print(f"  {scenario['label']}")
    print("=" * 72)
    print(f"Billet     : {args.ticket}")
    print(f"Déclaratif : {declaration}")

    dossier = instruct(args.ticket, declaration, verbose=not args.quiet)

    print_verdict(dossier)

    path = write_journal(dossier, args.journal or f"out/dossier_{args.scenario}.json")
    print(f"\nJournal complet du dossier : {path} "
          f"({dossier['total_transitions']} transitions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
