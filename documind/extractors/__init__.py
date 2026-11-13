"""
Extraction subsystem containing extractors for PDF, Plain Text, and OCR.
"""

from documind.extractors.base import BaseExtractor
from documind.extractors.text_extractor import TextExtractor
from documind.extractors.pdf_extractor import PDFExtractor
from documind.extractors.ocr_extractor import OCRExtractor

__all__ = ["BaseExtractor", "TextExtractor", "PDFExtractor", "OCRExtractor"]
