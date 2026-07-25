"""CLI entry point of the EU261 Claim Agent.

    python main.py --scenario not_eligible            # replay a demo scenario
    python main.py --live --ticket billet.pdf --situation "retard de 4h a l'arrivee"

Two modes, and the distinction matters more than it looks:

  - WITHOUT --live, every model and network call is stubbed and driven by
    --scenario. The graph, the EU261 decision table and the journal are the real
    thing; only the outside world is replayed. This is the demo, and it runs on a
    laptop with the wifi off.
  - WITH --live, the same graph runs against the real gemma4:12b through Ollama
    and the real SerpAPI. --scenario is ignored; --ticket and --situation drive
    the run.

A live run starts with a preflight, printed before anything slow happens, so a
demo failure is diagnosable at a glance instead of after three minutes of
waiting on a model that was never there.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

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
                        help="jeu de données bouchonnées (ignoré avec --live)")
    parser.add_argument("--live", action="store_true",
                        help="appelle réellement Gemma (Ollama) et SerpAPI au lieu des bouchons")
    parser.add_argument("--quiet", action="store_true", help="masque la trace des transitions")
    parser.add_argument("--journal", default=None,
                        help="chemin du journal JSON (défaut : out/dossier_<scenario>.json)")
    args = parser.parse_args()

    return run_live(args) if args.live else run_stub(args)


# --------------------------------------------------------------------------
# Stubbed run: the replayable demo
# --------------------------------------------------------------------------


def run_stub(args: argparse.Namespace) -> int:
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


# --------------------------------------------------------------------------
# Live run: real Gemma, real SerpAPI
# --------------------------------------------------------------------------


def run_live(args: argparse.Namespace) -> int:
    # Each live call takes minutes. Block-buffered output would hold the whole
    # trace back until the run ends, which is exactly when it stops being useful
    # -- both for a recorded demo and for telling "slow" apart from "hung".
    sys.stdout.reconfigure(line_buffering=True)

    print("=" * 72)
    print("EU261 CLAIM AGENT — mode LIVE (Gemma local + SerpAPI)")
    print("=" * 72)

    if not preflight(args):
        return 2

    print(f"Billet     : {args.ticket}")
    print(f"Déclaratif : {args.situation}")

    tools.set_mode(True)
    dossier = instruct(args.ticket, args.situation, verbose=not args.quiet)

    print_verdict(dossier)

    fallbacks = tools.live_fallbacks()
    if fallbacks:
        # Never silent: a run where half the reasoning came from the fallback
        # path is a different run, and the jury gets to see which half.
        print("\n--- REPLIS DÉTERMINISTES (appel modèle en échec) ---")
        for item in fallbacks:
            print(f"  {item['call']:<24} {item['error']}")
    else:
        print("\nAucun repli : tous les appels au modèle ont abouti.")

    path = write_journal(dossier, args.journal or "out/dossier_live.json")
    print(f"\nJournal complet du dossier : {path} "
          f"({dossier['total_transitions']} transitions)")
    return 0


def preflight(args: argparse.Namespace) -> bool:
    """Check, and print, everything a live run depends on. False = do not start.

    Ollama being down is a hard stop rather than a slow crash: the vision call
    would sit on its timeout first. A missing SerpAPI key is NOT a stop -- the
    agent is built to degrade when its external source fails, and that path is
    the one the track grades.
    """
    from agent import config, gemma

    ok = True

    ticket = Path(args.ticket)
    print(f"Billet     : {ticket} — {'présent' if ticket.is_file() else 'INTROUVABLE'}")
    if not ticket.is_file():
        ok = False

    if not args.situation:
        print("Déclaratif : ABSENT — --situation est obligatoire en mode live")
        ok = False

    available = gemma.is_available()
    print(f"Ollama     : {config.ollama_host()} — modèle {config.gemma_model()} : "
          f"{'disponible' if available else 'INJOIGNABLE'}")
    if not available:
        ok = False

    try:
        from agent import flight_search

        configured = flight_search.is_configured()
    except ImportError as err:
        configured = False
        print(f"SerpAPI    : module indisponible ({err})")
    else:
        print(f"SerpAPI    : clé {config.redacted(config.serpapi_key())} — "
              f"{'configurée' if configured else 'ABSENTE'}")
    if not configured:
        print("             -> la recherche de vol échouera et l'agent basculera en "
              "MODE_DEGRADE. C'est un chemin prévu, pas une panne.")

    if not ok:
        print("\nRun live impossible en l'état. Corrigez les points ci-dessus, ou "
              "rejouez la démo hors ligne :\n  uv run main.py --scenario nominal")
    return ok


if __name__ == "__main__":
    raise SystemExit(main())
