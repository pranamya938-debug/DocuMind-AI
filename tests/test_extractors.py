"""
Unit tests for DocuMind-AI extractors and preprocessors.
"""

import io
import unittest
from PIL import Image, ImageDraw, ImageFont

from documind.extractors.text_extractor import TextExtractor
from documind.extractors.ocr_extractor import OCRExtractor
from documind.extractors.pdf_extractor import PDFExtractor
from documind.preprocessor.text_cleaner import clean_text
from documind.preprocessor.image_cleaner import preprocess_image_for_ocr


def create_synthetic_image(text: str) -> bytes:
    """Generate a clean synthetic PNG image containing black text on white background."""
    img = Image.new("RGB", (600, 150), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Use default bitmap font
    draw.text((20, 50), text, fill=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def create_synthetic_pdf(text: str) -> bytes:
    """Create a minimal valid digital PDF with an embedded text stream and valid xref table."""
    stream_content = f"BT /F1 14 Tf 50 700 Td ({text}) Tj ET".encode("latin-1")
    pdf = bytearray()
    pdf.extend(b"%PDF-1.4\n")
    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>\nendobj\n"
    )
    obj4 = b"4 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    obj5 = (
        b"5 0 obj\n<< /Length " + str(len(stream_content)).encode() + b" >>\nstream\n"
        + stream_content + b"\nendstream\nendobj\n"
    )

    offsets = [0]
    pos = len(pdf)
    for obj in [obj1, obj2, obj3, obj4, obj5]:
        offsets.append(pos)
        pdf.extend(obj)
        pos = len(pdf)

    xref_pos = len(pdf)
    pdf.extend(b"xref\n0 6\n0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode())

    pdf.extend(b"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n" + str(xref_pos).encode() + b"\n%%EOF\n")
    return bytes(pdf)


class TestTextCleaner(unittest.TestCase):
    def test_normalize_whitespace_and_newlines(self):
        messy = "Hello   world!  \r\n\r\n\r\nThis   is   a   test.\r\n"
        cleaned = clean_text(messy)
        self.assertEqual(cleaned, "Hello world!\n\nThis is a test.")

    def test_strip_control_characters(self):
        text_with_ctrl = "Valid Text\x00\x07\x08With Null And Bell"
        cleaned = clean_text(text_with_ctrl)
        self.assertEqual(cleaned, "Valid TextWith Null And Bell")

    def test_repair_hyphenation(self):
        broken = "This agree-\n ment outlines our responsi-\n bilities."
        cleaned = clean_text(broken)
        self.assertIn("agreement", cleaned)
        self.assertIn("responsibilities", cleaned)


class TestImageCleaner(unittest.TestCase):
    def test_grayscale_and_rescaling(self):
        # Create small color image
        small_color = Image.new("RGBA", (100, 50), color=(255, 0, 0, 128))
        preprocessed = preprocess_image_for_ocr(small_color, min_dimension=400)

        self.assertEqual(preprocessed.mode, "L")
        self.assertGreaterEqual(max(preprocessed.size), 400)


class TestTextExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = TextExtractor()

    def test_extract_utf8(self):
        content = "DocuMind-AI text extraction test.\nFinancial obligation: $5,000 due May 1st."
        res = self.extractor.extract(content.encode("utf-8"), "test.txt")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "plain_text")
        self.assertIn("$5,000", res.clean_text)
        self.assertGreater(res.word_count, 5)

    def test_extract_latin1(self):
        content = "Café résumé payment: £120."
        res = self.extractor.extract(content.encode("latin-1"), "latin.txt")
        self.assertTrue(res.is_success)
        self.assertIn("Café", res.clean_text)

    def test_extract_cp1252(self):
        content = "Executive fee: €500."
        res = self.extractor.extract(content.encode("cp1252"), "cp1252.txt")
        self.assertTrue(res.is_success)
        self.assertIn("€500", res.clean_text)

    def test_extract_empty(self):
        res = self.extractor.extract(b"", "empty.txt")
        self.assertTrue(res.is_success)
        self.assertEqual(res.character_count, 0)
        self.assertIn("empty", res.warnings[0].lower())


class TestOCRExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = OCRExtractor()

    def test_tesseract_availability(self):
        self.assertTrue(self.extractor.is_available(), "Tesseract binary should be available.")

    def test_ocr_synthetic_image(self):
        img_bytes = create_synthetic_image("DOCUMIND TEST OCR")
        res = self.extractor.extract(img_bytes, "ocr_test.png")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "ocr_tesseract")
        # Check that OCR identified key characters
        self.assertIn("DOCUMIND", res.clean_text.upper())

    def test_ocr_blank_image(self):
        blank_img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        buf = io.BytesIO()
        blank_img.save(buf, format="PNG")
        res = self.extractor.extract(buf.getvalue(), "blank.png")
        self.assertTrue(res.is_success)
        self.assertTrue(any("legible" in w.lower() for w in res.warnings))


class TestPDFExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = PDFExtractor()

    def test_pdf_digital_extraction(self):
        pdf_bytes = create_synthetic_pdf("Commercial Real Estate Lease Agreement between Lessor and Lessee for Suite 400.")
        res = self.extractor.extract(pdf_bytes, "lease.pdf")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "digital_pdf")
        self.assertIn("Lease Agreement", res.clean_text)
        self.assertEqual(res.page_count, 1)

    def test_pdf_scanned_image_ocr_fallback(self):
        # Create a scanned PDF by exporting a Pillow synthetic image directly to PDF format
        img = Image.new("RGB", (450, 100), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((20, 40), "SCANNED INVOICE 999", fill=(0, 0, 0))
        buf = io.BytesIO()
        img.save(buf, format="PDF")
        pdf_bytes = buf.getvalue()

        res = self.extractor.extract(pdf_bytes, "scanned_doc.pdf")
        self.assertTrue(res.is_success)
        self.assertEqual(res.method, "scanned_pdf_ocr")
        self.assertIn("SCANNED", res.clean_text.upper())
        self.assertIn("999", res.clean_text)
        self.assertTrue(any("ocr fallback" in w.lower() for w in res.warnings))

    def test_pdf_corrupted_bytes(self):
        res = self.extractor.extract(b"%PDF-1.4 damaged header bad bytes", "corrupt.pdf")
        self.assertFalse(res.is_success)
        self.assertIn("corrupted", res.error_message.lower())


if __name__ == "__main__":
    unittest.main()
