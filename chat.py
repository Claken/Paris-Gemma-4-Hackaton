"""Chat interactif avec Gemma 4 local (Ollama).

Lancer :  .venv/bin/python chat.py
Quitter : Ctrl+C, ou taper "exit"
Reset :   taper "reset" pour vider l'historique
"""
from __future__ import annotations

import json
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:12b"
SYSTEM = "Tu es un assistant utile et concis. Réponds en français."


def chat_stream(messages: list[dict]) -> str:
    """Envoie l'historique à Gemma et affiche la réponse token par token."""
    reponse = ""
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "stream": True,
    }).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=300) as response:
        for ligne in response:
            if not ligne.strip():
                continue
            morceau = json.loads(ligne)["message"]["content"]
            print(morceau, end="", flush=True)
            reponse += morceau
    print()
    return reponse


def main():
    historique = [{"role": "system", "content": SYSTEM}]
    print(f"💬 Chat avec {MODEL} — 'exit' pour quitter, 'reset' pour repartir à zéro\n")
    while True:
        try:
            question = input("toi> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nbye !")
            break
        if not question:
            continue
        if question.lower() == "exit":
            print("bye !")
            break
        if question.lower() == "reset":
            historique = [{"role": "system", "content": SYSTEM}]
            print("(historique vidé)\n")
            continue

        historique.append({"role": "user", "content": question})
        print(f"\n{MODEL}> ", end="", flush=True)
        reponse = chat_stream(historique)
        historique.append({"role": "assistant", "content": reponse})
        print()


if __name__ == "__main__":
    main()
