"""Tests déterministes du routage de dossiers aériens."""
from __future__ import annotations

import io
import unittest
from unittest.mock import patch
import wave

from agent import (
    AgentError,
    merge_incident_statement,
    process,
    research_case,
    route_case,
    transcribe_audio,
)
from eu261 import (
    assess_ticket_reimbursement,
    compensation_amount,
    compute_distance,
    qualify_delay,
)
from tools import (
    RESEARCH_TOOL_DEFINITIONS,
    _api_key,
    build_research_context,
    build_rule_query,
    verify_air_passenger_rule,
)


COMPLETE_FLIGHT = {
    "flight_number": "AU 3127",
    "origin": "Paris CDG",
    "destination": "Lisbonne LIS",
    "departure_date": "2026-09-14",
}


class AudioTranscriptionTests(unittest.TestCase):
    @staticmethod
    def wav_bytes() -> bytes:
        output = io.BytesIO()
        with wave.open(output, "wb") as recording:
            recording.setnchannels(1)
            recording.setsampwidth(2)
            recording.setframerate(16000)
            recording.writeframes(b"\x00\x00" * 1600)
        return output.getvalue()

    @patch("agent._chat")
    def test_transcription_uses_local_gemma_audio(self, chat):
        chat.return_value = {
            "message": {
                "content": "Le vol est arrivé avec 3 h 25 de retard.\n"
            }
        }

        transcription = transcribe_audio(self.wav_bytes())

        self.assertEqual(
            transcription,
            "Le vol est arrivé avec 3 h 25 de retard.",
        )
        payload = chat.call_args.args[0]
        self.assertEqual(payload["model"], "gemma4:12b")
        self.assertFalse(payload["think"])
        self.assertEqual(len(payload["messages"][0]["images"]), 1)
        self.assertNotIn("audios", payload["messages"][0])

    def test_transcription_rejects_invalid_audio(self):
        with self.assertRaises(AgentError):
            transcribe_audio(b"pas un enregistrement")


class RouteCaseTests(unittest.TestCase):
    def test_ticket_without_disruption_requests_context(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
        }

        decision = route_case(extracted)

        self.assertEqual(decision["status"], "needs_information")
        self.assertIsNone(decision["next_tool"])
        self.assertIn("Que s'est-il passé", decision["questions"][0])

    def test_delay_without_duration_requests_arrival_delay(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "delay",
            "delay_minutes": None,
        }

        decision = route_case(extracted)

        self.assertEqual(decision["status"], "needs_information")
        self.assertIn("arrivée réelle", decision["questions"][0])

    def test_complete_incident_is_ready_for_research(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "delay",
            "delay_minutes": 205,
        }

        decision = route_case(extracted)

        self.assertEqual(decision["status"], "ready_for_research")
        self.assertEqual(decision["next_tool"], "verify_air_passenger_rule")

    def test_incident_statement_normalizes_hours_and_minutes(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol est arrivé avec 3 h 25 de retard après un problème technique.",
        )

        self.assertEqual(extracted["disruption_type"], "delay")
        self.assertEqual(extracted["delay_minutes"], 205)
        self.assertEqual(extracted["arrival_delay_minutes"], 205)
        self.assertIn("problème technique", extracted["disruption_cause"])

    def test_departure_delay_is_not_treated_as_arrival_delay(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol avait 5 h 10 de retard au départ.",
        )

        self.assertEqual(extracted["departure_delay_minutes"], 310)
        self.assertIsNone(extracted["delay_minutes"])

    def test_statement_distinguishes_two_delay_durations(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "arrival_delay_minutes": None,
            "departure_delay_minutes": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol avait 5 h de retard au départ et 2 h 30 à l'arrivée.",
        )

        self.assertEqual(extracted["departure_delay_minutes"], 300)
        self.assertEqual(extracted["arrival_delay_minutes"], 150)
        self.assertEqual(extracted["delay_minutes"], 150)

    def test_statement_records_an_explicitly_abandoned_trip(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "arrival_delay_minutes": None,
            "departure_delay_minutes": None,
            "trip_completed": None,
            "disruption_cause": None,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol avait 5 h de retard au départ, j'ai renoncé au voyage.",
        )

        self.assertEqual(extracted["departure_delay_minutes"], 300)
        self.assertFalse(extracted["trip_completed"])

    def test_statement_without_explicit_choice_clears_model_inference(self):
        extracted = {
            **COMPLETE_FLIGHT,
            "disruption_type": "unknown",
            "delay_minutes": None,
            "trip_completed": False,
            "evidence": [],
        }

        merge_incident_statement(
            extracted,
            "Le vol est arrivé avec 3 h 25 de retard.",
        )

        self.assertIsNone(extracted["trip_completed"])

    @patch("agent.extract_flight")
    def test_incomplete_case_does_not_call_research(self, extract_flight):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "disruption_type": "unknown",
                "delay_minutes": None,
            },
            1.2,
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertIsNone(result["research"])
        self.assertIsNone(result["claim"])

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_ticket_refund_is_not_masked_by_compensation_refusal(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                "disruption_type": "delay",
                "delay_minutes": 150,
                "arrival_delay_minutes": 150,
                "departure_delay_minutes": 300,
                "trip_completed": False,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"verified_live": True},
                "claim_channel": {"status": "demo_carrier"},
            },
            [],
        )
        draft_claim.return_value = ({"summary": "Remboursement possible."}, 1.0)

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "non_eligible")
        self.assertEqual(result["reimbursement"]["status"], "likely")
        self.assertEqual(result["decision"]["status"], "ready_for_claim")
        self.assertIsNone(result["refusal"])
        self.assertIsNotNone(result["claim"])

    @patch("agent.draft_claim")
    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_successful_pipeline_finishes_ready_for_claim(
        self, extract_flight, research_case_mock, draft_claim
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                "disruption_type": "delay",
                "delay_minutes": 205,
                "arrival_delay_minutes": 205,
                "departure_delay_minutes": None,
                "trip_completed": None,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"verified_live": True},
                "claim_channel": {"status": "demo_carrier"},
            },
            [],
        )
        draft_claim.return_value = ({"summary": "Dossier prêt."}, 1.0)

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "likely")
        self.assertEqual(result["decision"]["status"], "ready_for_claim")
        self.assertIsNotNone(result["claim"])
        self.assertIsNone(result["decision"]["next_tool"])

    def test_cdg_lis_distance_and_amount(self):
        distance = compute_distance("CDG", "LIS")

        self.assertGreater(distance, 1400)
        self.assertLess(distance, 1500)
        self.assertEqual(compensation_amount(distance, intra_eu=True), 250)

    def test_intra_eu_over_1500_is_400(self):
        distance = compute_distance("CDG", "ATH")

        self.assertGreater(distance, 1500)
        self.assertEqual(compensation_amount(distance, intra_eu=True), 400)

    def test_long_non_eu_route_is_600(self):
        distance = compute_distance("CDG", "JFK")

        self.assertGreater(distance, 3500)
        self.assertEqual(compensation_amount(distance, intra_eu=False), 600)

    def test_delay_below_three_hours_is_non_eligible(self):
        qualification = qualify_delay(
            {
                "origin": "PARIS CDG",
                "destination": "LISBONNE LIS",
                "delay_minutes": 130,
            }
        )

        self.assertEqual(qualification["status"], "non_eligible")
        self.assertEqual(qualification["compensation_eur"], 0)

    def test_arrival_delay_alone_does_not_prove_ticket_reimbursement(self):
        assessment = assess_ticket_reimbursement(
            {
                "disruption_type": "delay",
                "arrival_delay_minutes": 205,
            }
        )

        self.assertEqual(assessment["status"], "needs_information")
        self.assertIn("retard au départ", assessment["reason"])

    def test_five_hour_delay_requires_the_passenger_choice(self):
        assessment = assess_ticket_reimbursement(
            {
                "disruption_type": "delay",
                "departure_delay_minutes": 310,
            },
            verified_live=True,
        )

        self.assertEqual(assessment["status"], "needs_information")
        self.assertIn("renoncé", assessment["reason"])

    def test_five_hour_delay_and_abandoned_trip_can_trigger_reimbursement(self):
        assessment = assess_ticket_reimbursement(
            {
                "disruption_type": "delay",
                "departure_delay_minutes": 310,
                "trip_completed": False,
            },
            verified_live=True,
        )

        self.assertEqual(assessment["status"], "likely")
        self.assertIsNone(assessment["amount_eur"])

    @patch("agent.research_case")
    @patch("agent.extract_flight")
    def test_refund_question_is_not_masked_by_compensation_refusal(
        self, extract_flight, research_case_mock
    ):
        extract_flight.return_value = (
            {
                **COMPLETE_FLIGHT,
                "airline": "Aurora Airlines",
                "disruption_type": "delay",
                "delay_minutes": 150,
                "arrival_delay_minutes": 150,
                "departure_delay_minutes": 300,
                "trip_completed": None,
                "uncertain_fields": [],
            },
            1.0,
        )
        research_case_mock.return_value = (
            {
                "rights": {"verified_live": True},
                "claim_channel": {"status": "demo_carrier"},
            },
            [],
        )

        result = process(__import__("pathlib").Path("unused.pdf"))

        self.assertEqual(result["qualification"]["status"], "non_eligible")
        self.assertEqual(result["reimbursement"]["status"], "needs_information")
        self.assertEqual(result["decision"]["status"], "needs_information")
        self.assertIn("renoncé", result["decision"]["questions"][0])
        self.assertIsNone(result["refusal"])
        self.assertIsNone(result["claim"])

    def test_serpapi_rule_query_excludes_personal_data(self):
        query = build_rule_query(
            {
                "passenger_name": "MARTIN LEA",
                "booking_reference": "FQ7T2K",
                "disruption_type": "delay",
                "delay_minutes": 205,
                "origin": "PARIS CDG",
                "destination": "LISBONNE LIS",
            }
        )

        self.assertNotIn("MARTIN", query)
        self.assertNotIn("FQ7T2K", query)
        self.assertIn("retard", query)
        self.assertIn("site:europa.eu", query)
        self.assertNotIn(" OR ", query)


class NativeToolCallingTests(unittest.TestCase):
    def setUp(self):
        self.extracted = {
            **COMPLETE_FLIGHT,
            "passenger_name": "MARTIN LEA",
            "booking_reference": "FQ7T2K",
            "airline": "Aurora Airlines",
            "disruption_type": "delay",
            "arrival_delay_minutes": 205,
            "departure_delay_minutes": None,
        }
        self.rights = {
            "status": "online",
            "verified_live": True,
            "reason": None,
            "sources": [],
        }
        self.channel = {
            "status": "demo_carrier",
            "channel": None,
            "message": "Compagnie fictive.",
        }

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_gemma_tool_calls_are_parsed_and_dispatched(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "verify_air_passenger_rule",
                            "arguments": {
                                "disruption_type": "delay",
                                "origin": "Paris CDG",
                                "destination": "Lisbonne LIS",
                                "arrival_delay_minutes": 205,
                                "departure_delay_minutes": None,
                            },
                        }
                    },
                    {
                        "function": {
                            "name": "find_claim_channel",
                            "arguments": {"airline": "Aurora Airlines"},
                        }
                    },
                ]
            }
        }
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        research, trace = research_case(self.extracted)

        self.assertEqual(research["rights"]["status"], "online")
        verify_rule.assert_called_once()
        find_channel.assert_called_once_with({"airline": "Aurora Airlines"})
        self.assertEqual(trace[0]["outcome"], "gemma_tool_calls")
        self.assertEqual(trace[1]["selected_by"], "gemma_tool_call")
        self.assertEqual(trace[2]["selected_by"], "gemma_tool_call")
        payload = chat.call_args.args[0]
        self.assertEqual(payload["tools"], RESEARCH_TOOL_DEFINITIONS)
        serialized_messages = str(payload["messages"])
        self.assertNotIn("MARTIN LEA", serialized_messages)
        self.assertNotIn("FQ7T2K", serialized_messages)

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_no_tool_call_uses_deterministic_fallback(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {"message": {"content": "Je propose une recherche."}}
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        verify_rule.assert_called_once()
        find_channel.assert_called_once()
        self.assertEqual(trace[0]["outcome"], "deterministic_fallback")
        self.assertIn("aucun outil", trace[0]["details"])
        self.assertEqual(trace[1]["selected_by"], "deterministic_fallback")

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_tool_result_is_returned_before_second_tool_call(
        self, chat, verify_rule, find_channel
    ):
        chat.side_effect = [
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "verify_air_passenger_rule",
                                "arguments": {
                                    "disruption_type": "delay",
                                    "origin": "Paris CDG",
                                    "destination": "Lisbonne LIS",
                                    "arrival_delay_minutes": 205,
                                    "departure_delay_minutes": None,
                                },
                            }
                        }
                    ]
                }
            },
            {
                "message": {
                    "tool_calls": [
                        {
                            "function": {
                                "name": "find_claim_channel",
                                "arguments": {"airline": "Aurora Airlines"},
                            }
                        }
                    ]
                }
            },
        ]
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        self.assertEqual(chat.call_count, 2)
        second_messages = chat.call_args_list[1].args[0]["messages"]
        tool_messages = [
            message for message in second_messages if message["role"] == "tool"
        ]
        self.assertEqual(tool_messages[0]["tool_name"], "verify_air_passenger_rule")
        self.assertIn('"status": "online"', tool_messages[0]["content"])
        self.assertEqual(trace[0]["outcome"], "gemma_tool_calls")
        self.assertEqual(trace[0]["tool_result_round_trips"], 1)

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_unknown_tool_is_rejected_by_allow_list(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "read_private_file",
                            "arguments": {"path": ".env"},
                        }
                    }
                ]
            }
        }
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        self.assertEqual(trace[0]["rejected_tool_calls"], 1)
        self.assertEqual(trace[0]["outcome"], "deterministic_fallback")
        verify_rule.assert_called_once()
        find_channel.assert_called_once()

    @patch("agent.find_claim_channel")
    @patch("agent.verify_air_passenger_rule")
    @patch("agent._chat")
    def test_extra_personal_argument_is_rejected(
        self, chat, verify_rule, find_channel
    ):
        chat.return_value = {
            "message": {
                "tool_calls": [
                    {
                        "function": {
                            "name": "find_claim_channel",
                            "arguments": {
                                "airline": "Aurora Airlines",
                                "booking_reference": "FQ7T2K",
                            },
                        }
                    }
                ]
            }
        }
        verify_rule.return_value = self.rights
        find_channel.return_value = self.channel

        _, trace = research_case(self.extracted)

        self.assertEqual(trace[0]["rejected_tool_calls"], 1)
        find_channel.assert_called_once_with({"airline": "Aurora Airlines"})
        self.assertEqual(trace[2]["selected_by"], "deterministic_fallback")

    def test_tool_schemas_forbid_additional_properties(self):
        for declaration in RESEARCH_TOOL_DEFINITIONS:
            parameters = declaration["function"]["parameters"]
            self.assertFalse(parameters["additionalProperties"])
            self.assertEqual(
                set(parameters["required"]),
                set(parameters["properties"]),
            )

    def test_research_context_is_minimized(self):
        context = build_research_context(self.extracted)

        self.assertNotIn("passenger_name", context)
        self.assertNotIn("booking_reference", context)
        self.assertEqual(context["arrival_delay_minutes"], 205)

    @patch("tools._dotenv_value")
    @patch("tools.os.getenv")
    def test_environment_key_has_priority_over_dotenv(self, getenv, dotenv_value):
        getenv.side_effect = (
            lambda name: "environment-value" if name == "SERPAPI_KEY" else None
        )

        self.assertEqual(_api_key(), "environment-value")
        dotenv_value.assert_not_called()

    @patch("tools.web_search", return_value=[])
    def test_empty_search_result_uses_offline_reference(self, _web_search):
        result = verify_air_passenger_rule(self.extracted)

        self.assertEqual(result["status"], "offline")
        self.assertFalse(result["verified_live"])
        self.assertEqual(len(result["sources"]), 2)

    @patch(
        "tools.web_search",
        return_value=[
            {
                "title": "Résultat hors sujet",
                "link": "https://europa.eu/example",
                "snippet": "Sans rapport avec les passagers aériens.",
            },
            {
                "title": "Droits des passagers aériens - Your Europe",
                "link": (
                    "https://europa.eu/youreurope/citizens/travel/"
                    "passenger-rights/air/index_fr.htm"
                ),
                "snippet": "Référentiel officiel.",
            },
        ],
    )
    def test_live_rule_verification_filters_irrelevant_sources(
        self, _web_search
    ):
        result = verify_air_passenger_rule(self.extracted)

        self.assertEqual(result["status"], "online")
        self.assertTrue(result["verified_live"])
        self.assertEqual(len(result["sources"]), 1)
        self.assertIn("passenger-rights/air", result["sources"][0]["link"])


if __name__ == "__main__":
    unittest.main()
