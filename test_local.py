"""Test 1 — Gemma 4 local seul, sans SerpApi."""
from __future__ import annotations

import json
import time
import urllib.request

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "gemma4:12b"


def ask_gemma(prompt: str, system: str | None = None) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = json.dumps({
        "model": MODEL,
        "messages": messages,
        "stream": False,
    }).encode("utf-8")
    request = urllib.request.Request(
        OLLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)["message"]["content"]


if __name__ == "__main__":
    t0 = time.time()
    reponse = ask_gemma(
        "Donne-moi 3 idées d'agents IA originaux pour un hackathon, en une ligne chacune.",
        system="Tu es un assistant concis. Réponds en français.",
    )
    print(f"--- Réponse de {MODEL} ({time.time() - t0:.1f}s) ---")
    print(reponse)
