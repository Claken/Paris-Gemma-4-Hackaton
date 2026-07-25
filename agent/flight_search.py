"""SerpAPI client: real status of a past flight.

Read this before judging the hit rate of this module.

The spec is explicit (tools[1].avertissement): a web search is *structurally*
unreliable for a flight that has already landed. Flight trackers paywall or
purge their history, Google surfaces the schedule rather than the actual
arrival, and most queries come back with "here is the AF1234 route" instead of
"AF1234 arrived 3h12 late on 12 March". That is the failure mode the track asks
us to survive, not a defect to grind down.

So this module optimises for honesty, not for coverage:

  * it establishes a delay only when a snippet states one unambiguously;
  * two snippets that disagree produce `found: False`, never an average;
  * a duration with no delay keyword next to it is a flight time, not a delay,
    and is ignored;
  * when nothing usable comes back it raises, because `SearchUnavailable` and
    `NoUsableResult` both have a defined transition in the graph (-> retry,
    then MODE_DEGRADE). A fabricated `retard_arrivee_h: 0.0` would silently
    turn into "no compensation due" in a legal letter. Raising is the correct,
    expected outcome here.

`snippets` is therefore the most valuable part of the return value: it carries
the raw result text through to CONSOLIDATION_PREUVES, where Gemma reasons over
what this parser could not decide by itself.

Naming note: identifiers, comments and docstrings are English; exception
messages are French because they end up in the dossier and in front of the user.
The API key is read through agent.config and never logged -- use
`config.redacted()` if you ever need to show it in a demo.
"""

from __future__ import annotations

import re
from datetime import date as _date
from typing import Any

import requests

from agent import config

__all__ = [
    "SearchError",
    "SearchUnavailable",
    "NoUsableResult",
    "is_configured",
    "search_flight_status",
    "parse_delay_hours",
    "build_query",
]

SERPAPI_ENDPOINT = "https://serpapi.com/search.json"
SERPAPI_ENGINE = "google_light"

#: Maximum sources / snippets carried back to the graph. Enough for Gemma to
#: arbitrate, small enough to keep the dossier JSON readable by the jury.
MAX_RESULTS = 8

#: Above this, a "delay" is almost certainly a parsing accident (a flight time,
#: a price, a duration in an unrelated result).
MAX_PLAUSIBLE_DELAY_H = 48.0


class SearchError(Exception):
    """Base class: the flight status could not be established from the web."""


class SearchUnavailable(SearchError):
    """The call itself failed: no key, network down, timeout, HTTP or quota error.

    Retryable. The graph gives it MAX_RETRIES_RECHERCHE attempts, then degrades.
    """


class NoUsableResult(SearchError):
    """The API answered, but nothing in it establishes the flight status.

    The common case for a past flight. Carries `.sources` and `.snippets` so a
    caller can still hand the raw text to Gemma instead of throwing it away.
    """

    def __init__(
        self,
        message: str,
        *,
        sources: list[dict[str, str]] | None = None,
        snippets: list[str] | None = None,
    ) -> None:
        super().__init__(message)
        self.sources = sources or []
        self.snippets = snippets or []


# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------


def is_configured() -> bool:
    """True when a SerpAPI key is available. Never raises, never logs the key."""
    try:
        return bool(config.serpapi_key().strip())
    except Exception:  # pragma: no cover - config is dependency-free, but never crash here
        return False


# --------------------------------------------------------------------------
# Query building
# --------------------------------------------------------------------------

_MONTHS_EN = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _human_date(date: str) -> str:
    """'2026-03-12' -> '12 March 2026'. Unparseable input is returned as-is."""
    try:
        parsed = _date.fromisoformat(date.strip())
    except (ValueError, AttributeError):
        return str(date)
    return f"{parsed.day} {_MONTHS_EN[parsed.month - 1]} {parsed.year}"


def build_query(flight_number: str, date: str, attempt: int = 1) -> str:
    """Query for `attempt`. Attempt 2+ reformulates, as the spec requires.

    Attempt 1 asks the question directly; if that fails, repeating it verbatim
    only burns quota, so attempt 2 changes both the phrasing and the date format
    (ISO vs human) to hit a different slice of the index.
    """
    number = flight_number.strip().upper()
    if attempt <= 1:
        return f"{number} {date} arrival delay status"
    return (
        f'"{number}" flight {_human_date(date)} '
        f"actual arrival time delayed OR cancelled OR diverted"
    )


# --------------------------------------------------------------------------
# Snippet parsing (pure functions -- the testable part)
# --------------------------------------------------------------------------

# A duration only counts as a delay when a delay word sits next to it. Without
# this guard "flight time 3 hours 20 minutes" reads as a 3h20 delay, which is
# exactly the kind of confidently wrong answer that would poison a claim.
_DELAY_KEYWORD_RE = re.compile(
    r"\b(?:delay(?:ed|s)?|delayed\s+by|late|lateness|behind\s+schedule|"
    r"retard(?:e|é|ee|ée|s)?|en\s+retard|arriv(?:ed|al)\s+late)\b",
    re.IGNORECASE,
)

_DELAY_KEYWORD_WINDOW = 40  # characters between the keyword and the duration

# Observed on the very first real call: flight trackers answer a query about one
# flight with route statistics -- "Average Delay: 10-20 minutes", "Late on
# average 33 minutes". Reading those as *this* flight's delay is precisely the
# confidently-wrong answer that would poison a legal claim, so a statistical
# marker anywhere near the duration disqualifies it.
_STATISTIC_RE = re.compile(
    r"\b(?:average|avg|on\s+average|typical(?:ly)?|usual(?:ly)?|historical(?:ly)?|"
    r"on[-\s]?time\s+(?:rate|performance)|moyenne?|en\s+moyenne|habituellement)\b",
    re.IGNORECASE,
)
_STATISTIC_WINDOW = 60

# "3h 20m", "3 hours 20 minutes", "4 heures 30 minutes", "3h20"
_HOURS_MINUTES_RE = re.compile(
    r"(\d{1,2})\s*(?:h\b|hrs?\b|hours?\b|heures?\b|h(?=\d))"
    r"\s*(?:and|et)?\s*"
    r"(\d{1,2})\s*(?:m\b|mins?\b|minutes?\b)?",
    re.IGNORECASE,
)
# "3 hours", "1.5 hours", "4 heures", "2,5 heures"
_HOURS_RE = re.compile(
    r"(\d{1,2}(?:[.,]\d{1,2})?)\s*(?:h\b|hrs?\b|hours?\b|heures?\b)", re.IGNORECASE
)
# "45 minutes", "90 min"
_MINUTES_RE = re.compile(r"(\d{1,3})\s*(?:m\b|mins?\b|minutes?\b)", re.IGNORECASE)

_CANCELLED_RE = re.compile(r"\b(?:cancell?ed|cancellation|annul(?:e|é)(?:e|é)?s?)\b", re.IGNORECASE)


def _to_float(raw: str) -> float:
    return float(raw.replace(",", "."))


def parse_delay_hours(text: str) -> float | None:
    """Best-effort arrival delay in hours from one snippet. None when unsure.

    Handles "delayed by 3h 20m", "3 hours 20 minutes late", "retard de 4 heures",
    "arrived 45 minutes late".

    Returns None -- deliberately -- when:
      * no delay keyword is present (a bare duration is a flight time, not a delay);
      * the duration is a statistic ("average delay 20 minutes") or a range
        ("10-20 minutes"), which describes the route, not this flight;
      * the snippet yields two different durations (ambiguous, let Gemma or the
        user arbitrate);
      * the value is <= 0 or implausibly large.

    A None routes the agent to ask or to degrade. A wrong float silently
    corrupts a legal claim, so every doubt resolves to None.
    """
    if not text:
        return None

    keyword_spans = [m.span() for m in _DELAY_KEYWORD_RE.finditer(text)]
    if not keyword_spans:
        return None

    statistic_spans = [m.span() for m in _STATISTIC_RE.finditer(text)]

    consumed: list[tuple[int, int]] = []
    values: list[float] = []

    def _within(span: tuple[int, int], other: tuple[int, int], window: int) -> bool:
        return other[0] - window <= span[1] and span[0] <= other[1] + window

    def _near_keyword(span: tuple[int, int]) -> bool:
        return any(_within(span, k, _DELAY_KEYWORD_WINDOW) for k in keyword_spans)

    def _is_statistic(span: tuple[int, int]) -> bool:
        if any(_within(span, s, _STATISTIC_WINDOW) for s in statistic_spans):
            return True
        # "10-20 minutes" / "1 to 2 hours": a range is not a measurement.
        prefix = text[max(0, span[0] - 6) : span[0]]
        return re.search(r"(?:\d\s*[-–—]\s*|\bto\s+)$", prefix) is not None

    def _overlaps(span: tuple[int, int]) -> bool:
        return any(span[0] < end and start < span[1] for start, end in consumed)

    # Most specific pattern first; each match masks its span so the coarser
    # patterns cannot re-read "3 hours" out of "3 hours 20 minutes".
    for pattern, to_hours in (
        (_HOURS_MINUTES_RE, lambda m: _to_float(m.group(1)) + int(m.group(2)) / 60.0),
        (_HOURS_RE, lambda m: _to_float(m.group(1))),
        (_MINUTES_RE, lambda m: int(m.group(1)) / 60.0),
    ):
        for match in pattern.finditer(text):
            span = match.span()
            if _overlaps(span) or not _near_keyword(span) or _is_statistic(span):
                continue
            consumed.append(span)
            values.append(round(to_hours(match), 2))

    distinct = {v for v in values if 0 < v <= MAX_PLAUSIBLE_DELAY_H}
    if len(distinct) != 1:
        # 0 -> nothing usable; 2+ -> contradictory, which is a declared failure
        # mode, not something to average away.
        return None
    return distinct.pop()


def _mentions_flight(text: str, flight_number: str) -> bool:
    """True when `text` names this flight (AF1234 / AF 1234 / AF-1234 / AF 01234)."""
    match = re.fullmatch(r"\s*([A-Za-z]{1,3})\s*-?\s*(\d{1,4})\s*", flight_number or "")
    if not match:
        return bool(flight_number) and flight_number.strip().lower() in text.lower()
    carrier, number = match.group(1), match.group(2).lstrip("0") or "0"
    pattern = rf"\b{re.escape(carrier)}\s*-?\s*0*{re.escape(number)}\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _mentions_date(text: str, date: str) -> bool:
    """True when `text` carries the flight date, in any common rendering.

    Load-bearing guard. A tracker page for "AF1234" describes the route in
    general; only a snippet that also pins the date can be evidence about the
    flight the passenger actually took. Without this check the client happily
    reports the route's average delay as the claim's delay.
    """
    try:
        parsed = _date.fromisoformat((date or "").strip())
    except (ValueError, AttributeError):
        return False
    day, month, year = parsed.day, parsed.month, parsed.year
    month_en = _MONTHS_EN[month - 1]
    forms = [
        parsed.isoformat(),
        rf"\b0?{day}\s+{month_en}\b",
        rf"\b0?{day}\s+{month_en[:3]}\b",
        rf"\b{month_en}\s+0?{day}\b",
        rf"\b{month_en[:3]}\s+0?{day}\b",
        rf"\b{day:02d}[/.-]{month:02d}[/.-](?:{year}|{year % 100:02d})\b",
        rf"\b{month:02d}[/.-]{day:02d}[/.-](?:{year}|{year % 100:02d})\b",
    ]
    return any(re.search(form, text, re.IGNORECASE) for form in forms)


def _looks_cancelled(text: str, flight_number: str) -> bool:
    return _CANCELLED_RE.search(text) is not None and _mentions_flight(text, flight_number)


# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------


def _collect(payload: dict[str, Any]) -> tuple[list[dict[str, str]], list[str]]:
    """Flatten the SerpAPI payload into (sources, snippets)."""
    sources: list[dict[str, str]] = []
    snippets: list[str] = []

    answer_box = payload.get("answer_box") or {}
    if isinstance(answer_box, dict):
        for key in ("answer", "snippet", "title"):
            value = answer_box.get(key)
            if isinstance(value, str) and value.strip():
                snippets.append(value.strip())
        link = answer_box.get("link")
        if isinstance(link, str) and link:
            sources.append({"title": str(answer_box.get("title") or "answer box"), "url": link})

    for result in payload.get("organic_results") or []:
        if not isinstance(result, dict):
            continue
        title = str(result.get("title") or "").strip()
        url = str(result.get("link") or "").strip()
        if url:
            sources.append({"title": title, "url": url})
        # Titles carry the status as often as the snippet does ("AF1234 Delayed").
        parts = [title, str(result.get("snippet") or "").strip()]
        parts += [str(h) for h in (result.get("snippet_highlighted_words") or []) if h]
        text = " ".join(p for p in parts if p)
        if text:
            snippets.append(text)
        if len(snippets) >= MAX_RESULTS:
            break

    return sources[:MAX_RESULTS], snippets[:MAX_RESULTS]


def _request(query: str, api_key: str, timeout: float) -> dict[str, Any]:
    """One SerpAPI call. Every failure mode becomes SearchUnavailable."""
    params = {
        "engine": SERPAPI_ENGINE,
        "q": query,
        "api_key": api_key,
        "hl": "en",
        "gl": "us",
        "num": 10,
    }
    try:
        response = requests.get(SERPAPI_ENDPOINT, params=params, timeout=timeout)
    except requests.Timeout as exc:
        raise SearchUnavailable(f"délai dépassé après {timeout:.0f}s sur SerpAPI") from exc
    except requests.RequestException as exc:
        raise SearchUnavailable(f"SerpAPI injoignable : {type(exc).__name__}") from exc

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}

    # SerpAPI reports quota and bad keys inside the JSON body, sometimes with a
    # 200. Check the payload before trusting the status code.
    error = payload.get("error")
    if isinstance(error, str) and error.strip():
        raise SearchUnavailable(f"SerpAPI a renvoyé une erreur : {error.strip()}")

    if response.status_code == 429:
        raise SearchUnavailable("quota SerpAPI dépassé (HTTP 429)")
    if response.status_code >= 400:
        raise SearchUnavailable(f"SerpAPI a répondu HTTP {response.status_code}")

    status = (payload.get("search_metadata") or {}).get("status")
    if isinstance(status, str) and status.lower() == "error":
        raise SearchUnavailable("SerpAPI a marqué la recherche en erreur")

    return payload


# --------------------------------------------------------------------------
# Public entry point
# --------------------------------------------------------------------------


def search_flight_status(
    flight_number: str,
    date: str,
    *,
    attempt: int = 1,
    timeout: float = 15.0,
) -> dict:
    """Look up the real status of a past flight on the web.

    Returns exactly::

        {"found": bool, "retard_arrivee_h": float | None, "cancelled": bool | None,
         "sources": [{"title": str, "url": str}], "snippets": [str]}

    `found` is True only when a delay or a cancellation was actually
    established. `found: False` still carries the snippets: they are the input
    to the Gemma arbitration downstream.

    Raises:
        SearchUnavailable: no key, network failure, timeout, HTTP or quota error.
        NoUsableResult: the API answered but nothing relates to this flight.

    Both are expected outcomes for a past flight and are routed to the degraded
    mode by the graph. Nothing here ever invents a value to avoid raising.
    """
    api_key = config.serpapi_key().strip()
    if not api_key:
        # No HTTP call at all: fail before touching the network.
        raise SearchUnavailable("clé SerpAPI absente (SERPAPI_KEY non renseignée)")

    if not (flight_number or "").strip():
        raise NoUsableResult("numéro de vol manquant : recherche web impossible")

    query = build_query(flight_number, date, attempt)
    payload = _request(query, api_key, timeout)
    sources, snippets = _collect(payload)

    if not snippets:
        raise NoUsableResult(
            f"aucun résultat exploitable pour « {query} »", sources=sources, snippets=snippets
        )

    relevant = [s for s in snippets if _mentions_flight(s, flight_number)]
    if not relevant:
        # Results exist but none of them names the flight: for a past flight
        # this is the normal outcome, and asserting anything from it would be
        # pure invention.
        raise NoUsableResult(
            f"aucun résultat ne mentionne le vol {flight_number}",
            sources=sources,
            snippets=snippets,
        )

    # Only snippets that name BOTH the flight and the date can say anything
    # about this particular flight. Everything else is route documentation.
    dated = [s for s in relevant if _mentions_date(s, date)]

    delays = {d for d in (parse_delay_hours(s) for s in dated) if d is not None}
    # One agreed value is usable; several contradict each other, and a
    # contradiction is a declared failure mode, not something to average.
    delay = delays.pop() if len(delays) == 1 else None

    cancelled: bool | None = True if any(_looks_cancelled(s, flight_number) for s in dated) else None

    return {
        "found": delay is not None or cancelled is True,
        "retard_arrivee_h": delay,
        "cancelled": cancelled,
        "sources": sources,
        "snippets": snippets,
    }


if __name__ == "__main__":  # pragma: no cover - manual probe, useful during the demo
    import json
    import sys

    number = sys.argv[1] if len(sys.argv) > 1 else "AF1680"
    day = sys.argv[2] if len(sys.argv) > 2 else "2026-06-15"
    print(f"clé SerpAPI : {config.redacted(config.serpapi_key())}")
    try:
        print(json.dumps(search_flight_status(number, day), indent=2, ensure_ascii=False))
    except SearchError as exc:
        print(f"{type(exc).__name__}: {exc}")
