#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PROJECT_DIR}/.venv/bin/python"
DEMO_PORT="${DEMO_PORT:-7865}"
DEMO_URL="http://127.0.0.1:${DEMO_PORT}"

cd "${PROJECT_DIR}"

if [[ ! -x "${PYTHON_BIN}" ]]; then
  echo "Erreur : environnement .venv introuvable."
  exit 1
fi

if ! curl -fsS http://127.0.0.1:11434/api/tags \
  | "${PYTHON_BIN}" -c \
    'import json,sys; d=json.load(sys.stdin); raise SystemExit(not any("gemma4:12b" in m.get("name","") for m in d.get("models",[])))'
then
  echo "Erreur : lance Ollama avec le modèle gemma4:12b."
  exit 1
fi

echo "Préchargement de Gemma 4…"
curl -fsS http://127.0.0.1:11434/api/generate \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4:12b","prompt":"","stream":false,"keep_alive":"10m"}' \
  >/dev/null

if curl -fsS "${DEMO_URL}" | rg -q "Droit de Retard"; then
  echo "Démo déjà disponible sur ${DEMO_URL}"
  if [[ "${DEMO_NO_OPEN:-0}" != "1" ]]; then
    open "${DEMO_URL}"
  fi
  exit 0
fi

if [[ "${DEMO_NO_OPEN:-0}" != "1" ]]; then
  (sleep 1; open "${DEMO_URL}") &
fi

echo "Démarrage de la démo sur ${DEMO_URL}"
exec "${PYTHON_BIN}" app.py --port "${DEMO_PORT}"
