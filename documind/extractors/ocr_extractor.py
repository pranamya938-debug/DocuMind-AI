"""
OCR Extractor targeting Tesseract OCR Engine via subprocess.
"""

import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Union, Optional
from PIL import Image

from documind.config import TESSERACT_CMD, OCR_TIMEOUT_SECONDS
from documind.extractors.base import BaseExtractor
from documind.models import ExtractionResult, ExtractionMethod
from documind.preprocessor.image_cleaner import preprocess_image_for_ocr, load_image
from documind.preprocessor.text_cleaner import clean_text


class OCRExtractor(BaseExtractor):
    """Extractor for scanned documents and images using local Tesseract OCR."""

    def __init__(self, tesseract_cmd: Optional[str] = None, timeout_seconds: int = OCR_TIMEOUT_SECONDS):
        self.tesseract_cmd = tesseract_cmd or TESSERACT_CMD
        self.timeout_seconds = timeout_seconds

    def is_available(self) -> bool:
        """Check if Tesseract binary is executable."""
        cmd_path = Path(self.tesseract_cmd)
        return cmd_path.is_file() and os.access(self.tesseract_cmd, os.X_OK)

    def extract_from_image(self, image: Union[Image.Image, bytes], filename: str = "image.png") -> ExtractionResult:
        """Extract text directly from a PIL Image or image bytes."""
        start_time = time.perf_counter()
        warnings = []

        if not self.is_available():
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.OCR_TESSERACT.value,
                raw_text="",
                clean_text="",
                character_count=0,
                word_count=0,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=["Tesseract OCR binary not found or not executable."],
                is_success=False,
                error_message=f"Tesseract executable not found at '{self.tesseract_cmd}'.",
            )

        try:
            # 1. Preprocess image
            processed_img = preprocess_image_for_ocr(image)
        except Exception as e:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.OCR_TESSERACT.value,
                raw_text="",
                clean_text="",
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=[f"Failed to preprocess image: {str(e)}"],
                is_success=False,
                error_message=f"Image decoding error: {str(e)}",
            )

        # 2. Write preprocessed image to a temp file for Tesseract execution
        temp_img_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_file:
                temp_img_path = temp_file.name
                processed_img.save(temp_file, format="PNG")

            # 3. Execute Tesseract binary via subprocess
            # Command: tesseract <image_path> stdout -l eng
            cmd = [
                str(self.tesseract_cmd),
                temp_img_path,
                "stdout",
                "-l",
                "eng",
            ]

            process = subprocess.run(
                cmd,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )

            if process.returncode != 0:
                stderr_text = process.stderr.decode("utf-8", errors="replace")
                warnings.append(f"Tesseract returned non-zero code {process.returncode}: {stderr_text.strip()}")

            raw_output = process.stdout.decode("utf-8", errors="replace")

        except subprocess.TimeoutExpired:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.OCR_TESSERACT.value,
                raw_text="",
                clean_text="",
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=[f"OCR processing timed out after {self.timeout_seconds} seconds."],
                is_success=False,
                error_message="OCR processing timed out.",
            )
        except Exception as e:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.OCR_TESSERACT.value,
                raw_text="",
                clean_text="",
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=[f"Subprocess execution error: {str(e)}"],
                is_success=False,
                error_message=str(e),
            )
        finally:
            # Ephemeral scratch cleanup
            if temp_img_path and os.path.exists(temp_img_path):
                try:
                    os.remove(temp_img_path)
                except OSError:
                    pass

        # 4. Clean extracted text
        cleaned = clean_text(raw_output)
        duration_ms = (time.perf_counter() - start_time) * 1000

        if len(cleaned) < 5:
            warnings.append("No legible text detected in image. Ensure image is well-lit and in focus.")

        words = len(cleaned.split()) if cleaned else 0
        chars = len(cleaned)

        return ExtractionResult(
            filename=filename,
            method=ExtractionMethod.OCR_TESSERACT.value,
            raw_text=raw_output,
            clean_text=cleaned,
            character_count=chars,
            word_count=words,
            page_count=1,
            processing_time_ms=round(duration_ms, 2),
            metadata={"ocr_engine": "Tesseract 5.x", "image_size": processed_img.size},
            warnings=warnings,
            is_success=True,
        )

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """Extract text from image bytes."""
        if not file_bytes:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.OCR_TESSERACT.value,
                raw_text="",
                clean_text="",
                character_count=0,
                word_count=0,
                page_count=1,
                processing_time_ms=0.0,
                warnings=["Uploaded image file is empty."],
                is_success=True,
            )
        return self.extract_from_image(file_bytes, filename=filename)
