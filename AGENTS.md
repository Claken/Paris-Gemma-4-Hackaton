# Repository Guidelines

## Project Structure & Module Organization

This repository contains a local-first EU261 claim-preparation prototype.

- `agent.py`: Gemma 4 vision/audio extraction, routing, research, and letter
  pipeline.
- `eu261.py`: deterministic distance, compensation, and ticket-refund rules.
- `tools.py`: privacy-minimized SerpApi searches and offline recovery.
- `app.py` and `static/index.html`: local demo and optional microphone dictation.
- `test_agent.py`: deterministic unit tests.
- `billet_avion_fictif.pdf`: fictional demo input.
- `knowledge/airline_policies/`: optional versioned airline-procedure corpus.
- `PLAN.md`, `RAPPORT_AVANCEMENT.md`, and `DECOUPAGE_AGENTS.md`: status,
  priorities, ownership, and parallel work packages.

Keep legal calculations in `eu261.py`; Gemma must extract or draft, never
invent eligibility rules. Do not commit `.env`, `.venv/`, `__pycache__/`, or
temporary rendered documents.

## Build, Test, and Development Commands

There is no build step and runtime Python uses the standard library. PDF
rendering needs Poppler; optional browser dictation needs FFmpeg.

```bash
ollama serve
ollama pull gemma4:12b
.venv/bin/python -m unittest -v test_agent.py
./demo.sh
.venv/bin/python agent.py billet_avion_fictif.pdf \
  --incident "Le vol est arrivé avec 3 h 25 de retard."
```

The interface is available at `http://127.0.0.1:7865`. Online research
requires `SERPAPI_KEY` in the launching process. Never print or commit it.

## Coding Style & Testing

Target Python 3.10+, PEP 8, four-space indentation, `snake_case` names, type
annotations for public helpers, and explicit network timeouts. Preserve French
user-facing text. Add deterministic coverage to `test_agent.py`; run all tests
after changes to routing, rules, parsing, or research. Ollama integration tests
must be sequential because concurrent runs distort latency. Tool calls must use
an explicit allow-list and validated arguments; retain a deterministic fallback.
Audio must remain local, must never be persisted, and its transcription must be
confirmed before it affects routing.

## Agent Coordination & Review

Read `PLAN.md` and `DECOUPAGE_AGENTS.md` before editing. Work only inside the
assigned file set; the main agent owns core P0 files until the demo is frozen.
External agents must not change `PLAN.md` or this guide. Contributions should
state files changed, commands run, observed results, assumptions, and remaining
risks. Use short imperative commit subjects, for example
`docs: add Kaggle writeup`.

Pull requests must describe user-visible behavior, tests performed,
configuration needs, and any SerpApi quota impact. Do not claim guaranteed
compensation or legal representation.
