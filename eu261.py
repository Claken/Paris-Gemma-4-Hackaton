"""Qualification EU261 simplifiée et déterministe pour la démonstration.

Référentiel : règlement (CE) no 261/2004, vérifié le 25 juillet 2026.
Cette table ne remplace pas une analyse juridique et couvre uniquement les
cas nécessaires à la démo.
"""
from __future__ import annotations

import re
from math import asin, cos, radians, sin, sqrt
from typing import Any

RULESET = {
    "name": "EU261 simplified demo rules",
    "verified_on": "2026-07-25",
    "source": (
        "https://europa.eu/youreurope/citizens/travel/"
        "passenger-rights/air/index_fr.htm"
    ),
}

# Sous-ensemble volontairement réduit aux scénarios de démonstration.
AIRPORTS = {
    "ATH": {"lat": 37.9364, "lon": 23.9475, "eu": True},
    "CDG": {"lat": 49.0097, "lon": 2.5479, "eu": True},
    "JFK": {"lat": 40.6413, "lon": -73.7781, "eu": False},
    "LIS": {"lat": 38.7742, "lon": -9.1342, "eu": True},
}


def extract_iata(value: str | None) -> str | None:
    """Retourne le dernier code IATA à trois lettres trouvé."""
    matches = re.findall(r"\b[A-Z]{3}\b", (value or "").upper())
    return matches[-1] if matches else None


def compute_distance(origin: str, destination: str) -> float:
    """Calcule la distance orthodromique entre deux aéroports connus."""
    try:
        departure = AIRPORTS[origin]
        arrival = AIRPORTS[destination]
    except KeyError as exc:
        raise ValueError(f"Aéroport non référencé : {exc.args[0]}") from exc

    lat1, lon1, lat2, lon2 = map(
        radians,
        (
            departure["lat"],
            departure["lon"],
            arrival["lat"],
            arrival["lon"],
        ),
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    haversine = (
        sin(delta_lat / 2) ** 2
        + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    )
    return 6371 * 2 * asin(sqrt(haversine))


def compensation_amount(distance_km: float, intra_eu: bool) -> int:
    """Applique le barème forfaitaire à la distance."""
    if distance_km <= 1500:
        return 250
    if intra_eu or distance_km <= 3500:
        return 400
    return 600


def qualify_delay(
    extracted: dict[str, Any], *, verified_live: bool = False
) -> dict[str, Any]:
    """Qualifie un retard à l'arrivée sans déléguer le calcul au modèle."""
    origin = extract_iata(extracted.get("origin"))
    destination = extract_iata(extracted.get("destination"))
    if not origin or not destination:
        return {
            "status": "needs_information",
            "reason": "Codes IATA de départ ou d'arrivée manquants.",
            "ruleset": RULESET,
        }
    try:
        distance = compute_distance(origin, destination)
    except ValueError as exc:
        return {
            "status": "needs_information",
            "reason": str(exc),
            "ruleset": RULESET,
        }

    departure_eu = bool(AIRPORTS[origin]["eu"])
    arrival_eu = bool(AIRPORTS[destination]["eu"])
    if not departure_eu:
        return {
            "status": "needs_information" if arrival_eu else "non_eligible",
            "reason": (
                "Pour un vol arrivant dans l'UE depuis un pays tiers, le statut "
                "communautaire du transporteur doit être vérifié."
                if arrival_eu
                else "Le trajet est hors du champ géographique simplifié EU261."
            ),
            "distance_km": round(distance, 1),
            "ruleset": RULESET,
        }

    delay_minutes = extracted.get("arrival_delay_minutes")
    if delay_minutes is None:
        # Compatibilité avec les premières extractions du prototype.
        delay_minutes = extracted.get("delay_minutes")
    if delay_minutes is None:
        return {
            "status": "needs_information",
            "reason": "Le retard à l'arrivée doit être renseigné.",
            "distance_km": round(distance, 1),
            "ruleset": RULESET,
        }
    if delay_minutes < 180:
        return {
            "status": "non_eligible",
            "reason": (
                f"Le retard déclaré à l'arrivée est de {delay_minutes} minutes, "
                "sous le seuil de 180 minutes de ce prototype."
            ),
            "distance_km": round(distance, 1),
            "compensation_eur": 0,
            "rule": "Retard à l'arrivée inférieur à 3 heures.",
            "ruleset": RULESET,
        }

    intra_eu = departure_eu and arrival_eu
    amount = compensation_amount(distance, intra_eu)
    return {
        "status": "likely" if verified_live else "conditional",
        "right_type": "eu261_compensation",
        "reason": (
            "Le seuil de retard et la distance sont satisfaits, sous réserve "
            "de la cause, des preuves et des exceptions applicables."
        ),
        "distance_km": round(distance, 1),
        "compensation_eur": amount,
        "rule": (
            f"Retard à l'arrivée >= 3 h ; tranche de distance donnant {amount} €."
        ),
        "ruleset": RULESET,
    }


def assess_ticket_reimbursement(
    extracted: dict[str, Any], *, verified_live: bool = False
) -> dict[str, Any]:
    """Évalue séparément le remboursement du billet pour un retard au départ."""
    disruption = extracted.get("disruption_type")
    if disruption == "cancellation":
        return {
            "status": "likely" if verified_live else "conditional",
            "right_type": "ticket_reimbursement",
            "reason": (
                "En cas d'annulation, le passager doit pouvoir choisir entre "
                "remboursement, réacheminement ou nouvelle réservation."
            ),
            "rule": "Annulation : remboursement proposé comme option.",
            "amount_eur": None,
            "ruleset": RULESET,
        }
    if disruption != "delay":
        return {
            "status": "not_assessed",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Cette vérification couvre les retards au départ et les "
                "annulations."
            ),
            "amount_eur": None,
            "ruleset": RULESET,
        }

    departure_delay = extracted.get("departure_delay_minutes")
    if departure_delay is None:
        return {
            "status": "needs_information",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Le retard à l'arrivée ne suffit pas : indique le retard au "
                "départ pour vérifier le seuil de remboursement de 5 heures."
            ),
            "question": "Combien de retard le vol avait-il au départ ?",
            "amount_eur": None,
            "ruleset": RULESET,
        }
    if departure_delay < 300:
        return {
            "status": "non_eligible",
            "right_type": "ticket_reimbursement",
            "reason": (
                f"Le retard déclaré au départ est de {departure_delay} minutes, "
                "sous le seuil de remboursement de 300 minutes."
            ),
            "rule": "Retard au départ inférieur à 5 heures.",
            "amount_eur": 0,
            "ruleset": RULESET,
        }
    trip_completed = extracted.get("trip_completed")
    if trip_completed is None:
        return {
            "status": "needs_information",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Le seuil de 5 heures au départ est atteint. Indique si le "
                "passager a renoncé au voyage ou s'il a finalement pris le vol."
            ),
            "question": (
                "Avez-vous renoncé au voyage ou avez-vous finalement pris le vol ?"
            ),
            "amount_eur": None,
            "ruleset": RULESET,
        }
    if trip_completed:
        return {
            "status": "non_eligible",
            "right_type": "ticket_reimbursement",
            "reason": (
                "Le vol a été pris : le remboursement du billet inutilisé lié "
                "au renoncement après 5 heures n'est pas retenu."
            ),
            "rule": "Retard au départ d'au moins 5 heures et voyage abandonné.",
            "amount_eur": 0,
            "ruleset": RULESET,
        }
    return {
        "status": "likely" if verified_live else "conditional",
        "right_type": "ticket_reimbursement",
        "reason": (
            "Le retard déclaré au départ atteint 5 heures et le passager a "
            "renoncé au voyage. Le remboursement porte sur le prix du billet, "
            "qui doit être justifié."
        ),
        "rule": "Retard au départ d'au moins 5 heures et voyage abandonné.",
        "amount_eur": None,
        "ruleset": RULESET,
    }


def qualify_case(
    extracted: dict[str, Any], *, verified_live: bool = False
) -> dict[str, Any]:
    """Route vers la qualification déterministe disponible."""
    disruption = extracted.get("disruption_type")
    if disruption == "delay":
        return qualify_delay(extracted, verified_live=verified_live)
    return {
        "status": "needs_information",
        "reason": (
            "Le prototype déterministe couvre pour l'instant uniquement les "
            "retards à l'arrivée."
        ),
        "ruleset": RULESET,
    }
