"""Deterministic EU261 logic: distance and compensation amount.

NOTHING in this file calls a model. This is the central claim of the project:
the LLM decides (qualification, arbitration, drafting), the code calculates
(distance, tariff bands, thresholds). An LLM that computes a distance or an
amount is an LLM that will eventually be 50 EUR off without anyone noticing.

Simplified rules for a prototype. See the README disclaimer.

Naming note: identifiers, comments and docstrings are English. Two families of
strings stay French, as in dossier.py:
  - the returned dict keys (eligible, montant, reduction_50, regle_appliquee,
    motif_refus), which the spec imposes as a data contract;
  - the ``regle_appliquee`` / ``motif_refus`` texts, which are quoted verbatim
    to the user in the refusal explanation and in the claim letter.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import lru_cache
from math import asin, cos, radians, sin, sqrt
from pathlib import Path

AIRPORTS_PATH = Path(__file__).resolve().parent.parent / "data" / "airports.csv"

# States where Regulation (EC) No 261/2004 applies: the EU27, plus Iceland,
# Norway and Switzerland. The UK left it (UK261 regime since 2021).
EU261_COUNTRIES = frozenset(
    {
        "AT", "BE", "BG", "HR", "CY", "CZ", "DK", "EE", "FI", "FR", "DE", "GR",
        "HU", "IE", "IT", "LV", "LT", "LU", "MT", "NL", "PL", "PT", "RO", "SK",
        "SI", "ES", "SE",  # EU27
        "IS", "NO", "CH",  # EEA + Switzerland
    }
)

EARTH_RADIUS_KM = 6371.0

# Arrival-delay thresholds, in hours, below which a re-routing triggers a 50%
# reduction of the compensation (art. 7 §2). Keyed by tariff band.
REDUCTION_THRESHOLDS_H = {250: 2.0, 400: 3.0, 600: 4.0}

DELAY_THRESHOLD_H = 3.0  # art. 6 + Sturgeon ruling (C-402/07)
CANCELLATION_NOTICE_DAYS = 14  # art. 5 §1 c)


@dataclass(frozen=True)
class Airport:
    iata: str
    name: str
    city: str
    country: str
    latitude: float
    longitude: float

    @property
    def in_eu(self) -> bool:
        return self.country in EU261_COUNTRIES


class UnknownAirport(KeyError):
    """IATA code missing from the local reference table."""


@lru_cache(maxsize=1)
def _reference_table() -> dict[str, Airport]:
    # CSV headers stay French (iata,nom,ville,pays,latitude,longitude): the file
    # is shared data, not code.
    with AIRPORTS_PATH.open(encoding="utf-8") as stream:
        return {
            row["iata"]: Airport(
                iata=row["iata"],
                name=row["nom"],
                city=row["ville"],
                country=row["pays"],
                latitude=float(row["latitude"]),
                longitude=float(row["longitude"]),
            )
            for row in csv.DictReader(stream)
        }


def airport(iata: str) -> Airport:
    """Airport by IATA code. Raises UnknownAirport rather than guessing."""
    code = (iata or "").strip().upper()
    try:
        return _reference_table()[code]
    except KeyError as err:
        raise UnknownAirport(
            f"IATA code « {code} » missing from {AIRPORTS_PATH.name}"
        ) from err


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in km between two points."""
    phi1, phi2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(a))


def compute_distance(iata_dep: str, iata_arr: str) -> float:
    """Flight distance in km. Deterministic."""
    dep, arr = airport(iata_dep), airport(iata_arr)
    return haversine(dep.latitude, dep.longitude, arr.latitude, arr.longitude)


def is_intra_eu(iata_dep: str, iata_arr: str) -> bool:
    """True when both endpoints are within the EU261 area."""
    return airport(iata_dep).in_eu and airport(iata_arr).in_eu


def check_scope(iata_dep: str, iata_arr: str, eu_carrier: bool) -> tuple[bool, str]:
    """Geographic scope of the regulation (art. 3).

    Returns (applicable, rationale). Two cases bring a flight into scope:
      - departure from an EU airport, whatever the carrier;
      - arrival in the EU, only if the operating carrier is an EU carrier.

    The rationale is French: it is quoted back to the user.
    """
    dep, arr = airport(iata_dep), airport(iata_arr)

    if dep.in_eu:
        return True, f"vol au départ de {dep.iata} ({dep.country}), situé dans l'UE (art. 3 §1 a)"
    if arr.in_eu and eu_carrier:
        return True, (
            f"vol à destination de {arr.iata} ({arr.country}) opéré par un transporteur "
            "communautaire (art. 3 §1 b)"
        )
    if arr.in_eu:
        return False, (
            f"le vol arrive dans l'UE ({arr.iata}) mais n'est pas opéré par un transporteur "
            "communautaire : le règlement ne s'applique pas (art. 3 §1 b)"
        )
    return False, (
        f"ni le départ ({dep.iata}, {dep.country}) ni l'arrivée ({arr.iata}, {arr.country}) "
        "ne relèvent de l'UE : le règlement ne s'applique pas (art. 3)"
    )


def compensation_tier(distance_km: float, intra_eu: bool) -> int:
    """Tariff band of art. 7 §1, in euros.

    <= 1500 km          -> 250
    > 1500 km intra-EU  -> 400
    1500-3500 km        -> 400
    > 3500 km with a non-EU endpoint -> 600
    """
    if distance_km <= 1500:
        return 250
    if intra_eu:
        return 400
    if distance_km <= 3500:
        return 400
    return 600


def compute_compensation(
    distance_km: float,
    type_perturbation: str,
    retard_arrivee_h: float,
    reachemine: bool,
    retard_reacheminement_h: float | None,
    *,
    intra_eu: bool = True,
    in_scope: bool = True,
    out_of_scope_reason: str | None = None,
    cancellation_notice_days: int | None = None,
    extraordinary_circumstance: bool = False,
    extraordinary_reason: str | None = None,
) -> dict:
    """EU261 decision table. Pure Python, deterministic, testable.

    The five positional parameters are the contract imposed by the spec (and
    keep their French names for that reason); the keyword-only arguments carry
    the context needed to characterise a refusal.

    Returns {eligible, montant, reduction_50, regle_appliquee, motif_refus}.
    """
    if not in_scope:
        return _refusal(
            "art. 3 : champ d'application géographique",
            out_of_scope_reason or "le vol ne relève pas du champ d'application du règlement",
        )

    if extraordinary_circumstance:
        return _refusal(
            "art. 5 §3 : circonstances extraordinaires",
            extraordinary_reason
            or "la perturbation résulte de circonstances extraordinaires qui n'auraient pas "
            "pu être évitées même si toutes les mesures raisonnables avaient été prises",
        )

    # Triggering event (art. 4, 5, 6). Note the delay threshold applies to the
    # delay at ARRIVAL, not at departure -- the classic mistake.
    if type_perturbation == "retard":
        if retard_arrivee_h is None or retard_arrivee_h < DELAY_THRESHOLD_H:
            observed = "inconnu" if retard_arrivee_h is None else f"{retard_arrivee_h:.2f} h"
            return _refusal(
                f"art. 6 + arrêt Sturgeon : seuil de {DELAY_THRESHOLD_H:.0f} h à l'arrivée",
                f"le retard constaté à l'arrivée est de {observed}, inférieur au seuil de "
                f"{DELAY_THRESHOLD_H:.0f} heures ouvrant droit à indemnisation",
            )
        rule = f"art. 6 : retard de {retard_arrivee_h:.2f} h à l'arrivée"

    elif type_perturbation == "annulation":
        # An unknown notice period is NOT treated as favourable to the passenger:
        # that would assert a fact nobody established. Symmetrical with an unknown
        # arrival delay above. The graph should ask the user for the notification
        # date before qualifying a cancellation (step 3).
        if cancellation_notice_days is None:
            return _refusal(
                "art. 5 §1 c) : préavis d'annulation inconnu",
                "la date à laquelle l'annulation vous a été notifiée n'est pas établie ; "
                "elle détermine le droit à indemnisation et doit être confirmée avant "
                "toute réclamation",
            )
        if cancellation_notice_days >= CANCELLATION_NOTICE_DAYS:
            return _refusal(
                f"art. 5 §1 c) : préavis d'annulation de {CANCELLATION_NOTICE_DAYS} jours",
                f"l'annulation a été notifiée {cancellation_notice_days} jours avant le départ, "
                f"soit au moins {CANCELLATION_NOTICE_DAYS} jours à l'avance",
            )
        rule = (
            f"art. 5 : annulation notifiée moins de {CANCELLATION_NOTICE_DAYS} jours "
            "avant le départ"
        )

    elif type_perturbation == "refus_embarquement":
        rule = "art. 4 : refus d'embarquement pour surréservation"

    else:
        return _refusal(
            "fait générateur non reconnu",
            f"le type de perturbation « {type_perturbation} » n'ouvre pas droit à "
            "indemnisation au titre du règlement",
        )

    base = compensation_tier(distance_km, intra_eu)

    # 50% reduction when a re-routing keeps the arrival delay under the band's
    # threshold (art. 7 §2).
    reduced = False
    effective_delay = retard_reacheminement_h if reachemine else None
    if effective_delay is not None and effective_delay < REDUCTION_THRESHOLDS_H[base]:
        reduced = True
        rule += (
            f" ; réacheminement limitant le retard à {effective_delay:.2f} h "
            f"(< {REDUCTION_THRESHOLDS_H[base]:.0f} h) : réduction de 50 % (art. 7 §2)"
        )

    amount = base // 2 if reduced else base
    return {
        "eligible": True,
        "montant": amount,
        "reduction_50": reduced,
        "regle_appliquee": (
            f"{rule} ; art. 7 §1 : barème {base} EUR pour {distance_km:.0f} km"
            f"{' (vol intra-UE)' if intra_eu else ''}"
        ),
        "motif_refus": None,
    }


def _refusal(rule: str, reason: str) -> dict:
    """Build a negative verdict. The agent is allowed to conclude "no claim"."""
    return {
        "eligible": False,
        "montant": 0,
        "reduction_50": False,
        "regle_appliquee": rule,
        "motif_refus": reason,
    }
