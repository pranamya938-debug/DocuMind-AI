"""
Unit and Integration Tests for DocuMind-AI Streamlit Web Application Components.
Verifies UI helper functions, report builders, sample file loading, and module integrity.
"""

import json
import unittest
from pathlib import Path

from app import build_markdown_report, build_json_report, load_sample_file
from documind.models import (
    DocuMindAnalysis,
    PlainEnglishSection,
    CriticalNumberOrWarning,
    GlossaryItem,
    ExtractionResult,
)


class TestUIComponents(unittest.TestCase):
    def setUp(self):
        self.sample_analysis = DocuMindAnalysis(
            document_name="test_lease.pdf",
            document_type="digital_pdf",
            word_count=500,
            executive_summary="This is an executive summary of the commercial lease.",
            plain_english_breakdown=[
                PlainEnglishSection(
                    section_title="Rent Terms",
                    simplified_content="You must pay $4,500.00 each month.",
                )
            ],
            critical_numbers_and_warnings=[
                CriticalNumberOrWarning(type="Financial", detail="$4,500.00 monthly rent"),
                CriticalNumberOrWarning(type="Warning", detail="5% late fee penalty applies"),
            ],
            terminology_glossary=[
                GlossaryItem(term="Indemnify", definition="To protect from legal loss.")
            ],
            actionable_takeaways=[
                "Pay rent on the 1st of the month.",
                "Deliver certificate of insurance.",
            ],
            extracted_text_snippet="Commercial lease agreement text snippet...",
            engine_used="offline_heuristic",
            is_fallback=True,
        )

        self.sample_extraction = ExtractionResult(
            filename="test_lease.pdf",
            method="digital_pdf",
            clean_text="Clean extracted text for inspection.",
            character_count=35,
            word_count=5,
            processing_time_ms=12.5,
        )

    def test_build_markdown_report(self):
        md = build_markdown_report(self.sample_analysis, self.sample_extraction)
        self.assertIn("# DocuMind-AI Analysis Report: test_lease.pdf", md)
        self.assertIn("## 1. Executive Overview", md)
        self.assertIn("## 2. Plain-English Simplification", md)
        self.assertIn("## 3. Critical Numbers, Conditions & Warnings", md)
        self.assertIn("## 4. Jargon Buster Glossary", md)
        self.assertIn("## 5. Actionable Takeaways & Checklist", md)
        self.assertIn("## 6. Source Text Excerpt", md)
        self.assertIn("$4,500.00", md)
        self.assertIn("Indemnify", md)
        self.assertIn("Disclaimer:", md)

    def test_build_json_report(self):
        json_str = build_json_report(self.sample_analysis)
        data = json.loads(json_str)
        self.assertEqual(data["document_name"], "test_lease.pdf")
        self.assertEqual(data["word_count"], 500)
        self.assertEqual(len(data["plain_english_breakdown"]), 1)
        self.assertEqual(len(data["critical_numbers_and_warnings"]), 2)
        self.assertEqual(data["terminology_glossary"][0]["term"], "Indemnify")

    def test_load_sample_files(self):
        contract_bytes = load_sample_file("sample_contract.txt")
        self.assertIsNotNone(contract_bytes)
        self.assertGreater(len(contract_bytes), 100)

        medical_bytes = load_sample_file("sample_discharge_summary.txt")
        self.assertIsNotNone(medical_bytes)
        self.assertGreater(len(medical_bytes), 100)

        receipt_bytes = load_sample_file("sample_receipt.png")
        self.assertIsNotNone(receipt_bytes)
        self.assertGreater(len(receipt_bytes), 100)

    def test_load_nonexistent_sample_returns_none(self):
        result = load_sample_file("nonexistent_file.xyz")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
