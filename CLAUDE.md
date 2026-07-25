# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

**EU261 Claim Agent** — built for the Gemma 4 Hackathon (42 Paris), Track 02 "Autonomous Agents". A local agent that
builds an EU261 air passenger compensation claim from a photo of a flight ticket, under uncertain/incomplete
evidence, and that is explicitly allowed to conclude the user is not entitled to anything.

This is **not** a letter generator. The letter is the trivial output. The value is in (a) legal qualification under
incomplete/contradictory information and (b) how the agent behaves when its sources fail — that is the literal
track question ("Does it survive contact with failure?"). A project that is a linear prompt chain with no branching
or error recovery caps at 2/5 on the track's own rubric.

**`hackathon_spec.json` is the authoritative build spec.** Read it in full before writing code — it defines the
exact state machine, tool signatures, EU261 decision tables, prompt/schema contracts, letter template, build order,
and anti-patterns. The instructions below summarize it; the JSON file is the source of truth and takes precedence
if anything here goes stale.

## Current state of the repo

**Steps 1 and 2 are done and verified. Step 3 is code-complete but not fully verified end-to-end — read
`HANDOVER.md` before touching anything.** Steps 4–6 (PDF, demo, eval+writeup) are not started.

`HANDOVER.md` holds the current status, the verification gaps, the hard-won gotchas (Gemma latency, Ollama
context size, the SerpAPI finding) and the roadmap. It is the first file to read when picking this up.

- `agent/graph.py` — orchestration loop + ASCII diagram of the whole graph in the module docstring.
- `agent/states.py` — one function per state, `STATES` dict at the bottom is the edge table.
- `agent/tools.py` — the 6 tools + the Gemma-reasoning calls. `compute_distance` / `compute_compensation` now
  delegate to `eu261`; the rest are **stubbed**, driven by `SCENARIOS`.
- `agent/eu261.py` — real haversine + decision table. Deterministic, no model, 41 unit tests.
- `agent/dossier.py` — the central dossier, provenance/confidence helpers.
- `data/airports.csv` — 118 IATA airports (EU27 + IS/NO/CH + French overseas; the UK is deliberately outside the
  EU261 country set since 2021).
- `spike_vision.py` — the original working Ollama vision call (proven `dpi=200` + base64 payload). Reuse it as the
  basis for the real `extract_ticket` at step 3; it is not wired into the agent.

Replacing a stub means editing only the body in `tools.py` — signatures are final, and no state calls a model, an
API, or `eu261` directly.

## Commands

```bash
uv sync                                  # install deps into .venv
uv run main.py                           # nominal scenario, full transition trace
uv run main.py --scenario not_eligible   # any key of tools.SCENARIOS
uv run main.py --scenario conflicting_evidence --quiet

uv run tests/test_eu261.py               # EU261 decision table; plain asserts, no pytest
```

Scenarios available: `nominal`, `source_failure`, `not_eligible`, `conflicting_evidence` (the 4 demo cases),
plus `blurry_ticket`, `malformed_json`, `user_gives_up` (injected failures for the eval). Each run writes a full
JSON journal to `out/dossier_<scenario>.json` — that journal is the artifact the jury inspects.

Smoke test — every scenario must reach a verdict without a traceback:

```bash
for s in nominal source_failure not_eligible conflicting_evidence blurry_ticket malformed_json user_gives_up; do
  uv run main.py --scenario "$s" --quiet | grep -m1 VERDICT
done
```

There is no linter or formatter configured, and pytest is deliberately not a dependency — `tests/test_eu261.py`
is a self-contained script so it runs offline during the hackathon.

No test suite, linter, or formatter is configured yet. Requires Python >=3.14 (per `pyproject.toml`; the spec
itself was written against 3.11+ semantics — don't rely on syntax newer than 3.11 without checking `.python-version`).

The target model is `gemma4:12b` served locally via **Ollama** (`http://localhost:11434/api/chat`) — no external
LLM API calls. Ollama must be running locally for anything vision/reasoning-related to work.

## Architecture (per hackathon_spec.json)

### Build order — do not deviate

The spec is explicit that the graph must be built and validated with **stubbed tools** (hardcoded return values)
*before* wiring in real Gemma calls or SerpAPI. Building tools first is called out as the #1 way to lose the
hackathon (you end up debugging search API responses instead of the graded architecture). Order:

1. `graph.py` + `states.py` with all 6 tools stubbed — verify all 4 demo scenarios traverse the graph correctly with fake data.
2. `eu261.py` — haversine distance + compensation decision table, unit-tested against known cases.
3. Wire in real `extract_ticket` (Gemma vision) and `search_flight_status` (SerpAPI).
4. `REDACTION` → `AUTO_VERIFICATION` → `GENERATION_PDF`.
5. Replayable demo scenarios + terminal recording.
6. Eval script + Kaggle writeup + README.

### Guiding principles

- **The LLM decides, the code calculates.** Distance and compensation amount are always deterministic Python
  (haversine + a lookup table), never generated by the model — this is a load-bearing claim in the writeup.
- **The agent must be able to fail cleanly**: refuse, ask, or flag a conflict. An agent that always produces a
  letter is just a template engine.
- **Every fact in the case file carries a source and a confidence level.** Nothing is asserted without provenance.
- **Every tool call can fail, and every failure has a defined transition in the graph.**

### State machine

Explicit states, each a function `(dossier) -> (nouvel_etat, dossier)` in `agent/states.py`, driven by a hand-written
loop in `agent/graph.py` (no LangChain/LangGraph — deliberate, for debuggability and so the graph is legible to
judges in one file open). The central object is the **dossier**: a serializable dict accumulating facts + their
source + confidence, logged after every transition (this transition log is the demo trace).

States: `INIT` → `EXTRACTION` (Gemma vision, retry ≤2 on bad JSON, else → `ASK_USER`) → `VALIDATION_CHAMPS` (checks
required fields present & high/medium confidence) → `RECHERCHE_VOL` (SerpAPI flight status; ≤2 retries with
backoff, then → `MODE_DEGRADE` on definitive failure) → `CONSOLIDATION_PREUVES` (Gemma arbitrates user-reported vs.
web-sourced facts, contradictions → `ASK_USER`, never silently resolved) → `QUALIFICATION_EU261` (Gemma applies the
rules; code computes distance/amount) → either `EXPLICATION_REFUS` (no letter — this state is explicitly called out
as the one not to cut for scope reasons, it's what proves the agent has judgment rather than being a template) or
`REDACTION` / `REDACTION_CONDITIONNELLE` (degraded-evidence variant, conditional tense, asks carrier to confirm
facts rather than asserting them) → `AUTO_VERIFICATION` (second Gemma call acting as critical reviewer, checks for
unfilled variables / hallucinated facts / amount-distance inconsistency; loops back to `REDACTION` ≤2 times on
non-conformance) → `GENERATION_PDF` → `FIN`.

### Tools (`agent/tools.py`)

Six tools: `extract_ticket` (Gemma vision → structured JSON with per-field confidence), `search_flight_status`
(SerpAPI — spec explicitly says this source is *structurally* unreliable for past flights; that's the failure mode
the track wants demonstrated, not a bug to fix — cap effort at 30 min), `compute_distance` (deterministic haversine
over a local IATA airport CSV), `compute_compensation` (pure Python decision table from `logique_eu261`),
`ask_user` (CLI `input()`), `render_pdf` (fpdf2).

### EU261 decision logic (`agent/eu261.py`)

Simplified rules for a prototype — the generated PDF must carry a disclaimer that it's a draft to review, not legal
advice. Key points: scope is EU-departure (any carrier) or EU-arrival (EU carrier only); delay must be ≥3h at
*arrival* (not departure — the spec flags this as the classic mistake to check explicitly); cancellation
<14 days' notice; compensation tiers by distance (€250 / €400 / €600) with a 50% reduction if a reroute keeps the
arrival delay under 2h/3h/4h respectively; extraordinary-circumstances exemption (weather, ATC strike — an ordinary
technical fault does not qualify); 5-year statute of limitations in France.

### Bounded loops

Every cycle in the graph is bounded, and the bounds live as constants at the top of `states.py`:
`MAX_TENTATIVES_EXTRACTION`, `MAX_RETRIES_RECHERCHE`, `MAX_BOUCLES_REDACTION`, `MAX_QUESTIONS_PAR_CHAMP`, plus
`MAX_TRANSITIONS` in `graph.py` as a last-resort guard that raises. `MAX_QUESTIONS_PAR_CHAMP` exists because an
agent that re-asks the same question forever has not survived failure — after two unanswered attempts it exits via
`EXPLICATION_REFUS` with `code: "dossier_incomplet"` rather than inventing a value.

Two other invariants worth preserving: `review_letter` keeps a deterministic `{{variable}}` scan even once it
becomes a real Gemma call (an unfilled template variable is the worst defect a letter can carry and needs no
model to spot), and a letter that still has residual defects after the correction loop is **never** delivered
silently — `print_verdict` prints them as a warning.

### Planned file layout

```
main.py                 CLI entrypoint: python main.py --ticket billet.png --situation "..."
agent/graph.py           orchestration loop / state machine
agent/states.py          one function per state
agent/tools.py           the 6 tools
agent/gemma.py           ollama wrapper, robust JSON parsing with retry
agent/eu261.py           deterministic decision table + haversine
agent/prompts.py         centralized system prompts
data/airports.csv        IATA coordinates
templates/lettre.txt     letter template (full text is in hackathon_spec.json under template_lettre)
demo/                    the 4 replayable scenarios + run_demo.sh
eval/                    10 labeled scenarios + measurement script
```

The spec's stated goal is that the graph must be understandable by opening a single file — that's what judges look
at first.

### Language convention

**All identifiers, comments and docstrings are English.** Three families of strings stay French, and only
these — do not "fix" them:

1. **Spec-imposed data contracts.** The 13 state ids (`VALIDATION_CHAMPS`, `RECHERCHE_VOL`, …), the ticket
   field names inside `extraction` (`numero_vol`, `date_vol`, `aeroport_depart`, …) with their inner keys
   `valeur`/`confiance`, the confidence scale values (`haute`/`moyenne`/`basse`/`nulle`), and the keys returned
   by `compute_compensation` (`eligible`, `montant`, `reduction_50`, `regle_appliquee`, `motif_refus`). The
   ticket field names map one-to-one onto the letter template placeholders, so renaming them breaks the letter.
2. **Anything shown to the user** — questions, refusal explanations, letter body, verdict labels — properly
   accented French.
3. **`data/airports.csv` headers** (`iata,nom,ville,pays,latitude,longitude`), shared data rather than code.

The dossier's own keys (`verified_facts`, `declared_disruption`, `pending_question`, …) and fact records
(`{fact, value, source, confidence}`) are English: they are our design, not the spec's.

### Anti-patterns (explicitly called out in the spec — avoid)

- Building tools before the graph.
- Letting the LLM compute distance or a compensation amount.
- Cutting the `EXPLICATION_REFUS` state to save time.
- Happy-path-only design that assumes SerpAPI will respond during the live demo.
- Expanding scope (multi-language, web UI, baggage handling) — hard freeze at T-45min remaining.
