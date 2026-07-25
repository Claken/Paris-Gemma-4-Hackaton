#!/usr/bin/env python
"""Unit tests for the deterministic EU261 logic (`agent/eu261.py`).

Exit criterion for step 2 of the build order: distance and compensation must be
correct on known cases, refusal cases included.

Runs with no test framework and no third-party dependency:

    uv run tests/test_eu261.py

Every check is a top-level ``test_*`` function using plain ``assert``, so the
same file also runs under pytest if it ever gets installed. ``main()`` calls
each one explicitly, prints one line per case and exits non-zero on failure.

Reference distances are great-circle values recomputed from `data/airports.csv`
and cross-checked against published airport-pair distances; tolerances are wide
enough (a few tens of km, i.e. well under 1%) that they assert the formula is
right without pinning a float produced by the implementation under test.
"""

from __future__ import annotations

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agent.eu261 import (  # noqa: E402
    UnknownAirport,
    airport,
    check_scope,
    compensation_tier,
    compute_compensation,
    compute_distance,
    haversine,
    is_intra_eu,
)

RESULT_KEYS = {"eligible", "montant", "reduction_50", "regle_appliquee", "motif_refus"}


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def assert_close(actual: float, expected: float, tol: float, label: str) -> None:
    """Assert ``actual`` is within ``tol`` of ``expected``."""
    assert abs(actual - expected) <= tol, (
        f"{label}: expected {expected} +/- {tol}, got {actual:.3f}"
    )


def assert_refusal(result: dict, label: str) -> None:
    """A refusal must be explicit: not eligible, zero, and a stated reason."""
    assert set(result) == RESULT_KEYS, f"{label}: unexpected keys {sorted(result)}"
    assert result["eligible"] is False, f"{label}: eligible should be False"
    assert result["montant"] == 0, f"{label}: montant should be 0, got {result['montant']}"
    assert result["reduction_50"] is False, f"{label}: reduction_50 should be False"
    motif = result["motif_refus"]
    assert isinstance(motif, str) and motif.strip(), (
        f"{label}: motif_refus must be a non-empty string, got {motif!r}"
    )


def assert_award(result: dict, montant: int, reduction: bool, label: str) -> None:
    """An award must carry the exact amount, the reduction flag and a rule."""
    assert set(result) == RESULT_KEYS, f"{label}: unexpected keys {sorted(result)}"
    assert result["eligible"] is True, f"{label}: eligible should be True"
    assert result["montant"] == montant, (
        f"{label}: expected {montant} EUR, got {result['montant']}"
    )
    assert result["reduction_50"] is reduction, (
        f"{label}: expected reduction_50={reduction}, got {result['reduction_50']}"
    )
    assert result["motif_refus"] is None, f"{label}: motif_refus should be None"
    assert isinstance(result["regle_appliquee"], str) and result["regle_appliquee"].strip(), (
        f"{label}: regle_appliquee must be a non-empty string"
    )


def delay_case(distance_km: float, hours: float, **kwargs) -> dict:
    """Shorthand: a plain delay, no rerouting."""
    kwargs.setdefault("intra_eu", True)
    return compute_compensation(distance_km, "retard", hours, False, None, **kwargs)


# --------------------------------------------------------------------------
# distances
# --------------------------------------------------------------------------


def test_distance_cdg_ath() -> None:
    """CDG-ATH: the reference medium-haul intra-EU pair, ~2100 km."""
    assert_close(compute_distance("CDG", "ATH"), 2100.0, 30.0, "CDG-ATH")


def test_distance_short_hop() -> None:
    """CDG-NCE: short domestic hop, ~695 km."""
    assert_close(compute_distance("CDG", "NCE"), 695.0, 20.0, "CDG-NCE")


def test_distance_long_haul() -> None:
    """CDG-JFK: transatlantic long haul, ~5835 km."""
    assert_close(compute_distance("CDG", "JFK"), 5835.0, 40.0, "CDG-JFK")


def test_distance_is_symmetric() -> None:
    """A->B and B->A must be the same distance."""
    there = compute_distance("CDG", "JFK")
    back = compute_distance("JFK", "CDG")
    assert there == back, f"asymmetric distance: {there} vs {back}"

    cdg, ath = airport("CDG"), airport("ATH")
    h1 = haversine(cdg.latitude, cdg.longitude, ath.latitude, ath.longitude)
    h2 = haversine(ath.latitude, ath.longitude, cdg.latitude, cdg.longitude)
    assert h1 == h2, f"asymmetric haversine: {h1} vs {h2}"


def test_distance_zero_for_same_airport() -> None:
    """Degenerate case: an airport is at distance 0 from itself."""
    assert_close(compute_distance("CDG", "CDG"), 0.0, 1e-6, "CDG-CDG")


def test_unknown_airport_raises() -> None:
    """A bogus IATA code must raise, never silently return a guess."""
    for bogus in ("ZZZ", "", "XQX"):
        try:
            airport(bogus)
        except UnknownAirport:
            pass
        else:
            raise AssertionError(f"airport({bogus!r}) should have raised UnknownAirport")

    try:
        compute_distance("CDG", "ZZZ")
    except UnknownAirport:
        pass
    else:
        raise AssertionError("compute_distance with a bogus arrival should raise")

    assert issubclass(UnknownAirport, KeyError), "UnknownAirport must subclass KeyError"


def test_airport_lookup_fields() -> None:
    """The referential exposes the fields the rest of the agent relies on."""
    cdg = airport("cdg")  # lookup must be case-insensitive
    assert cdg.iata == "CDG"
    assert cdg.country == "FR"
    assert cdg.city and cdg.name
    assert 48.0 < cdg.latitude < 50.0 and 1.0 < cdg.longitude < 4.0
    assert cdg.in_eu is True

    assert airport("JFK").in_eu is False
    # Post-Brexit: the UK left the scope of Regulation (EC) 261/2004.
    assert airport("LHR").in_eu is False, "LHR must not be treated as an EU airport"


def test_is_intra_eu() -> None:
    assert is_intra_eu("CDG", "ATH") is True
    assert is_intra_eu("CDG", "JFK") is False
    assert is_intra_eu("JFK", "LAX") is False
    # An outermost region of an EU member state is still EU territory.
    assert is_intra_eu("CDG", "RUN") is True


# --------------------------------------------------------------------------
# tariff bands
# --------------------------------------------------------------------------


def test_band_250_short_flight() -> None:
    """<= 1500 km: 250 EUR, whatever the intra-EU status."""
    assert compensation_tier(1064.0, True) == 250
    assert compensation_tier(347.0, False) == 250
    assert_award(delay_case(compute_distance("CDG", "MAD"), 4.0), 250, False, "CDG-MAD delay")


def test_band_400_intra_eu_over_1500() -> None:
    """Intra-EU and > 1500 km: 400 EUR (CDG-ATH, ~2100 km)."""
    distance = compute_distance("CDG", "ATH")
    assert compensation_tier(distance, True) == 400
    assert_award(delay_case(distance, 5.0), 400, False, "CDG-ATH delay")


def test_band_400_intra_eu_stays_capped_beyond_3500() -> None:
    """Intra-EU caps at 400 even on a very long flight (CDG-RUN, ~9370 km)."""
    distance = compute_distance("CDG", "RUN")
    assert distance > 3500, "CDG-RUN should be a long-haul intra-EU flight"
    assert compensation_tier(distance, True) == 400
    assert_award(delay_case(distance, 6.0), 400, False, "CDG-RUN delay")


def test_band_400_non_intra_eu_1500_to_3500() -> None:
    """Non intra-EU between 1500 and 3500 km: 400 EUR (CDG-CAI, ~3210 km)."""
    distance = compute_distance("CDG", "CAI")
    assert 1500 < distance < 3500, f"CDG-CAI expected in the middle band, got {distance:.0f}"
    assert compensation_tier(distance, False) == 400
    assert_award(
        delay_case(distance, 4.5, intra_eu=False), 400, False, "CDG-CAI delay"
    )


def test_band_600_non_intra_eu_over_3500() -> None:
    """Non intra-EU and > 3500 km: 600 EUR (CDG-JFK, ~5835 km)."""
    distance = compute_distance("CDG", "JFK")
    assert compensation_tier(distance, False) == 600
    assert_award(
        delay_case(distance, 7.0, intra_eu=False), 600, False, "CDG-JFK delay"
    )


# --------------------------------------------------------------------------
# boundary values (spec text is the reference, not the implementation)
# --------------------------------------------------------------------------


def test_boundary_1500_km() -> None:
    """Spec: "distance <= 1500 km" -> 250. Exactly 1500 km is still 250."""
    assert compensation_tier(1500.0, True) == 250, "1500 km intra-EU must be 250"
    assert compensation_tier(1500.0, False) == 250, "1500 km non intra-EU must be 250"
    assert compensation_tier(1500.01, True) == 400, "just above 1500 km intra-EU -> 400"
    assert compensation_tier(1500.01, False) == 400, "just above 1500 km -> 400"


def test_boundary_3500_km() -> None:
    """Spec: 1500-3500 -> 400, "> 3500 km" -> 600. Exactly 3500 stays at 400."""
    assert compensation_tier(3500.0, False) == 400, "3500 km must still be 400"
    assert compensation_tier(3500.01, False) == 600, "just above 3500 km -> 600"
    assert compensation_tier(3500.0, True) == 400, "intra-EU is 400 either side of 3500"
    assert compensation_tier(3500.01, True) == 400, "intra-EU is capped at 400"


def test_boundary_delay_exactly_3h() -> None:
    """Spec: "retard >= 3h a l'ARRIVEE". Exactly 3.0 h is eligible."""
    assert_award(delay_case(1000.0, 3.0), 250, False, "delay exactly 3.00 h")
    assert_refusal(delay_case(1000.0, 2.99), "delay 2.99 h")


def test_boundary_cancellation_notice_14_days() -> None:
    """Spec: cancellation notified *less than* 14 days ahead. 14 days -> refusal."""
    at_14 = compute_compensation(
        1000.0, "annulation", 0.0, False, None, cancellation_notice_days=14
    )
    assert_refusal(at_14, "cancellation notified 14 days ahead")

    at_13 = compute_compensation(
        1000.0, "annulation", 0.0, False, None, cancellation_notice_days=13
    )
    assert_award(at_13, 250, False, "cancellation notified 13 days ahead")


# --------------------------------------------------------------------------
# refusals
# --------------------------------------------------------------------------


def test_refusal_delay_under_3h() -> None:
    """2h10 at arrival: below the threshold, no compensation."""
    result = delay_case(compute_distance("CDG", "ATH"), 2.17)
    assert_refusal(result, "arrival delay 2.17 h")
    assert "3" in result["motif_refus"], "the reason should mention the 3-hour threshold"


def test_refusal_delay_unknown() -> None:
    """An unknown arrival delay must refuse, never award by default."""
    assert_refusal(delay_case(2100.0, None), "unknown arrival delay")


def test_refusal_cancellation_notified_early() -> None:
    result = compute_compensation(
        2100.0, "annulation", 0.0, False, None, cancellation_notice_days=30
    )
    assert_refusal(result, "cancellation notified 30 days ahead")


def test_refusal_extraordinary_circumstance() -> None:
    """An otherwise eligible 6h delay is refused if caused by a storm."""
    result = compute_compensation(
        2100.0,
        "retard",
        6.0,
        False,
        None,
        extraordinary_circumstance=True,
        extraordinary_reason="tempete Ciaran sur l'aeroport de depart",
    )
    assert_refusal(result, "extraordinary circumstance")
    assert "Ciaran" in result["motif_refus"], "the supplied reason should be carried through"


def test_refusal_cancellation_notice_unknown() -> None:
    """An unknown notice period must not be read as favourable to the passenger.

    Symmetrical with an unknown arrival delay: the agent never asserts a fact
    nobody established, even when doing so would help the claimant.
    """
    result = compute_compensation(2100.0, "annulation", 0.0, False, None)
    assert_refusal(result, "cancellation with unknown notice period")
    assert "notifi" in result["motif_refus"], "the reason should point at the notification date"


def test_refusal_out_of_geographic_scope() -> None:
    result = compute_compensation(
        3974.0,
        "retard",
        8.0,
        False,
        None,
        intra_eu=False,
        in_scope=False,
        out_of_scope_reason="JFK-LAX : vol interieur americain, hors champ du reglement",
    )
    assert_refusal(result, "out of scope")
    assert "JFK" in result["motif_refus"], "the supplied reason should be carried through"


def test_refusal_out_of_scope_without_supplied_reason() -> None:
    """Even with no reason passed in, a refusal still states a motive."""
    assert_refusal(
        compute_compensation(1000.0, "retard", 8.0, False, None, in_scope=False),
        "out of scope, default reason",
    )


def test_refusal_unknown_disruption_type() -> None:
    """A disruption the regulation does not cover is refused, not guessed."""
    assert_refusal(
        compute_compensation(2100.0, "bagage_perdu", 0.0, False, None),
        "unknown disruption type",
    )


def test_refusal_wins_over_everything_else() -> None:
    """Scope is checked before the extraordinary circumstance and the facts."""
    result = compute_compensation(
        6000.0,
        "retard",
        10.0,
        True,
        0.5,
        intra_eu=False,
        in_scope=False,
        extraordinary_circumstance=True,
    )
    assert_refusal(result, "out of scope + extraordinary + reroute")


# --------------------------------------------------------------------------
# 50 % reduction on rerouting (art. 7 §2)
# --------------------------------------------------------------------------


def test_reduction_band_250_under_2h() -> None:
    """250 band: reroute landing 1h30 late -> 125 EUR."""
    result = compute_compensation(1000.0, "annulation", 8.0, True, 1.5, cancellation_notice_days=2)
    assert_award(result, 125, True, "250 band, reroute 1.5 h")


def test_no_reduction_band_250_over_2h() -> None:
    """250 band: reroute still 2h30 late -> full 250 EUR."""
    result = compute_compensation(1000.0, "annulation", 8.0, True, 2.5, cancellation_notice_days=2)
    assert_award(result, 250, False, "250 band, reroute 2.5 h")


def test_no_reduction_band_250_exactly_2h() -> None:
    """Spec says the delay must stay *under* 2 h: exactly 2.0 h is not reduced."""
    result = compute_compensation(1000.0, "annulation", 8.0, True, 2.0, cancellation_notice_days=2)
    assert_award(result, 250, False, "250 band, reroute exactly 2.0 h")


def test_reduction_band_400_under_3h() -> None:
    """400 band: reroute landing 2h30 late -> 200 EUR."""
    result = compute_compensation(2100.0, "retard", 6.0, True, 2.5, intra_eu=True)
    assert_award(result, 200, True, "400 band, reroute 2.5 h")


def test_no_reduction_band_400_exactly_3h() -> None:
    result = compute_compensation(2100.0, "retard", 6.0, True, 3.0, intra_eu=True)
    assert_award(result, 400, False, "400 band, reroute exactly 3.0 h")


def test_reduction_band_600_under_4h() -> None:
    """600 band: reroute landing 3h30 late -> 300 EUR."""
    result = compute_compensation(5835.0, "retard", 9.0, True, 3.5, intra_eu=False)
    assert_award(result, 300, True, "600 band, reroute 3.5 h")


def test_no_reduction_band_600_over_4h() -> None:
    result = compute_compensation(5835.0, "retard", 9.0, True, 4.5, intra_eu=False)
    assert_award(result, 600, False, "600 band, reroute 4.5 h")


def test_no_reduction_when_not_rerouted() -> None:
    """A short reroute delay must be ignored when there was no reroute."""
    result = compute_compensation(1000.0, "retard", 8.0, False, 0.5)
    assert_award(result, 250, False, "not rerouted, stray reroute delay")


def test_no_reduction_when_reroute_delay_unknown() -> None:
    """Rerouted but the arrival delay is unknown: no reduction, no crash."""
    result = compute_compensation(1000.0, "retard", 8.0, True, None)
    assert_award(result, 250, False, "rerouted, unknown reroute delay")


# --------------------------------------------------------------------------
# geographic scope (art. 3)
# --------------------------------------------------------------------------


def test_scope_eu_departure_non_eu_carrier() -> None:
    """Departure from the EU is in scope whoever operates the flight."""
    in_scope, reason = check_scope("CDG", "JFK", False)
    assert in_scope is True, "CDG-JFK on a non-EU carrier must be in scope"
    assert isinstance(reason, str) and reason.strip(), "scope must be motivated"


def test_scope_non_eu_departure_non_eu_carrier_is_out() -> None:
    """Arrival in the EU on a non-EU carrier is *out* of scope."""
    in_scope, reason = check_scope("JFK", "CDG", False)
    assert in_scope is False, "JFK-CDG on a non-EU carrier must be out of scope"
    assert isinstance(reason, str) and reason.strip(), "refusal must be motivated"


def test_scope_non_eu_departure_eu_carrier_is_in() -> None:
    """Arrival in the EU on an EU carrier is in scope."""
    in_scope, reason = check_scope("JFK", "CDG", True)
    assert in_scope is True, "JFK-CDG on an EU carrier must be in scope"
    assert isinstance(reason, str) and reason.strip()


def test_scope_outside_eu_entirely() -> None:
    """Neither end in the EU: out of scope, even for an EU carrier."""
    for eu_carrier in (False, True):
        in_scope, reason = check_scope("JFK", "LAX", eu_carrier)
        assert in_scope is False, f"JFK-LAX must be out of scope (eu_carrier={eu_carrier})"
        assert isinstance(reason, str) and reason.strip()


def test_scope_uk_departure_is_out_of_scope() -> None:
    """Post-Brexit: LHR-CDG on a non-EU carrier is out of scope."""
    assert check_scope("LHR", "CDG", False)[0] is False
    assert check_scope("LHR", "CDG", True)[0] is True, "an EU carrier arriving in the EU is in scope"


def test_scope_feeds_compute_compensation() -> None:
    """End-to-end: check_scope drives the refusal in compute_compensation."""
    in_scope, reason = check_scope("JFK", "CDG", False)
    result = compute_compensation(
        compute_distance("JFK", "CDG"),
        "retard",
        9.0,
        False,
        None,
        intra_eu=is_intra_eu("JFK", "CDG"),
        in_scope=in_scope,
        out_of_scope_reason=reason,
    )
    assert_refusal(result, "JFK-CDG non-EU carrier, end to end")

    in_scope, reason = check_scope("CDG", "JFK", False)
    result = compute_compensation(
        compute_distance("CDG", "JFK"),
        "retard",
        9.0,
        False,
        None,
        intra_eu=is_intra_eu("CDG", "JFK"),
        in_scope=in_scope,
        out_of_scope_reason=reason,
    )
    assert_award(result, 600, False, "CDG-JFK non-EU carrier, end to end")


TESTS = [
    # distances
    test_distance_cdg_ath,
    test_distance_short_hop,
    test_distance_long_haul,
    test_distance_is_symmetric,
    test_distance_zero_for_same_airport,
    test_unknown_airport_raises,
    test_airport_lookup_fields,
    test_is_intra_eu,
    # tariff bands
    test_band_250_short_flight,
    test_band_400_intra_eu_over_1500,
    test_band_400_intra_eu_stays_capped_beyond_3500,
    test_band_400_non_intra_eu_1500_to_3500,
    test_band_600_non_intra_eu_over_3500,
    # boundaries
    test_boundary_1500_km,
    test_boundary_3500_km,
    test_boundary_delay_exactly_3h,
    test_boundary_cancellation_notice_14_days,
    # refusals
    test_refusal_delay_under_3h,
    test_refusal_delay_unknown,
    test_refusal_cancellation_notified_early,
    test_refusal_cancellation_notice_unknown,
    test_refusal_extraordinary_circumstance,
    test_refusal_out_of_geographic_scope,
    test_refusal_out_of_scope_without_supplied_reason,
    test_refusal_unknown_disruption_type,
    test_refusal_wins_over_everything_else,
    # 50 % reduction
    test_reduction_band_250_under_2h,
    test_no_reduction_band_250_over_2h,
    test_no_reduction_band_250_exactly_2h,
    test_reduction_band_400_under_3h,
    test_no_reduction_band_400_exactly_3h,
    test_reduction_band_600_under_4h,
    test_no_reduction_band_600_over_4h,
    test_no_reduction_when_not_rerouted,
    test_no_reduction_when_reroute_delay_unknown,
    # scope
    test_scope_eu_departure_non_eu_carrier,
    test_scope_non_eu_departure_non_eu_carrier_is_out,
    test_scope_non_eu_departure_eu_carrier_is_in,
    test_scope_outside_eu_entirely,
    test_scope_uk_departure_is_out_of_scope,
    test_scope_feeds_compute_compensation,
]


def main() -> int:
    """Run every check, one line per case, non-zero exit if anything failed."""
    width = max(len(test.__name__) for test in TESTS)
    failures: list[tuple[str, str]] = []

    for test in TESTS:
        try:
            test()
        except Exception:  # noqa: BLE001 - a failing check must not stop the run
            failures.append((test.__name__, traceback.format_exc()))
            print(f"FAIL  {test.__name__.ljust(width)}  {sys.exc_info()[1]}")
        else:
            print(f"ok    {test.__name__}")

    total = len(TESTS)
    print(f"\n{total - len(failures)}/{total} checks passed")

    for name, trace in failures:
        print(f"\n--- {name} ---\n{trace}", end="")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
