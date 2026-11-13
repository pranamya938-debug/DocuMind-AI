"""
Gemini API Client for DocuMind-AI using HTTPX.
Enforces structured JSON output and validates responses against Pydantic models.
"""

import json
import os
import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx

from documind.config import GEMINI_API_KEY, GEMINI_MODEL
from documind.models import DocuMindAnalysis, PlainEnglishSection, CriticalNumberOrWarning, GlossaryItem
from documind.ai.prompts import SYSTEM_INSTRUCTION, build_analysis_prompt


class LLMClientError(Exception):
    """Custom exception raised for LLM client communication or validation errors."""
    pass


class GeminiLLMClient:
    """
    Client for Google Gemini REST API.
    Interacts with Gemini via HTTPX, requesting structured JSON output.
    """

    DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout_seconds: float = 25.0,
        base_url: Optional[str] = None,
    ):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
        self.model_name = model_name or os.environ.get("GEMINI_MODEL", GEMINI_MODEL)
        self.timeout_seconds = timeout_seconds
        self.base_url = (base_url or self.DEFAULT_BASE_URL).rstrip("/")

    def is_configured(self) -> bool:
        """Return True if an API key is present."""
        return bool(self.api_key and self.api_key.strip())

    def verify_connection(self) -> tuple[bool, str]:
        """
        Verify whether the API key and model endpoint are reachable.
        Uses a lightweight metadata query that consumes zero token quota.
        """
        if not self.is_configured():
            return False, "Gemini API key is not configured."

        endpoint = f"{self.base_url}/models/{self.model_name}"
        params = {"key": self.api_key}

        try:
            with httpx.Client(timeout=8.0) as client:
                resp = client.get(endpoint, params=params)
                if resp.status_code == 200:
                    return True, f"Verified connection to model '{self.model_name}'."
                elif resp.status_code == 404:
                    return False, f"Model '{self.model_name}' was not found or has been retired by Google. Please select 'gemini-3.8-flash'."
                elif resp.status_code in (401, 403):
                    return False, "Invalid or unauthorized Gemini API key. Please check your credentials."
                elif resp.status_code == 429:
                    return False, "Gemini API quota or rate limit exceeded."
                else:
                    return False, f"Gemini API returned status HTTP {resp.status_code}."
        except httpx.TimeoutException:
            return False, "Connection timed out while contacting Gemini API."
        except Exception as e:
            return False, f"Network error contacting Gemini API: {str(e)}"

    def _clean_json_response(self, text: str) -> str:
        """Strip markdown fences (```json ... ```) or conversational padding."""
        cleaned = text.strip()
        # Remove opening ```json or ```
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned, flags=re.IGNORECASE)
        # Remove closing ```
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        return cleaned.strip()

    def analyze_document(
        self,
        document_text: str,
        document_name: str,
        document_type: str = "Document",
    ) -> DocuMindAnalysis:
        """
        Send document text to Gemini API and return a validated DocuMindAnalysis object.
        
        Raises:
            LLMClientError: On network failures, HTTP errors, timeouts, or JSON parsing issues.
        """
        if not self.is_configured():
            raise LLMClientError("Gemini API key is not configured.")

        if not document_text or not document_text.strip():
            raise LLMClientError("Document text is empty; nothing to analyze.")

        prompt = build_analysis_prompt(document_text, document_name, document_type)

        endpoint = f"{self.base_url}/models/{self.model_name}:generateContent"
        params = {"key": self.api_key}
        headers = {"Content-Type": "application/json"}

        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}],
                }
            ],
            "systemInstruction": {
                "parts": [{"text": SYSTEM_INSTRUCTION}],
            },
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.2,
            },
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds) as client:
                response = client.post(
                    endpoint,
                    params=params,
                    headers=headers,
                    json=payload,
                )

            if response.status_code != 200:
                # Do not log or include the full URL or query params to protect the API key!
                error_detail = response.text[:300]
                if response.status_code == 404:
                    msg = f"Gemini model '{self.model_name}' was not found or is retired. Please switch to 'gemini-3.8-flash'."
                elif response.status_code in (401, 403):
                    msg = "Invalid or unauthorized Gemini API key. Please check your credentials."
                elif response.status_code == 429:
                    msg = "Gemini API rate limit or quota exceeded."
                else:
                    msg = f"Gemini API returned HTTP {response.status_code}: {error_detail}"
                raise LLMClientError(msg)

            data = response.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise LLMClientError("Gemini API returned no response candidates.")

            part = candidates[0].get("content", {}).get("parts", [{}])[0]
            raw_content = part.get("text", "")
            if not raw_content:
                raise LLMClientError("Gemini candidate content was empty.")

            cleaned_json_str = self._clean_json_response(raw_content)
            parsed_data = json.loads(cleaned_json_str)

        except httpx.TimeoutException as e:
            raise LLMClientError(f"Gemini API request timed out after {self.timeout_seconds}s: {str(e)}")
        except httpx.RequestError as e:
            raise LLMClientError(f"Network error contacting Gemini API: {str(e)}")
        except json.JSONDecodeError as e:
            raise LLMClientError(f"Failed to parse Gemini output as JSON: {str(e)}")
        except Exception as e:
            if isinstance(e, LLMClientError):
                raise
            raise LLMClientError(f"Unexpected error during AI generation: {str(e)}")

        # Construct and validate DocuMindAnalysis object
        try:
            sections = [
                PlainEnglishSection(
                    section_title=s.get("section_title", "Section"),
                    simplified_content=s.get("simplified_content", ""),
                )
                for s in parsed_data.get("plain_english_breakdown", [])
            ]

            warnings = [
                CriticalNumberOrWarning(
                    type=w.get("type", "Notice"),
                    detail=w.get("detail", ""),
                )
                for w in parsed_data.get("critical_numbers_and_warnings", [])
            ]

            glossary = [
                GlossaryItem(
                    term=g.get("term", ""),
                    definition=g.get("definition", ""),
                )
                for g in parsed_data.get("terminology_glossary", [])
            ]

            takeaways = parsed_data.get("actionable_takeaways", [])

            words = len(document_text.split())
            snippet = document_text[:500] + ("..." if len(document_text) > 500 else "")

            return DocuMindAnalysis(
                document_name=document_name,
                document_type=document_type,
                word_count=words,
                executive_summary=parsed_data.get("executive_summary", "Summary unavailable."),
                plain_english_breakdown=sections,
                critical_numbers_and_warnings=warnings,
                terminology_glossary=glossary,
                actionable_takeaways=takeaways,
                extracted_text_snippet=snippet,
                engine_used=f"gemini_api ({self.model_name})",
                is_fallback=False,
                processing_timestamp=datetime.now(timezone.utc).isoformat(),
            )
        except Exception as e:
            raise LLMClientError(f"Failed to conform API output to DocuMindAnalysis schema: {str(e)}")
