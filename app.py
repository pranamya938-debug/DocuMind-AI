"""
DocuMind-AI: Interactive Streamlit Web Application.
Connects the document extraction pipeline with the AI understanding and fallback engine.
"""

import json
import os
from pathlib import Path
from typing import Optional
import streamlit as st

from documind.config import MAX_FILE_SIZE_BYTES, SUPPORTED_EXTENSIONS
from documind.extractors.ocr_extractor import OCRExtractor
from documind.models import DocuMindAnalysis, ExtractionResult
from documind.pipeline import ExtractionPipeline
from documind.ai.llm_client import GeminiLLMClient
from documind.ai.service import DocumentUnderstandingService


# ---------------------------------------------------------------------------
# Helper Functions (Export & Sample Loading)
# ---------------------------------------------------------------------------

def build_markdown_report(
    analysis: DocuMindAnalysis,
    extraction_result: Optional[ExtractionResult] = None,
) -> str:
    """Build a comprehensive, formatted Markdown report of the analysis."""
    lines = [
        f"# DocuMind-AI Analysis Report: {analysis.document_name}",
        f"**Document Type:** {analysis.document_type}  ",
        f"**Word Count:** {analysis.word_count}  ",
        f"**Engine Used:** {analysis.engine_used}  ",
        f"**Generated:** {analysis.processing_timestamp or 'N/A'}  \n",
        "---",
        "## 1. Executive Overview",
        analysis.executive_summary,
        "",
        "---",
        "## 2. Plain-English Simplification",
    ]

    for sec in analysis.plain_english_breakdown:
        lines.append(f"### {sec.section_title}")
        lines.append(sec.simplified_content)
        lines.append("")

    lines.extend([
        "---",
        "## 3. Critical Numbers, Conditions & Warnings",
    ])
    for item in analysis.critical_numbers_and_warnings:
        lines.append(f"- **[{item.type}]** {item.detail}")

    lines.extend([
        "",
        "---",
        "## 4. Jargon Buster Glossary",
    ])
    for g in analysis.terminology_glossary:
        lines.append(f"- **{g.term}:** {g.definition}")

    lines.extend([
        "",
        "---",
        "## 5. Actionable Takeaways & Checklist",
    ])
    for idx, act in enumerate(analysis.actionable_takeaways, start=1):
        lines.append(f"{idx}. {act}")

    if extraction_result and (extraction_result.clean_text or extraction_result.raw_text):
        snippet = extraction_result.clean_text or extraction_result.raw_text
        lines.extend([
            "",
            "---",
            "## 6. Source Text Excerpt",
            "```text",
            snippet[:3000] + ("\n... [truncated]" if len(snippet) > 3000 else ""),
            "```",
        ])

    lines.extend([
        "",
        "---",
        "*Disclaimer: DocuMind-AI provides automated document simplification to assist human understanding and does not replace professional legal, medical, or financial counsel.*",
    ])

    return "\n".join(lines)


def build_json_report(analysis: DocuMindAnalysis) -> str:
    """Serialize the DocuMindAnalysis Pydantic model into pretty-printed JSON."""
    return analysis.model_dump_json(indent=2)


def load_sample_file(filename: str) -> Optional[bytes]:
    """Load sample file bytes from the repository samples directory."""
    sample_path = Path(__file__).resolve().parent / "samples" / filename
    if sample_path.is_file():
        with open(sample_path, "rb") as f:
            return f.read()
    return None


# ---------------------------------------------------------------------------
# Main Streamlit Application
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(
        page_title="DocuMind-AI",
        page_icon="🧠",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Custom CSS for Modern, Accessible Styling
    st.markdown(
        """
        <style>
        .main-header {
            font-size: 2.2rem;
            font-weight: 700;
            margin-bottom: 0.2rem;
            color: #1E293B;
        }
        .tagline {
            font-size: 1.1rem;
            color: #475569;
            margin-bottom: 1.5rem;
        }
        .metric-card {
            background-color: #F8FAFC;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .badge-pill {
            display: inline-block;
            padding: 0.25rem 0.6rem;
            font-size: 0.85rem;
            font-weight: 600;
            border-radius: 9999px;
            margin-right: 0.5rem;
        }
        .badge-financial { background-color: #DEF7EC; color: #03543F; }
        .badge-deadline { background-color: #FEF08A; color: #713F12; }
        .badge-warning { background-color: #FDE8E8; color: #9B1C1C; }
        .badge-obligation { background-color: #E1EFFE; color: #1E429F; }
        .badge-percentage { background-color: #EDEBFE; color: #5521B5; }
        .disclaimer-text {
            font-size: 0.82rem;
            color: #64748B;
            border-top: 1px solid #E2E8F0;
            padding-top: 1rem;
            margin-top: 2rem;
        }
        [data-testid="stMetricValue"] {
            font-size: 1.05rem !important;
            word-break: break-word !important;
            overflow-wrap: break-word !important;
            white-space: normal !important;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

    # Initialize Session State
    if "current_file_bytes" not in st.session_state:
        st.session_state.current_file_bytes = None
    if "current_filename" not in st.session_state:
        st.session_state.current_filename = None
    if "analysis_result" not in st.session_state:
        st.session_state.analysis_result = None
    if "extraction_result" not in st.session_state:
        st.session_state.extraction_result = None
    if "gemini_status" not in st.session_state:
        st.session_state.gemini_status = "offline"
    if "gemini_status_msg" not in st.session_state:
        st.session_state.gemini_status_msg = ""

    # -----------------------------------------------------------------------
    # Sidebar: Settings & Architecture Status
    # -----------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### 🧠 DocuMind-AI")
        st.markdown("*Cognitive Document Simplification Engine*")
        st.divider()

        st.markdown("#### ⚙️ Engine Settings")
        env_api_key = os.environ.get("GEMINI_API_KEY", "")
        user_api_key = st.text_input(
            "Gemini API Key (Optional)",
            value=env_api_key,
            type="password",
            help="Leave blank to use the deterministic Offline Heuristic Engine automatically.",
        )

        selected_model = st.selectbox(
            "Model Selection",
            ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-4-carbon", "gemini-1.5-flash"],
            index=0,
            help="Google Gemini model configuration.",
        )

        # Connection Verification Button
        if st.button("🔌 Verify Gemini Connection", use_container_width=True):
            if not user_api_key or not user_api_key.strip():
                st.session_state.gemini_status = "offline"
                st.session_state.gemini_status_msg = "No API key configured."
                st.info("No API key entered. Running in Offline Heuristic Mode.")
            else:
                test_client = GeminiLLMClient(api_key=user_api_key, model_name=selected_model)
                is_ok, msg = test_client.verify_connection()
                if is_ok:
                    st.session_state.gemini_status = "connected"
                    st.session_state.gemini_status_msg = msg
                    st.success(f"🟢 {msg}")
                else:
                    st.session_state.gemini_status = "error"
                    st.session_state.gemini_status_msg = msg
                    st.error(f"🔴 {msg}")

        st.divider()

        # Engine Status Indicator (Accurate Tri-State)
        if user_api_key and user_api_key.strip():
            if st.session_state.gemini_status == "connected":
                st.success(f"🟢 Gemini Connected ({selected_model})")
            elif st.session_state.gemini_status == "error":
                st.error(f"🔴 Offline Fallback Active ({st.session_state.gemini_status_msg})")
            else:
                st.warning("🟡 API Key Configured (Pending Verification)")
        else:
            st.info("⚙️ Offline Mode (Heuristic Engine Active)")

        # Local OCR Status
        ocr_checker = OCRExtractor()
        if ocr_checker.is_available():
            st.caption("✅ Local Tesseract OCR 5.x Ready")
        else:
            st.caption("⚠️ Tesseract OCR binary not detected")

        st.divider()

        # Reset / Clear Button
        if st.button("🔄 Reset / Clear Session", use_container_width=True):
            st.session_state.current_file_bytes = None
            st.session_state.current_filename = None
            st.session_state.analysis_result = None
            st.session_state.extraction_result = None
            st.session_state.gemini_status = "offline"
            st.session_state.gemini_status_msg = ""
            st.rerun()

        st.caption("DocuMind-AI MVP v1.1.0")

    # -----------------------------------------------------------------------
    # Main Header
    # -----------------------------------------------------------------------
    st.markdown('<div class="main-header">🧠 DocuMind-AI</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="tagline">Understand Any Document. Simplify Complex Information.</div>',
        unsafe_allow_html=True,
    )

    # -----------------------------------------------------------------------
    # Sample Documents Section
    # -----------------------------------------------------------------------
    st.markdown("#### 🚀 Try with Sample Documents")
    st.markdown(
        "Click any sample below to evaluate the system immediately without uploading your own paperwork:"
    )

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        if st.button("📄 Commercial Lease Contract", use_container_width=True):
            sample_data = load_sample_file("sample_contract.txt")
            if sample_data:
                st.session_state.current_file_bytes = sample_data
                st.session_state.current_filename = "sample_contract.txt"
                st.session_state.analysis_result = None
                st.session_state.extraction_result = None
                st.toast("Loaded sample_contract.txt", icon="📄")

    with col_s2:
        if st.button("🏥 Hospital Discharge Summary", use_container_width=True):
            sample_data = load_sample_file("sample_discharge_summary.txt")
            if sample_data:
                st.session_state.current_file_bytes = sample_data
                st.session_state.current_filename = "sample_discharge_summary.txt"
                st.session_state.analysis_result = None
                st.session_state.extraction_result = None
                st.toast("Loaded sample_discharge_summary.txt", icon="🏥")

    with col_s3:
        if st.button("🧾 Clinic Receipt (OCR Scan)", use_container_width=True):
            sample_data = load_sample_file("sample_receipt.png")
            if sample_data:
                st.session_state.current_file_bytes = sample_data
                st.session_state.current_filename = "sample_receipt.png"
                st.session_state.analysis_result = None
                st.session_state.extraction_result = None
                st.toast("Loaded sample_receipt.png", icon="🧾")

    st.markdown("")

    # -----------------------------------------------------------------------
    # Document Upload Section
    # -----------------------------------------------------------------------
    st.markdown("#### 📤 Upload Document")
    uploaded_file = st.file_uploader(
        "Upload a digital document or scanned image",
        type=["pdf", "txt", "png", "jpg", "jpeg", "tiff", "bmp"],
        help=f"Supported formats: PDF, TXT, PNG, JPG, JPEG. Max file size: {MAX_FILE_SIZE_BYTES // (1024*1024)} MB.",
    )

    if uploaded_file is not None:
        file_bytes = uploaded_file.getvalue()
        filename = uploaded_file.name

        # Size check
        if len(file_bytes) > MAX_FILE_SIZE_BYTES:
            st.error(
                f"File size exceeds {MAX_FILE_SIZE_BYTES // (1024*1024)} MB limit. Please upload a smaller file."
            )
        elif len(file_bytes) == 0:
            st.error("Uploaded file is empty (0 bytes). Please upload a valid document.")
        else:
            if (
                st.session_state.current_filename != filename
                or st.session_state.current_file_bytes != file_bytes
            ):
                st.session_state.current_file_bytes = file_bytes
                st.session_state.current_filename = filename
                st.session_state.analysis_result = None
                st.session_state.extraction_result = None

    # Display Active Document Status
    if st.session_state.current_file_bytes:
        size_kb = len(st.session_state.current_file_bytes) / 1024
        size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{(size_kb/1024):.1f} MB"
        st.info(f"**Selected Document:** `{st.session_state.current_filename}` ({size_str})")

        # Understand Document Primary Button
        if st.button("🚀 Understand Document", type="primary", use_container_width=True):
            pipeline = ExtractionPipeline()

            with st.spinner("Extracting text and analyzing document..."):
                # 1. Extraction Pipeline
                extraction_res = pipeline.process(
                    st.session_state.current_file_bytes,
                    st.session_state.current_filename,
                )

                if not extraction_res.is_success:
                    st.error(f"Extraction failed: {extraction_res.error_message}")
                    st.session_state.extraction_result = extraction_res
                    st.session_state.analysis_result = None
                else:
                    # 2. AI Cognition & Understanding
                    llm_client = GeminiLLMClient(
                        api_key=user_api_key,
                        model_name=selected_model,
                    )
                    service = DocumentUnderstandingService(llm_client=llm_client)
                    analysis = service.analyze(extraction_res)

                    # Update actual engine status accurately
                    if analysis.is_fallback:
                        if user_api_key and user_api_key.strip():
                            st.session_state.gemini_status = "error"
                            api_err = analysis.warnings[0] if analysis.warnings else "API request failed."
                            st.session_state.gemini_status_msg = api_err
                        else:
                            st.session_state.gemini_status = "offline"
                            st.session_state.gemini_status_msg = "Heuristic Engine Active"
                    else:
                        st.session_state.gemini_status = "connected"
                        st.session_state.gemini_status_msg = f"Connected to {selected_model}"

                    st.session_state.extraction_result = extraction_res
                    st.session_state.analysis_result = analysis
                    st.toast("Document analysis complete!", icon="✅")

    # -----------------------------------------------------------------------
    # Analysis Results Display
    # -----------------------------------------------------------------------
    analysis: Optional[DocuMindAnalysis] = st.session_state.analysis_result
    extraction_res: Optional[ExtractionResult] = st.session_state.extraction_result

    if analysis is not None:
        st.divider()

        # Engine & Status Metadata Banner
        col_m1, col_m2, col_m3, col_m4 = st.columns(4)
        with col_m1:
            st.metric("Document", analysis.document_name)
        with col_m2:
            st.metric("Detected Format", analysis.document_type)
        with col_m3:
            st.metric("Word Count", f"{analysis.word_count:,}")
        with col_m4:
            st.metric("Engine Used", analysis.engine_used)

        if analysis.is_fallback:
            fallback_warning_msg = analysis.warnings[0] if analysis.warnings else "Plain-language simplification is rule-based."
            st.warning(f"⚙️ **Notice:** Analysis generated using the **Offline Heuristic Engine**. {fallback_warning_msg}")

        st.markdown("### 📊 Document Analysis")

        # Five Core Tabs
        tab_exec, tab_plain, tab_crit, tab_jargon, tab_actions = st.tabs([
            "📌 Executive Overview",
            "💡 Plain-English Breakdown",
            "⚠️ Numbers & Warnings",
            "📖 Jargon Buster",
            "✅ Action Checklist",
        ])

        # TAB 1: EXECUTIVE OVERVIEW
        with tab_exec:
            st.markdown("#### Executive Summary")
            st.info(analysis.executive_summary)

        # TAB 2: PLAIN-ENGLISH SIMPLIFICATION
        with tab_plain:
            st.markdown("#### Section-by-Section Simplification")
            if analysis.plain_english_breakdown:
                for sec in analysis.plain_english_breakdown:
                    with st.expander(f"📑 {sec.section_title}", expanded=True):
                        st.markdown(sec.simplified_content)
            else:
                st.caption("No individual sections identified.")

        # TAB 3: CRITICAL NUMBERS & WARNINGS
        with tab_crit:
            st.markdown("#### Critical Numbers, Conditions & Warnings")
            st.caption("Verbatim extraction of financial amounts, deadlines, percentages, penalties, and obligations:")

            if analysis.critical_numbers_and_warnings:
                for item in analysis.critical_numbers_and_warnings:
                    badge_class = "badge-warning"
                    icon = "⚠️"
                    item_type_lower = item.type.lower()

                    if "financial" in item_type_lower or "$" in item.detail or "€" in item.detail:
                        badge_class = "badge-financial"
                        icon = "💵"
                    elif "deadline" in item_type_lower or "date" in item_type_lower:
                        badge_class = "badge-deadline"
                        icon = "⏰"
                    elif "obligation" in item_type_lower:
                        badge_class = "badge-obligation"
                        icon = "🔒"
                    elif "percentage" in item_type_lower or "%" in item.detail:
                        badge_class = "badge-percentage"
                        icon = "📊"

                    st.markdown(
                        f"""
                        <div class="metric-card">
                            <span class="badge-pill {badge_class}">{icon} {item.type.upper()}</span>
                            <span>{item.detail}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
            else:
                st.caption("No critical numerical conditions or warnings detected.")

        # TAB 4: JARGON BUSTER
        with tab_jargon:
            st.markdown("#### Jargon Buster & Glossary")
            st.caption("Complex domain terminology explained in plain English:")

            if analysis.terminology_glossary:
                for g in analysis.terminology_glossary:
                    st.markdown(f"**📖 {g.term}**")
                    st.markdown(f"> {g.definition}")
            else:
                st.caption("No obscure domain jargon detected in this document.")

        # TAB 5: ACTIONABLE TAKEAWAYS
        with tab_actions:
            st.markdown("#### Actionable Takeaways & Next Steps")
            st.caption("Concrete checklist items and obligations based on the document:")

            if analysis.actionable_takeaways:
                for idx, action in enumerate(analysis.actionable_takeaways, start=1):
                    st.markdown(f"**{idx}.** {action}")
            else:
                st.caption("No mandatory action items identified.")

        # -------------------------------------------------------------------
        # Raw Document View (Expandable for Auditability)
        # -------------------------------------------------------------------
        st.markdown("")
        with st.expander("🔍 View Original Extracted Text & Inspection Metadata", expanded=False):
            if extraction_res:
                st.markdown("##### Extraction Metadata")
                col_e1, col_e2, col_e3, col_e4 = st.columns(4)
                with col_e1:
                    st.caption(f"**Filename:** `{extraction_res.filename}`")
                with col_e2:
                    st.caption(f"**Method:** `{extraction_res.method}`")
                with col_e3:
                    st.caption(f"**Characters:** `{extraction_res.character_count:,}`")
                with col_e4:
                    st.caption(f"**Duration:** `{extraction_res.processing_time_ms:.1f} ms`")

                if extraction_res.warnings:
                    for w in extraction_res.warnings:
                        st.caption(f"⚠️ *Extraction Notice:* {w}")

                st.markdown("##### Extracted Text Content")
                st.text_area(
                    "Raw Extracted Text",
                    value=extraction_res.clean_text or extraction_res.raw_text,
                    height=250,
                    disabled=True,
                    label_visibility="collapsed",
                )
            else:
                st.caption("Extraction details unavailable.")

        # -------------------------------------------------------------------
        # Download Options (Markdown & JSON)
        # -------------------------------------------------------------------
        st.markdown("#### 📥 Export Analysis")
        col_d1, col_d2 = st.columns(2)

        base_name = Path(analysis.document_name).stem
        md_content = build_markdown_report(analysis, extraction_res)
        json_content = build_json_report(analysis)

        with col_d1:
            st.download_button(
                label="📥 Download Analysis as Markdown (.md)",
                data=md_content,
                file_name=f"{base_name}_documind_analysis.md",
                mime="text/markdown",
                use_container_width=True,
            )

        with col_d2:
            st.download_button(
                label="📥 Download Analysis as JSON (.json)",
                data=json_content,
                file_name=f"{base_name}_documind_analysis.json",
                mime="application/json",
                use_container_width=True,
            )

    # -----------------------------------------------------------------------
    # Informational Disclaimer
    # -----------------------------------------------------------------------
    st.markdown(
        """
        <div class="disclaimer-text">
            ⚠️ <strong>Disclaimer:</strong> DocuMind-AI is an automated document accessibility tool designed to assist human understanding and highlight key terms, numbers, and warnings. It does not replace professional legal, medical, or financial counsel. Always consult a qualified specialist for binding interpretations.
        </div>
        """,
        unsafe_allow_html=True,
    )


if __name__ == "__main__":
    main()
