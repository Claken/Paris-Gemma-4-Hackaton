"""Ollama wrapper for the local `gemma4:12b` model.

Everything the agent asks of a model goes through this module: one turn in, one
string (or one dict) out. No state calls Ollama directly, and no caller has to
know about base64, `/api/chat` payloads or markdown fences.

Three things make this file worth more than the twenty lines of `requests` it
wraps:

1. **A cheap health probe.** `is_available()` hits `/api/tags` with a short
   timeout. A 12B model on CPU takes a minute or two per generation, so the
   agent must be able to find out that Ollama is down *before* committing to
   that wait, and degrade instead of blocking the demo.
2. **Failures are typed.** Every transport-level problem — host unreachable,
   timeout, non-200, model not pulled — surfaces as `GemmaUnavailable`. A model
   that answered but whose JSON is unusable surfaces as `GemmaJSONError`. Those
   are two different transitions in the graph, so they must be two different
   exceptions.
3. **Retry on malformed JSON.** `chat_json` re-prompts the model with the
   parser's own error message appended. A small local model does emit a stray
   sentence before its object or forget a comma; recovering from that is the
   behaviour the track grades, not an implementation detail.

Dependencies: stdlib + `requests` + `pymupdf`. Nothing else, on purpose.
"""

from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import requests

from . import config

# The vision setting proven in spike_vision.py against the real ticket PDF, and
# re-verified here: at dpi=200 the model reads 6 of the 7 ticket fields exactly,
# missing only the booking reference.
# NOT TESTED: 150 and 300. Lowering the dpi is the obvious lever if extraction
# latency becomes a demo problem, but the booking reference is already marginal
# at 200, so it must be measured against the real ticket before adopting.
DEFAULT_DPI = 200

# Ollama's default slot is 4096 tokens. One A4 ticket page at dpi=200 plus the
# extraction prompt eats most of that, and the REDACTION call (long system
# prompt + dossier + a full letter out) is the one that would silently truncate.
# Asking for 8192 on every call keeps a single loaded instance: mixing context
# sizes across calls makes Ollama reload the 12B model between them, which costs
# far more than the extra KV cache.
NUM_CTX = 8192

_SAMPLING = {"top_p": 0.95, "top_k": 64, "num_ctx": NUM_CTX}

# Measured on this machine (12B, CPU, num_ctx=8192): text generations land at
# 80-120 s, the vision extraction at ~4 min once the model is resident and
# 15-18 min cold, almost all of it image prompt processing. A single default
# would either strangle the vision call or let a dead text call hang the demo,
# so the two budgets are separate and `chat` picks by payload.
TEXT_TIMEOUT = 180.0
VISION_TIMEOUT = 1200.0

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


# --------------------------------------------------------------------------
# Exceptions
# --------------------------------------------------------------------------


class GemmaError(Exception):
    """Base class for every failure coming out of this module."""


class GemmaUnavailable(GemmaError):
    """The model could not be reached: host down, timeout, HTTP error, no model.

    The agent treats this as an infrastructure failure and degrades; it never
    retries its way out of it inside this module.
    """


class GemmaJSONError(GemmaError):
    """The model replied, but no usable JSON object could be parsed.

    Carries the last raw reply (`.raw`) and the last parser message
    (`.parse_error`) so the caller can log what the model actually said — that
    trace is what makes the retry visible in the demo journal.
    """

    def __init__(self, message: str, *, raw: str = "", parse_error: str = ""):
        super().__init__(message)
        self.raw = raw
        self.parse_error = parse_error


# --------------------------------------------------------------------------
# Health probe
# --------------------------------------------------------------------------


def is_available(timeout: float = 3.0) -> bool:
    """True when Ollama answers and the configured model is pulled.

    Never raises: the whole point is to be callable from a state that must keep
    running when the answer is no.
    """
    try:
        response = requests.get(f"{config.ollama_host()}/api/tags", timeout=timeout)
        if response.status_code != 200:
            return False
        names = [model.get("name", "") for model in response.json().get("models", [])]
    except Exception:
        return False
    return any(_same_model(name, config.gemma_model()) for name in names)


def _same_model(tag: str, wanted: str) -> bool:
    """Compare model tags, treating a bare name as its `:latest` variant."""
    normalise = lambda name: name if ":" in name else f"{name}:latest"  # noqa: E731
    return normalise(tag) == normalise(wanted)


# --------------------------------------------------------------------------
# Image encoding
# --------------------------------------------------------------------------


def encode_images(path: str, dpi: int = DEFAULT_DPI) -> list[str]:
    """Return the document as base64 PNG pages, ready for the Ollama payload.

    A PDF becomes one entry per page (rendered at `dpi`); a plain image file
    becomes a single entry read as-is. Ollama accepts the raw bytes of common
    formats, so a JPEG is not re-encoded — that would cost a Pillow dependency
    to lose quality.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"fichier introuvable : {path}")

    suffix = source.suffix.lower()
    if suffix == ".pdf":
        import fitz  # pymupdf; imported lazily so a text-only run needs no PDF stack

        pages: list[str] = []
        document = fitz.open(source)
        try:
            for page in document:
                pixmap = page.get_pixmap(dpi=dpi)
                pages.append(base64.b64encode(pixmap.tobytes("png")).decode("utf-8"))
        finally:
            document.close()
        if not pages:
            raise GemmaError(f"PDF sans page exploitable : {path}")
        return pages

    if suffix in IMAGE_SUFFIXES:
        return [base64.b64encode(source.read_bytes()).decode("utf-8")]

    raise GemmaError(
        f"format non supporté : {suffix or '(sans extension)'} — "
        f"attendu .pdf ou l'un de {sorted(IMAGE_SUFFIXES)}"
    )


# --------------------------------------------------------------------------
# Chat
# --------------------------------------------------------------------------


def chat(
    system: str,
    user: str,
    *,
    images: list[str] | None = None,
    temperature: float = 1.0,
    timeout: float | None = None,
) -> str:
    """One non-streamed turn. Returns the assistant's message content.

    Every transport problem — connection refused, timeout, non-200, unpullable
    model — is normalised into `GemmaUnavailable`, so a caller only ever has one
    exception to catch for "the model is not there".

    `timeout=None` picks the right budget automatically: a vision call is an
    order of magnitude slower than a text one (measured: ~4 min warm, 15-18 min
    cold, against ~90 s for text), so a single default cannot serve both. Pass an
    explicit float to override.
    """
    user_message: dict = {"role": "user", "content": user}
    if images:
        user_message["images"] = images
    if timeout is None:
        timeout = VISION_TIMEOUT if images else TEXT_TIMEOUT

    payload = {
        "model": config.gemma_model(),
        "messages": [{"role": "system", "content": system}, user_message],
        "stream": False,
        "options": {"temperature": temperature, **_SAMPLING},
    }

    try:
        response = requests.post(
            f"{config.ollama_host()}/api/chat", json=payload, timeout=timeout
        )
    except requests.exceptions.Timeout as exc:
        raise GemmaUnavailable(
            f"délai dépassé ({timeout:.0f}s) sur {config.ollama_host()}"
        ) from exc
    except requests.exceptions.RequestException as exc:
        raise GemmaUnavailable(f"Ollama injoignable sur {config.ollama_host()} : {exc}") from exc

    if response.status_code != 200:
        raise GemmaUnavailable(
            f"Ollama a répondu HTTP {response.status_code} : {response.text[:200]}"
        )

    try:
        content = response.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise GemmaUnavailable(f"réponse Ollama inexploitable : {response.text[:200]}") from exc

    return content


def chat_json(
    system: str,
    user: str,
    *,
    images: list[str] | None = None,
    temperature: float = 0.4,
    timeout: float | None = None,
    max_attempts: int = 2,
) -> dict:
    """Same as `chat`, but the reply must be a JSON object.

    `timeout=None` delegates the vision-vs-text budget choice to `chat`.

    On a parse failure the model is asked again with its own broken output and
    the parser's error message appended — the cheapest possible self-correction,
    and one that works on small local models. Temperature defaults lower than
    `chat` because structured output is not a place for creativity.

    Raises `GemmaJSONError` after `max_attempts` failed parses, and
    `GemmaUnavailable` if the host goes away mid-retry.
    """
    prompt = user
    raw = ""
    parse_error = ""

    for attempt in range(1, max_attempts + 1):
        raw = chat(
            system, prompt, images=images, temperature=temperature, timeout=timeout
        )
        try:
            return extract_json(raw)
        except ValueError as exc:
            parse_error = str(exc)
            if attempt == max_attempts:
                break
            # Re-prompt: the model sees what it produced and what broke. Images
            # are deliberately resent, otherwise a vision retry answers blind.
            prompt = (
                f"{user}\n\n"
                "--- CORRECTION ---\n"
                "Ta réponse précédente n'était pas un objet JSON valide.\n"
                f"Erreur de l'analyseur : {parse_error}\n"
                f"Réponse précédente :\n{raw[:1500]}\n\n"
                "Renvoie UNIQUEMENT l'objet JSON corrigé, sans texte avant ni après, "
                "sans bloc de code markdown."
            )

    raise GemmaJSONError(
        f"JSON inexploitable après {max_attempts} tentative(s) : {parse_error}",
        raw=raw,
        parse_error=parse_error,
    )


# --------------------------------------------------------------------------
# JSON salvage
# --------------------------------------------------------------------------

_FENCE = re.compile(r"```(?:json|JSON)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model reply.

    Handles the three things a chatty model does to structured output: wrap it
    in a ```json fence, introduce it with a sentence, and comment on it
    afterwards. Raises `ValueError` when nothing parses — `chat_json` turns that
    into the retry prompt.
    """
    if not text or not text.strip():
        raise ValueError("réponse vide")

    candidates: list[str] = []
    fenced = _FENCE.search(text)
    if fenced:
        candidates.append(fenced.group(1))
    candidates.append(text)

    reason = "aucun objet JSON trouvé dans la réponse"
    for candidate in candidates:
        stripped = candidate.strip()
        for snippet in (stripped, _first_object(stripped)):
            if not snippet:
                continue
            try:
                parsed = json.loads(snippet)
            except json.JSONDecodeError as exc:
                reason = str(exc)
                continue
            if isinstance(parsed, dict):
                return parsed
            reason = f"JSON valide mais de type {type(parsed).__name__}, objet attendu"

    raise ValueError(reason)


def _first_object(text: str) -> str | None:
    """Slice the first brace-balanced object, ignoring braces inside strings."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]
    return None
