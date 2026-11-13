"""
Unit and Integration Tests for DocuMind-AI Cognitive Understanding & Fallback Subsystem.
Tests Gemini LLM Client (mocked), Offline Fallback Engine, Prompts, and Unified Service.
"""

import json
import unittest
from unittest.mock import patch, MagicMock
import httpx

from documind.ai.prompts import build_analysis_prompt, SYSTEM_INSTRUCTION
from documind.ai.llm_client import GeminiLLMClient, LLMClientError
from documind.ai.fallback_engine import FallbackUnderstandingEngine
from documind.ai.service import DocumentUnderstandingService
from documind.models import DocuMindAnalysis, ExtractionResult


MOCK_CONTRACT_TEXT = """
COMMERCIAL OFFICE LEASE AGREEMENT
Landlord leases Suite 400 to Tenant commencing August 1, 2026, expiring July 31, 2029.
Base Monthly Rent is $4,500.00 due on the first day of each month.
A late fee penalty of 5% applies after the 5th calendar day.
Tenant must deposit a security deposit of $9,000.00 upon execution.
Tenant agrees to indemnify Landlord from and against all liabilities and breach claims.
Non-payment for more than 10 days constitutes an incurable event of default.
Tenant must maintain $1,000,000 in general liability insurance.
"""

MOCK_GEMINI_SUCCESS_PAYLOAD = {
    "candidates": [
        {
            "content": {
                "parts": [
                    {
                        "text": json.dumps(
                            {
                                "executive_summary": "This is a commercial lease agreement for Suite 400 with a monthly rent of $4,500.00.",
                                "plain_english_breakdown": [
                                    {
                                        "section_title": "Rent Terms",
                                        "simplified_content": "Tenant pays $4,500.00 on the 1st of every month.",
                                    }
                                ],
                                "critical_numbers_and_warnings": [
                                    {
                                        "type": "Financial",
                                        "detail": "$4,500.00 monthly rent",
                                    },
                                    {
                                        "type": "Warning",
                                        "detail": "5% late fee penalty after the 5th day",
                                    },
                                ],
                                "terminology_glossary": [
                                    {
                                        "term": "Indemnify",
                                        "definition": "To compensate or protect from financial loss or legal claims.",
                                    }
                                ],
                                "actionable_takeaways": [
                                    "Pay $4,500.00 rent on or before the 1st of each month."
                                ],
                            }
                        )
                    }
                ]
            }
        }
    ]
}


class TestAIPrompts(unittest.TestCase):
    def test_prompt_construction(self):
        prompt = build_analysis_prompt(MOCK_CONTRACT_TEXT, "lease.pdf", "PDF")
        self.assertIn("lease.pdf", prompt)
        self.assertIn("executive_summary", prompt)
        self.assertIn("critical_numbers_and_warnings", prompt)
        self.assertIn("terminology_glossary", prompt)
        self.assertIn("actionable_takeaways", prompt)
        self.assertIn("$4,500.00", prompt)

    def test_system_instruction_directives(self):
        self.assertIn("TARGET READING LEVEL", SYSTEM_INSTRUCTION)
        self.assertIn("ABSOLUTE NUMERICAL & FACTUAL FIDELITY", SYSTEM_INSTRUCTION)
        self.assertIn("ZERO HALLUCINATION", SYSTEM_INSTRUCTION)


class TestFallbackUnderstandingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = FallbackUnderstandingEngine()

    def test_all_five_sections_generated(self):
        analysis = self.engine.analyze(MOCK_CONTRACT_TEXT, "lease.txt", "Text")
        self.assertIsInstance(analysis, DocuMindAnalysis)
        self.assertTrue(analysis.is_fallback)
        self.assertEqual(analysis.engine_used, "offline_heuristic")

        # 1. Executive Summary
        self.assertTrue(len(analysis.executive_summary) > 20)
        self.assertIn("lease agreement", analysis.executive_summary.lower())

        # 2. Plain-English Breakdown
        self.assertGreater(len(analysis.plain_english_breakdown), 0)
        self.assertTrue(any("rent" in s.section_title.lower() or "term" in s.section_title.lower() for s in analysis.plain_english_breakdown))

        # 3. Critical Numbers & Warnings
        self.assertGreater(len(analysis.critical_numbers_and_warnings), 0)

        # 4. Terminology Glossary
        self.assertGreater(len(analysis.terminology_glossary), 0)

        # 5. Actionable Takeaways
        self.assertGreater(len(analysis.actionable_takeaways), 0)

    def test_numerical_and_currency_extraction(self):
        analysis = self.engine.analyze(MOCK_CONTRACT_TEXT, "lease.txt", "Text")
        critical_details = " ".join(c.detail for c in analysis.critical_numbers_and_warnings)
        self.assertIn("$4,500.00", critical_details)
        self.assertIn("$9,000.00", critical_details)
        self.assertIn("$1,000,000", critical_details)

    def test_dates_and_percentages_extraction(self):
        analysis = self.engine.analyze(MOCK_CONTRACT_TEXT, "lease.txt", "Text")
        critical_details = " ".join(c.detail for c in analysis.critical_numbers_and_warnings)
        self.assertIn("August 1, 2026", critical_details)
        self.assertIn("5%", critical_details)

    def test_obligations_and_warnings_detection(self):
        analysis = self.engine.analyze(MOCK_CONTRACT_TEXT, "lease.txt", "Text")
        types = [c.type for c in analysis.critical_numbers_and_warnings]
        self.assertIn("Warning", types)
        self.assertIn("Obligation", types)

    def test_domain_glossary_matching(self):
        analysis = self.engine.analyze(MOCK_CONTRACT_TEXT, "lease.txt", "Text")
        glossary_terms = [g.term.lower() for g in analysis.terminology_glossary]
        self.assertTrue(any("indemnif" in t for t in glossary_terms))
        self.assertTrue(any("default" in t for t in glossary_terms))
        self.assertTrue(any("breach" in t for t in glossary_terms))

    def test_empty_document_handling(self):
        analysis = self.engine.analyze("", "empty.txt", "Text")
        self.assertEqual(analysis.word_count, 0)
        self.assertTrue(analysis.is_fallback)
        self.assertIn("no readable text", analysis.executive_summary.lower())


class TestGeminiLLMClient(unittest.TestCase):
    def test_unconfigured_client_raises_error(self):
        client = GeminiLLMClient(api_key="")
        self.assertFalse(client.is_configured())
        with self.assertRaises(LLMClientError):
            client.analyze_document(MOCK_CONTRACT_TEXT, "doc.txt")

    @patch("httpx.Client.post")
    def test_successful_mocked_gemini_analysis(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_GEMINI_SUCCESS_PAYLOAD
        mock_post.return_value = mock_resp

        client = GeminiLLMClient(api_key="mock_test_key_xyz", model_name="gemini-1.5-flash")
        self.assertTrue(client.is_configured())

        analysis = client.analyze_document(MOCK_CONTRACT_TEXT, "contract.pdf", "PDF")
        self.assertIsInstance(analysis, DocuMindAnalysis)
        self.assertFalse(analysis.is_fallback)
        self.assertIn("gemini_api", analysis.engine_used)
        self.assertIn("$4,500.00", analysis.executive_summary)
        self.assertEqual(len(analysis.critical_numbers_and_warnings), 2)
        self.assertEqual(analysis.terminology_glossary[0].term, "Indemnify")

    @patch("httpx.Client.post")
    def test_api_network_failure_raises_llm_error(self, mock_post):
        mock_post.side_effect = httpx.ConnectError("Connection refused by host")
        client = GeminiLLMClient(api_key="mock_key")
        with self.assertRaises(LLMClientError) as ctx:
            client.analyze_document(MOCK_CONTRACT_TEXT, "doc.txt")
        self.assertIn("Network error", str(ctx.exception))

    @patch("httpx.Client.post")
    def test_api_timeout_raises_llm_error(self, mock_post):
        mock_post.side_effect = httpx.TimeoutException("Timed out")
        client = GeminiLLMClient(api_key="mock_key")
        with self.assertRaises(LLMClientError) as ctx:
            client.analyze_document(MOCK_CONTRACT_TEXT, "doc.txt")
        self.assertIn("timed out", str(ctx.exception).lower())

    @patch("httpx.Client.post")
    def test_malformed_json_response_raises_llm_error(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Not valid JSON at all"}]}}]
        }
        mock_post.return_value = mock_resp

        client = GeminiLLMClient(api_key="mock_key")
        with self.assertRaises(LLMClientError) as ctx:
            client.analyze_document(MOCK_CONTRACT_TEXT, "doc.txt")
        self.assertIn("Failed to parse Gemini output", str(ctx.exception))


class TestDocumentUnderstandingService(unittest.TestCase):
    def test_service_unconfigured_uses_offline_fallback(self):
        service = DocumentUnderstandingService(
            llm_client=GeminiLLMClient(api_key=""),
            fallback_engine=FallbackUnderstandingEngine(),
        )
        analysis = service.analyze(MOCK_CONTRACT_TEXT, "lease.txt", "Text")
        self.assertTrue(analysis.is_fallback)
        self.assertEqual(analysis.engine_used, "offline_heuristic")
        self.assertIn("$4,500.00", " ".join(c.detail for c in analysis.critical_numbers_and_warnings))

    @patch("httpx.Client.post")
    def test_service_online_mode_uses_gemini(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = MOCK_GEMINI_SUCCESS_PAYLOAD
        mock_post.return_value = mock_resp

        service = DocumentUnderstandingService(
            llm_client=GeminiLLMClient(api_key="valid_key"),
            fallback_engine=FallbackUnderstandingEngine(),
        )
        analysis = service.analyze(MOCK_CONTRACT_TEXT, "lease.pdf", "PDF")
        self.assertFalse(analysis.is_fallback)
        self.assertIn("gemini_api", analysis.engine_used)

    @patch("httpx.Client.post")
    def test_service_seamless_fallback_on_api_error(self, mock_post):
        # Simulate API returning HTTP 500 Internal Server Error
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal Server Error"
        mock_post.return_value = mock_resp

        service = DocumentUnderstandingService(
            llm_client=GeminiLLMClient(api_key="valid_key"),
            fallback_engine=FallbackUnderstandingEngine(),
        )
        analysis = service.analyze(MOCK_CONTRACT_TEXT, "lease.pdf", "PDF")

        # Must seamlessly degrade to fallback
        self.assertTrue(analysis.is_fallback)
        self.assertEqual(analysis.engine_used, "offline_heuristic")
        self.assertTrue(any("switched to offline" in w.lower() for w in analysis.warnings))
        self.assertIn("$4,500.00", " ".join(c.detail for c in analysis.critical_numbers_and_warnings))

    def test_service_with_phase1_failed_extraction_result(self):
        failed_extraction = ExtractionResult(
            filename="bad.pdf",
            method="digital_pdf",
            is_success=False,
            error_message="File appears corrupted.",
        )
        service = DocumentUnderstandingService()
        analysis = service.analyze(failed_extraction)
        self.assertTrue(analysis.is_fallback)
        self.assertIn("Extraction failure", analysis.executive_summary)
        self.assertEqual(analysis.word_count, 0)


class TestImprovedFallbackQuality(unittest.TestCase):
    def setUp(self):
        self.engine = FallbackUnderstandingEngine()
        self.samples_dir = __import__("pathlib").Path(__file__).resolve().parent.parent / "samples"

    def test_discharge_summary_quality(self):
        with open(self.samples_dir / "sample_discharge_summary.txt", "r", encoding="utf-8") as f:
            text = f.read()

        analysis = self.engine.analyze(text, "sample_discharge_summary.txt")

        # 1. Executive overview is informative and non-generic
        self.assertNotIn("[Offline Heuristic Summary]", analysis.executive_summary)
        self.assertIn("Robert M. Chen", analysis.executive_summary)
        self.assertIn("discharge", analysis.executive_summary.lower())
        self.assertIn("myocardial infarction", analysis.executive_summary.lower())

        # 2. Plain-English simplification contains actual instructions
        section_titles = [s.section_title for s in analysis.plain_english_breakdown]
        self.assertTrue(any("medication" in t.lower() for t in section_titles))
        simplified_all = " ".join(s.simplified_content for s in analysis.plain_english_breakdown)
        self.assertIn("Ticagrelor", simplified_all)
        self.assertIn("10 lbs", simplified_all)

        # 3. Numbers & warnings have context
        critical_details = " ".join(c.detail for c in analysis.critical_numbers_and_warnings)
        self.assertIn("90 mg Ticagrelor", critical_details)
        self.assertIn("55 bpm", critical_details)
        self.assertIn("Emergency", critical_details)

        # 4. Glossary has medical terms with definitions
        glossary_map = {g.term: g.definition for g in analysis.terminology_glossary}
        self.assertTrue(any("myocardial" in k.lower() or "stent" in k.lower() for k in glossary_map))

        # 5. Action checklist has practical steps
        actions_str = " ".join(analysis.actionable_takeaways)
        self.assertIn("Ticagrelor", actions_str)
        self.assertIn("Sarah Vance", actions_str)

    def test_receipt_quality(self):
        with open(self.samples_dir / "sample_contract.txt", "r", encoding="utf-8") as f:
            text = f.read()

        analysis = self.engine.analyze(text, "sample_contract.txt")
        self.assertNotIn("[Offline Heuristic Summary]", analysis.executive_summary)
        self.assertIn("$4,500.00", analysis.executive_summary)
        self.assertIn("Suite 400", analysis.executive_summary)

    @patch("httpx.Client.get")
    def test_gemini_verify_connection_success(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        client = GeminiLLMClient(api_key="mock_key", model_name="gemini-3.8-flash")
        is_ok, msg = client.verify_connection()
        self.assertTrue(is_ok)
        self.assertIn("gemini-3.8-flash", msg)

    @patch("httpx.Client.get")
    def test_gemini_verify_connection_retired_model(self, mock_get):
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_get.return_value = mock_resp

        client = GeminiLLMClient(api_key="mock_key", model_name="retired-model")
        is_ok, msg = client.verify_connection()
        self.assertFalse(is_ok)
        self.assertIn("retired", msg.lower())


if __name__ == "__main__":
    unittest.main()
