"""
Unit and Integration Tests for ExtractionPipeline.
"""

import unittest
from documind.pipeline import ExtractionPipeline
from tests.test_extractors import create_synthetic_image, create_synthetic_pdf


class TestExtractionPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = ExtractionPipeline()

    def test_validation_unsupported_format(self):
        is_valid, err = self.pipeline.validate_file(b"archive bytes", "file.zip")
        self.assertFalse(is_valid)
        self.assertIn("not supported", err.lower())

    def test_validation_file_size_exceeded(self):
        pipeline_tiny = ExtractionPipeline(max_file_size=100)
        is_valid, err = pipeline_tiny.validate_file(b"a" * 200, "large.txt")
        self.assertFalse(is_valid)
        self.assertIn("exceeds", err.lower())

    def test_process_txt_file(self):
        text_data = b"This is a contract clause regarding termination notice within 30 days."
        res = self.pipeline.process(text_data, "contract.txt")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "plain_text")
        self.assertIn("30 days", res.clean_text)
        self.assertGreater(res.word_count, 0)
        self.assertGreater(res.character_count, 0)
        self.assertGreaterEqual(res.processing_time_ms, 0)

    def test_process_pdf_file(self):
        pdf_bytes = create_synthetic_pdf("Official Notice of Monthly Rent Increase to $2400 per month starting next quarter.")
        res = self.pipeline.process(pdf_bytes, "rent_notice.pdf")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "digital_pdf")
        self.assertIn("$2400", res.clean_text)

    def test_process_image_file(self):
        img_bytes = create_synthetic_image("RECEIPT TOTAL USD 99")
        res = self.pipeline.process(img_bytes, "receipt.png")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "ocr_tesseract")
        self.assertIn("TOTAL", res.clean_text.upper())

    def test_process_rejected_file_returns_failure_result(self):
        res = self.pipeline.process(b"malicious.exe", "payload.exe")
        self.assertFalse(res.is_success)
        self.assertIn("not supported", res.error_message.lower())


if __name__ == "__main__":
    unittest.main()
