"""
Text Cleaning & Sanitization Module for DocuMind-AI.
Normalizes whitespace, fixes line wraps, strips control characters, and repairs broken hyphenations.
"""

import re
import unicodedata


def clean_text(raw_text: str) -> str:
    """
    Sanitize and clean raw text extracted from PDF or OCR.
    
    Steps:
    1. Normalize Unicode (NFC form).
    2. Convert CRLF / CR to standard LF line breaks.
    3. Remove unprintable control characters (except newline, tab).
    4. Repair hyphenated word breaks across lines (e.g., "agree-\n ment" -> "agreement").
    5. Clean excess horizontal whitespace on each line.
    6. Collapse 3+ consecutive newlines into 2 (clean paragraph separation).
    7. Strip leading/trailing whitespace.
    """
    if not raw_text:
        return ""

    # 1. Normalize Unicode characters
    text = unicodedata.normalize("NFC", raw_text)

    # 2. Normalize line endings to \n
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # 3. Strip null bytes and non-printable control characters (keep \t, \n)
    text = re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F\ufffd]", "", text)

    # 4. Repair hyphenated word breaks at line ends:
    # e.g., "re-\nsponsibility" or "re- \n sponsibility" or "obliga-\n\ntion" -> "responsibility" / "obligation"
    text = re.sub(r"(\b[a-zA-Z]+)-\s*\n+\s*([a-zA-Z]+\b)", r"\1\2", text)

    # 5. Normalize multiple horizontal spaces and tabs on individual lines
    lines = text.split("\n")
    cleaned_lines = []
    for line in lines:
        cleaned_line = re.sub(r"[ \t]+", " ", line).strip()
        cleaned_lines.append(cleaned_line)
    text = "\n".join(cleaned_lines)

    # 6. Collapse 3 or more consecutive newlines into two (standard paragraph break)
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()
