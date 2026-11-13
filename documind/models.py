"""
Data Models & Pydantic Schemas for DocuMind-AI.
"""

from enum import Enum
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    DIGITAL_PDF = "digital_pdf"
    SCANNED_PDF_OCR = "scanned_pdf_ocr"
    OCR_TESSERACT = "ocr_tesseract"
    PLAIN_TEXT = "plain_text"


class DocumentMetadata(BaseModel):
    filename: str
    file_size_bytes: int
    mime_type: str
    page_count: Optional[int] = None
    detected_type: str


class ExtractionResult(BaseModel):
    filename: str
    method: str
    raw_text: str = ""
    clean_text: str = ""
    character_count: int = 0
    word_count: int = 0
    page_count: Optional[int] = 1
    processing_time_ms: float = 0.0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    is_success: bool = True
    error_message: Optional[str] = None


class PlainEnglishSection(BaseModel):
    section_title: str
    simplified_content: str


class CriticalNumberOrWarning(BaseModel):
    type: str = Field(description="e.g. Financial, Deadline, Warning, Condition, Percentage")
    detail: str


class GlossaryItem(BaseModel):
    term: str
    definition: str


class DocuMindAnalysis(BaseModel):
    document_name: str
    document_type: str
    word_count: int
    executive_summary: str
    plain_english_breakdown: List[PlainEnglishSection] = Field(default_factory=list)
    critical_numbers_and_warnings: List[CriticalNumberOrWarning] = Field(default_factory=list)
    terminology_glossary: List[GlossaryItem] = Field(default_factory=list)
    actionable_takeaways: List[str] = Field(default_factory=list)
    extracted_text_snippet: str = ""
    engine_used: str = "offline"
    is_fallback: bool = False
    warnings: List[str] = Field(default_factory=list)
    processing_timestamp: Optional[str] = None
