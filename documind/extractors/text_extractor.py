"""
Plain Text Document Extractor.
"""

import time
from typing import List
from documind.extractors.base import BaseExtractor
from documind.models import ExtractionResult, ExtractionMethod
from documind.preprocessor.text_cleaner import clean_text


class TextExtractor(BaseExtractor):
    """Extractor for plain text documents (.txt) with robust encoding fallback."""

    ENCODINGS: List[str] = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]

    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        start_time = time.perf_counter()
        warnings = []

        if not file_bytes:
            return ExtractionResult(
                filename=filename,
                method=ExtractionMethod.PLAIN_TEXT.value,
                raw_text="",
                clean_text="",
                character_count=0,
                word_count=0,
                page_count=1,
                processing_time_ms=(time.perf_counter() - start_time) * 1000,
                warnings=["Uploaded text file is empty."],
                is_success=True,
            )

        decoded_text = None
        used_encoding = None

        for enc in self.ENCODINGS:
            try:
                decoded_text = file_bytes.decode(enc)
                used_encoding = enc
                break
            except UnicodeDecodeError:
                continue

        if decoded_text is None:
            # Fallback with replacement characters
            decoded_text = file_bytes.decode("utf-8", errors="replace")
            used_encoding = "utf-8-replace"
            warnings.append("Text contained non-standard characters replaced during decoding.")

        cleaned = clean_text(decoded_text)
        duration_ms = (time.perf_counter() - start_time) * 1000

        words = len(cleaned.split()) if cleaned else 0
        chars = len(cleaned)

        return ExtractionResult(
            filename=filename,
            method=ExtractionMethod.PLAIN_TEXT.value,
            raw_text=decoded_text,
            clean_text=cleaned,
            character_count=chars,
            word_count=words,
            page_count=1,
            processing_time_ms=round(duration_ms, 2),
            metadata={"encoding": used_encoding, "file_size_bytes": len(file_bytes)},
            warnings=warnings,
            is_success=True,
        )
