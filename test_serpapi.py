"""Test 2 — Agent complet : recherche web SerpApi + raisonnement Gemma 4 local.

Prérequis : export SERPAPI_KEY=<ta_clé>  (https://serpapi.com/users/sign_up)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request

from test_local import ask_gemma

QUESTION = "Quelles sont les dernières actualités sur le modèle Gemma de Google ?"
SERPAPI_URL = "https://serpapi.com/search.json"


def web_search(query: str, num: int = 5) -> list[dict]:
    api_key = os.getenv("SERPAPI_KEY")
    if not api_key:
        raise SystemExit("SERPAPI_KEY absente — export SERPAPI_KEY=<ta_clé> puis relance.")

    params = {
        "engine": "google",
        "q": query,
        "num": num,
        "api_key": api_key,
    }
    url = f"{SERPAPI_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=15) as response:
        results = json.load(response)
    return [
        {"title": r.get("title", ""), "link": r.get("link", ""), "snippet": r.get("snippet", "")}
        for r in results.get("organic_results", [])[:num]
    ]


if __name__ == "__main__":
    if not os.getenv("SERPAPI_KEY"):
        sys.exit("SERPAPI_KEY absente — export SERPAPI_KEY=<ta_clé> puis relance.")

    print(f"Question : {QUESTION}\n")

    print("1) Recherche SerpApi…")
    sources = web_search("Google Gemma model news")
    for s in sources:
        print(f"   - {s['title']}")

    print("\n2) Synthèse par Gemma 4…")
    contexte = "\n".join(f"[{i+1}] {s['title']} — {s['snippet']} ({s['link']})"
                         for i, s in enumerate(sources))
    reponse = ask_gemma(
        f"Voici des résultats de recherche web :\n{contexte}\n\n"
        f"Réponds à la question en citant les sources [n] : {QUESTION}",
        system="Tu es un agent de recherche. Réponds en français, de façon factuelle et sourcée.",
    )
    print(f"\n--- Réponse de l'agent ---\n{reponse}")
