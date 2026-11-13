"""
Abstract Base Extractor for DocuMind-AI.
"""

from abc import ABC, abstractmethod
from documind.models import ExtractionResult


class BaseExtractor(ABC):
    """Abstract base class that all document extractors must inherit from."""

    @abstractmethod
    def extract(self, file_bytes: bytes, filename: str) -> ExtractionResult:
        """
        Extract text from raw file bytes.
        
        Args:
            file_bytes: Raw bytes of the uploaded file.
            filename: Original name of the uploaded file.
            
        Returns:
            ExtractionResult containing raw text, clean text, metadata, and status.
        """
        pass
