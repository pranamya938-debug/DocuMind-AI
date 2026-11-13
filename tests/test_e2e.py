"""
End-to-End (E2E) Integration and Workflow Test Suite for DocuMind-AI.
Validates the complete pipeline: File Ingestion -> Extraction/OCR -> AI Understanding -> Export Serialization.
"""

import json
from pathlib import Path
import unittest

from app import build_markdown_report, build_json_report, load_sample_file
from documind.ai.service import DocumentUnderstandingService
from documind.models import DocuMindAnalysis, ExtractionResult
from documind.pipeline import ExtractionPipeline
from tests.test_extractors import create_synthetic_pdf


class TestEndToEndWorkflow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pipeline = ExtractionPipeline()
        cls.understanding_service = DocumentUnderstandingService()
        cls.samples_dir = Path(__file__).resolve().parent.parent / "samples"

    def test_e2e_contract_workflow(self):
        """E2E Test: Commercial Lease Agreement plain text document."""
        contract_path = self.samples_dir / "sample_contract.txt"
        self.assertTrue(contract_path.is_file(), "sample_contract.txt must exist.")

        with open(contract_path, "rb") as f:
            file_bytes = f.read()

        # 1. Pipeline Extraction
        extract_res = self.pipeline.process(file_bytes, "sample_contract.txt")
        self.assertTrue(extract_res.is_success)
        self.assertEqual(extract_res.method, "plain_text")
        self.assertGreater(extract_res.word_count, 300)
        self.assertIn("$4,500.00", extract_res.clean_text)
        self.assertIn("$9,000.00", extract_res.clean_text)

        # 2. Cognitive Understanding Service
        analysis = self.understanding_service.analyze(extract_res)
        self.assertIsInstance(analysis, DocuMindAnalysis)
        self.assertEqual(analysis.document_name, "sample_contract.txt")

        # Verify all 5 sections
        self.assertTrue(len(analysis.executive_summary) > 20)
        self.assertGreater(len(analysis.plain_english_breakdown), 0)
        self.assertGreater(len(analysis.critical_numbers_and_warnings), 0)
        self.assertGreater(len(analysis.terminology_glossary), 0)
        self.assertGreater(len(analysis.actionable_takeaways), 0)

        # Verify entity extraction fidelity
        critical_str = " ".join(c.detail for c in analysis.critical_numbers_and_warnings)
        self.assertIn("$4,500.00", critical_str)
        self.assertIn("$9,000.00", critical_str)
        self.assertIn("5%", critical_str)

        # 3. Export Generation
        md_export = build_markdown_report(analysis, extract_res)
        self.assertIn("# DocuMind-AI Analysis Report", md_export)
        self.assertIn("## 1. Executive Overview", md_export)
        self.assertIn("$4,500.00", md_export)

        json_export = build_json_report(analysis)
        data = json.loads(json_export)
        self.assertEqual(data["document_name"], "sample_contract.txt")
        self.assertGreater(len(data["critical_numbers_and_warnings"]), 0)

    def test_e2e_discharge_summary_workflow(self):
        """E2E Test: Hospital Discharge Summary document."""
        discharge_path = self.samples_dir / "sample_discharge_summary.txt"
        self.assertTrue(discharge_path.is_file(), "sample_discharge_summary.txt must exist.")

        with open(discharge_path, "rb") as f:
            file_bytes = f.read()

        extract_res = self.pipeline.process(file_bytes, "sample_discharge_summary.txt")
        self.assertTrue(extract_res.is_success)
        self.assertEqual(extract_res.method, "plain_text")
        self.assertIn("Ticagrelor", extract_res.clean_text)

        analysis = self.understanding_service.analyze(extract_res)
        self.assertIsInstance(analysis, DocuMindAnalysis)

        # Check medical warning and obligation capture
        critical_types = [c.type for c in analysis.critical_numbers_and_warnings]
        self.assertTrue("Warning" in critical_types or "Obligation" in critical_types or "Deadline" in critical_types)

        # Check medical jargon glossary matching
        glossary_terms = [g.term.lower() for g in analysis.terminology_glossary]
        self.assertTrue(any("infarction" in t or "stent" in t or "ticagrelor" in t for t in glossary_terms))

        md_export = build_markdown_report(analysis, extract_res)
        self.assertIn("HOSPITAL DISCHARGE", md_export.upper())

    def test_e2e_receipt_ocr_workflow(self):
        """E2E Test: Clinic Receipt Image via Pillow & Tesseract OCR."""
        receipt_path = self.samples_dir / "sample_receipt.png"
        self.assertTrue(receipt_path.is_file(), "sample_receipt.png must exist.")

        with open(receipt_path, "rb") as f:
            file_bytes = f.read()

        extract_res = self.pipeline.process(file_bytes, "sample_receipt.png")
        self.assertTrue(extract_res.is_success)
        self.assertEqual(extract_res.method, "ocr_tesseract")
        self.assertIn("METRO", extract_res.clean_text.upper())
        self.assertLess(extract_res.processing_time_ms, 3000.0, "OCR should finish within 3 seconds.")

        analysis = self.understanding_service.analyze(extract_res)
        self.assertIsInstance(analysis, DocuMindAnalysis)
        self.assertEqual(analysis.document_type, "ocr_tesseract")

        json_export = build_json_report(analysis)
        self.assertIn("ocr_tesseract", json_export)

    def test_e2e_synthetic_digital_pdf_workflow(self):
        """E2E Test: Digital PDF creation, parsing, analysis, and report generation."""
        pdf_bytes = create_synthetic_pdf(
            "Executive Consulting Agreement: Retainer fee is $15,000.00 payable upon contract signing."
        )
        extract_res = self.pipeline.process(pdf_bytes, "consulting.pdf")
        self.assertTrue(extract_res.is_success)
        self.assertEqual(extract_res.method, "digital_pdf")
        self.assertIn("$15,000.00", extract_res.clean_text)

        analysis = self.understanding_service.analyze(extract_res)
        self.assertIn("$15,000.00", " ".join(c.detail for c in analysis.critical_numbers_and_warnings))

    def test_e2e_empty_document_handling(self):
        """E2E Test: Completely empty document."""
        extract_res = self.pipeline.process(b"", "empty.txt")
        self.assertTrue(extract_res.is_success)
        self.assertEqual(extract_res.character_count, 0)

        analysis = self.understanding_service.analyze(extract_res)
        self.assertEqual(analysis.word_count, 0)
        self.assertIn("no readable text", analysis.executive_summary.lower())

    def test_e2e_unsupported_format_handling(self):
        """E2E Test: Unsupported format rejection."""
        extract_res = self.pipeline.process(b"PK0304zipbytes", "archive.zip")
        self.assertFalse(extract_res.is_success)
        self.assertIn("not supported", extract_res.error_message.lower())

        analysis = self.understanding_service.analyze(extract_res)
        self.assertIn("Extraction failure", analysis.executive_summary)

    def test_e2e_corrupted_pdf_handling(self):
        """E2E Test: Corrupted PDF file."""
        extract_res = self.pipeline.process(b"%PDF-1.4 truncated corrupted bytes", "damaged.pdf")
        self.assertFalse(extract_res.is_success)
        self.assertIn("corrupted", extract_res.error_message.lower())

        analysis = self.understanding_service.analyze(extract_res)
        self.assertIn("Extraction failure", analysis.executive_summary)

    def test_e2e_missing_sample_file_returns_none(self):
        """E2E Test: Loading non-existent sample file."""
        data = load_sample_file("non_existent_doc_123.pdf")
        self.assertIsNone(data)


if __name__ == "__main__":
    unittest.main()
