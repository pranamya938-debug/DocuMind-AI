"""
PDF Extractor using pypdf for digital text and Tesseract OCR for scanned pages.
"""

import io
import time
from typing import List, Optional
import pypdf
from pypdf.errors import PdfReadError

from documind.extractors.base import BaseExtractor
from documind.extractors.ocr_extractor import OCRExtractor
from documind.models import ExtractionResult, ExtractionMethod
from documind.preprocessor.text_cleaner import clean_text


class PDFExtractor(BaseExtractor):
    """
    Hybrid PDF Extractor:
    - Extracts native digital text layers using pypdf.
    - If a page has < 50 characters (scanned or image-only), falls back to OCR on embedded page images.
    """

    DIGITAL_TEXT_THRESHOLD: int = 50

    def __init__(self, ocr_extractor: Optional[OCRExtractor] = None):
        self.ocr_extractor = ocr_extractor or OCRExtractor()

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        start_time = time.perf_counter()
        warnings: List[str] = []

        if not file_bytes:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.DIGITAL_PDF.value,
                raw_text="",
                clean_text="",
                character_count=0,
                word_count=0,
                page_count=0,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=["Uploaded PDF file is empty."],
                is_success=True,
            )

        try:
            reader = pypdf.PdfReader(io.BytesIO(file_bytes))
        except PdfReadError as e:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.DIGITAL_PDF.value,
                raw_text="",
                clean_text="",
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=["PDF appears corrupted or unreadable."],
                is_success=False,
                error_message=f"File appears corrupted or unreadable: {str(e)}",
            )
        except Exception as e:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.DIGITAL_PDF.value,
                raw_text="",
                clean_text="",
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=[f"Failed to parse PDF: {str(e)}"],
                is_success=False,
                error_message=f"PDF parsing error: {str(e)}",
            )

        # Handle password-protected PDFs with blank password attempt
        if reader.is_encrypted:
            try:
                decrypted = reader.decrypt("")
                if not decrypted:
                    return ExtractionResult(
                        filename=filename,
                        method=ExtractionMethod.DIGITAL_PDF.value,
                        raw_text="",
                        clean_text="",
                        processing_time_ms=(time.perf_counter() - start_time) * 1000,
                        warnings=["PDF is password-protected."],
                        is_success=False,
                        error_message="Document is encrypted and requires a password to open.",
                    )
            except Exception as e:
                return ExtractionResult(
                    filename=filename,
                    method=ExtractionMethod.DIGITAL_PDF.value,
                    raw_text="",
                    clean_text="",
                    processing_time_ms=(time.perf_counter() - start_time) * 1000,
                    warnings=["Failed to decrypt PDF."],
                    is_success=False,
                    error_message=f"Decryption error: {str(e)}",
                )

        total_pages = len(reader.pages)
        page_texts: List[str] = []
        scanned_pages_count = 0

        for page_idx, page in enumerate(reader.pages, start=1):
            extracted_text = ""
            try:
                extracted_text = page.extract_text() or ""
            except Exception as e:
                warnings.append(f"Page {page_idx}: text extraction warning: {str(e)}")

            # Check if page has sufficient digital text layer
            if len(extracted_text.strip()) >= self.DIGITAL_TEXT_THRESHOLD:
                page_texts.append(extracted_text)
            else:
                # Page has minimal or no text layer; check if it has embedded scanned images
                has_images = hasattr(page, "images") and bool(page.images)
                ocr_text = ""

                if has_images and self.ocr_extractor.is_available():
                    for img_obj in page.images:
                        try:
                            img_res = self.ocr_extractor.extract_from_image(
                                img_obj.data,
                                filename=f"{filename}_p{page_idx}_{img_obj.name}"
                            )
                            if img_res.clean_text:
                                ocr_text += "\n" + img_res.clean_text
                        except Exception as img_err:
                            warnings.append(f"Page {page_idx} OCR error on image {img_obj.name}: {str(img_err)}")

                if ocr_text.strip():
                    page_texts.append(ocr_text.strip())
                    scanned_pages_count += 1
                    warnings.append(f"Page {page_idx} extracted via OCR fallback.")
                elif extracted_text.strip():
                    # Native text was short but present with no OCR alternative
                    page_texts.append(extracted_text.strip())
                else:
                    warnings.append(f"Page {page_idx} had no extractable text or legible images.")

        combined_raw = "\n\n".join(page_texts)
        cleaned = clean_text(combined_raw)
        duration_ms = (time.perf_counter() - start_time) * 1000

        method = (
            ExtractionMethod.SCANNED_PDF_OCR.value
            if scanned_pages_count > 0 and (scanned_pages_count == total_pages)
            else ExtractionMethod.DIGITAL_PDF.value
        )

        words = len(cleaned.split()) if cleaned else 0
        chars = len(cleaned)

        if chars == 0:
            warnings.append("Document yielded zero characters. The file may be blank or composed of unreadable scans.")

        return ExtractionResult(
            filename=filename,
            method=method,
            raw_text=combined_raw,
            clean_text=cleaned,
            character_count=chars,
            word_count=words,
            page_count=total_pages,
            processing_time_ms=round(duration_ms, 2),
            metadata={
                "total_pages": total_pages,
                "scanned_pages_detected": scanned_pages_count,
            },
            warnings=warnings,
            is_success=True,
        )
