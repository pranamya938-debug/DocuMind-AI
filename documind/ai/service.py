"""
Unified Document Understanding Service for DocuMind-AI.
Orchestrates online Gemini LLM analysis with seamless offline heuristic fallback.
"""

from datetime import datetime, timezone
from typing import Optional, Union

from documind.ai.fallback_engine import FallbackUnderstandingEngine
from documind.ai.llm_client import GeminiLLMClient, LLMClientError
from documind.models import DocuMindAnalysis, ExtractionResult


class DocumentUnderstandingService:
    """
    Unified cognitive service:
    - Ingests ExtractionResult or raw text.
    - Routes to Gemini LLM if configured and online.
    - Seamlessly falls back to deterministic rule-based engine if unconfigured or on failure.
    - Guarantees 100% availability with standardized DocuMindAnalysis output.
    """

    def __init__(
        self,
        llm_client: Optional[GeminiLLMClient] = None,
        fallback_engine: Optional[FallbackUnderstandingEngine] = None,
    ):
        self.llm_client = llm_client or GeminiLLMClient()
        self.fallback_engine = fallback_engine or FallbackUnderstandingEngine()

    def analyze(
        self,
        target: Union[ExtractionResult, str],
        filename: str = "document.txt",
        document_type: str = "Document",
    ) -> DocuMindAnalysis:
        """
        Analyze extracted document content.
        
        Args:
            target: ExtractionResult from Phase 1, or raw text string.
            filename: Document filename (used if target is a string).
            document_type: Document format/type description.
            
        Returns:
            DocuMindAnalysis structured analysis object.
        """
        if isinstance(target, ExtractionResult):
            filename = target.filename
            document_type = target.method
            text = target.clean_text or target.raw_text

            # If extraction failed
            if not target.is_success:
                return DocuMindAnalysis(
                    document_name=filename,
                    document_type=document_type,
                    word_count=0,
                    executive_summary=f"Extraction failure: {target.error_message or 'Unable to read file.'}",
                    plain_english_breakdown=[],
                    critical_numbers_and_warnings=[],
                    terminology_glossary=[],
                    actionable_takeaways=["Please check the uploaded file for corruption or unsupported formatting."],
                    extracted_text_snippet="",
                    engine_used="offline_heuristic",
                    is_fallback=True,
                    warnings=target.warnings + [f"Extraction failed: {target.error_message}"],
                    processing_timestamp=datetime.now(timezone.utc).isoformat(),
                )
        else:
            text = str(target)

        # Attempt Online LLM Analysis if configured
        if self.llm_client.is_configured():
            try:
                analysis = self.llm_client.analyze_document(
                    document_text=text,
                    document_name=filename,
                    document_type=document_type,
                )
                return analysis
            except LLMClientError as e:
                # Log graceful degradation notice and fall through to deterministic fallback
                fallback_analysis = self.fallback_engine.analyze(
                    document_text=text,
                    document_name=filename,
                    document_type=document_type,
                )
                fallback_analysis.warnings.insert(
                    0,
                    f"Gemini API unavailable ({str(e)}). Switched to offline heuristic engine."
                )
                return fallback_analysis
            except Exception as e:
                fallback_analysis = self.fallback_engine.analyze(
                    document_text=text,
                    document_name=filename,
                    document_type=document_type,
                )
                fallback_analysis.warnings.insert(
                    0,
                    f"Unexpected AI error ({str(e)}). Switched to offline heuristic engine."
                )
                return fallback_analysis

        # Offline Mode (No API Key configured)
        return self.fallback_engine.analyze(
            document_text=text,
            document_name=filename,
            document_type=document_type,
        )
