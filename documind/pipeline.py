"""
Unified Document Ingestion and Extraction Pipeline for DocuMind-AI.
"""

import os
from pathlib import Path
from typing import Tuple, Optional

from documind.config import MAX_FILE_SIZE_BYTES, SUPPORTED_EXTENSIONS
from documind.extractors.pdf_extractor import PDFExtractor
from documind.extractors.ocr_extractor import OCRExtractor
from documind.extractors.text_extractor import TextExtractor
from documind.models import ExtractionResult


class ExtractionPipeline:
    """
    Central Orchestrator for Document Extraction:
    - Validates file format and size.
    - Routes file to appropriate extractor (PDF, Text, OCR).
    - Returns structured ExtractionResult.
    """

    def __init__(
        self,
        pdf_extractor: Optional[PDFExtractor] = None,
        ocr_extractor: Optional[OCRExtractor] = None,
        text_extractor: Optional[TextExtractor] = None,
        max_file_size: int = MAX_FILE_SIZE_BYTES,
    ):
        self.ocr_extractor = ocr_extractor or OCRExtractor()
        self.pdf_extractor = pdf_extractor or PDFExtractor(ocr_extractor=self.ocr_extractor)
        self.text_extractor = text_extractor or TextExtractor()
        self.max_file_size = max_file_size

    def validate_file(self, file_bytes: bytes, filename: str) -> Tuple[bool, Optional[str]]:
        """
        Validate file size and extension.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not filename:
            return False, "Filename cannot be empty."

        ext = Path(filename).suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            allowed = ", ".join(SUPPORTED_EXTENSIONS.keys())
            return False, f"Format '{ext}' is not supported. Please upload one of: {allowed}"

        if len(file_bytes) > self.max_file_size:
            max_mb = self.max_file_size / (1024 * 1024)
            actual_mb = len(file_bytes) / (1024 * 1024)
            return False, f"File size ({actual_mb:.1f} MB) exceeds maximum allowed limit ({max_mb:.0f} MB)."

        return True, None

    def detect_document_type(self, file_bytes: bytes, filename: str) -> str:
        """Detect document type via magic header bytes with extension fallback."""
        ext = Path(filename).suffix.lower()

        # Check magic bytes
        if file_bytes.startswith(b"%PDF-"):
            return "pdf"
        if file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image"
        if file_bytes.startswith(b"\xff\xd8\xff"):
            return "image"
        if file_bytes.startswith(b"II*\x00") or file_bytes.startswith(b"MM\x00*"):
            return "image"
        if file_bytes.startswith(b"BM"):
            return "image"

        # Fallback to extension
        if ext == ".pdf":
            return "pdf"
        elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".bmp"):
            return "image"
        elif ext == ".txt":
            return "text"

        return "unknown"

    def process(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """
        Execute end-to-end extraction pipeline on uploaded file.
        
        Args:
            file_bytes: Raw bytes of the document.
            filename: Name of the uploaded file.
            
        Returns:
            ExtractionResult containing cleaned text and metadata.
        """
        # 1. Validation
        is_valid, error_msg = self.validate_file(file_bytes, filename)
        if not is_valid:
            return ExtractionResult(
                filename=filename,
                method="validation_error",
                raw_text="",
                clean_text="",
                is_success=False,
                error_message=error_msg,
            )

        # 2. Type Detection & Routing
        doc_type = self.detect_document_type(file_bytes, filename)

        if doc_type == "pdf":
            return self.pdf_extractor.extract(file_bytes, filename)
        elif doc_type == "image":
            return self.ocr_extractor.extract(file_bytes, filename)
        elif doc_type == "text":
            return self.text_extractor.extract(file_bytes, filename)
        else:
            return ExtractionResult(
                filename=filename,
                method="unknown",
                raw_text="",
                clean_text="",
                is_success=False,
                error_message=f"Unable to determine extractor for file '{filename}'.",
            )
