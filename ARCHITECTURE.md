# System Architecture Documentation
## Project: DocuMind-AI
**Architectural Tier:** Production-Ready MVP  
**Revision:** 1.0.0  
**Target Execution Environment:** Python 3.14.2 / Windows 10/11 / Tesseract 5.4.0  

---

## 1. High-Level Architectural Pattern
DocuMind-AI is architected around a **Modular Clean Architecture & Pipeline Pattern**. The system separates business logic (document extraction, OCR, text normalization, AI understanding) from delivery mechanisms (web interfaces, REST APIs, CLI runners).

```
┌────────────────────────────────────────────────────────┐
│                   Presentation Layer                   │
│   Streamlit Web Interface / Modern FastAPI REST App    │
└───────────────────────────┬────────────────────────────┘
                            │
┌───────────────────────────▼────────────────────────────┐
│                  Service Orchestration                 │
│              DocuMind Orchestrator Service             │
└──────┬────────────────────┬────────────────────┬───────┘
       │                    │                    │
┌──────▼───────┐    ┌───────▼──────┐     ┌───────▼───────┐
│ Ingestion &  │    │  Extraction  │     │ AI Cognitive  │
│  Validation  │    │   Pipeline   │     │ Engine (LLM)  │
│  MIME/Types  │    │ (PDF & OCR)  │     │ & Fallback    │
└──────────────┘    └──────────────┘     └───────────────┘
```

This decoupled design enables:
1. Direct isolated unit testing of extraction, OCR, and AI prompts without spinning up a web server.
2. Dual frontends: An interactive Streamlit dashboard for end-user interaction and a FastAPI backend with REST endpoints for programmatic integration.
3. Zero lock-in: Extractor engines (pypdf vs Tesseract) and AI providers (Gemini API vs Local LLM vs Rule-based engine) can be swapped via clean interfaces.

---

## 2. Component Architecture

### 2.1 Presentation Layer (Frontend)
- **Technology:** Streamlit 1.64.0 (Pre-installed in environment) + FastAPI Dashboard capability.
- **Capabilities:**
  - Drag-and-drop file uploader supporting `.pdf`, `.txt`, `.png`, `.jpg`, `.jpeg`.
  - Real-time processing progress indicators and step status badges.
  - Side-by-side split layout:
    - **Left / Upper Pane:** Document Preview & Metadata (Filename, Type, Character count, Extraction method used).
    - **Right / Lower Pane:** Structured Cognitive Output Tabs:
      1. 📌 *Executive Overview*
      2. 💡 *Plain-English Simplification*
      3. ⚠️ *Crucial Numbers, Conditions & Warnings*
      4. 📖 *Jargon Buster Glossary*
      5. ✅ *Action Checklist*
      6. 🔍 *Raw Extracted Text (Inspectable/Auditable)*
  - One-click export button: Download comprehensive analysis report as Markdown or JSON.

### 2.2 Backend Architecture & Service Orchestration
- **Directory Layout:**
  ```
  DocuMind-AI/
  ├── app.py                     # Primary Application Entrypoint (Streamlit UI)
  ├── api.py                     # Optional FastAPI REST Server
  ├── documind/
  │   ├── __init__.py
  │   ├── config.py              # Central Configuration & Environment Settings
  │   ├── models.py              # Pydantic Schemas for Requests & Structured Output
  │   ├── pipeline.py            # End-to-end Processing Orchestrator
  │   ├── extractors/
  │   │   ├── __init__.py
  │   │   ├── base.py            # Base Extractor Abstract Class
  │   │   ├── pdf_extractor.py   # Native Digital PDF Parser (pypdf)
  │   │   ├── ocr_extractor.py   # Tesseract OCR Wrapper (CLI Subprocess)
  │   │   └── text_extractor.py  # Plain Text Normalizer
  │   ├── preprocessor/
  │   │   ├── __init__.py
  │   │   ├── image_cleaner.py   # Pillow Grayscale/Contrast/Binarization
  │   │   └── text_cleaner.py    # Regex whitespace normalization & artifact repair
  │   └── ai/
  │       ├── __init__.py
  │       ├── llm_client.py      # Gemini API Client with Rate-Limit & Error Handling
  │       ├── prompts.py         # System Prompts & Structured Extraction Directives
  │       └── fallback_engine.py # Offline Deterministic NLP & Heuristic Parser
  └── tests/
      ├── test_extractors.py     # OCR & PDF Unit Tests
      ├── test_pipeline.py       # End-to-end Pipeline Tests
      └── test_ai.py             # Prompt & Fallback Parser Tests
  ```

---

## 3. Detailed Document Processing Pipeline

```
[Uploaded File] ──► [File Validator] ──► [Document Type Router]
                                                  │
                       ┌──────────────────────────┴──────────────────────────┐
                       │ (MIME = pdf)                                        │ (MIME = image/*)
                       ▼                                                     ▼
           [pypdf Text Layer Check]                               [Pillow Image Preprocessing]
           ┌───────────┴───────────┐                                         │
           ▼ (Found Text)          ▼ (Scanned / Empty)                       │
  [Extract Digital Text]    [Render Page to Image]                           │
           │                       └────────────────► [Tesseract OCR Engine] ◄┘
           │                                                   │
           └───────────────────────┬───────────────────────────┘
                                   ▼
                         [Text Sanitizer & Cleaner]
                                   │
                                   ▼
                    [Prompt Context Assembly]
                                   │
                                   ▼
                   [AI Cognitive Engine (LLM / Fallback)]
                                   │
                                   ▼
                     [JSON Schema Validation]
                                   │
                                   ▼
                    [Structured Output Delivery]
```

### Step 1: Ingestion & Format Detection
1. The uploaded file is inspected via file signature (magic bytes) and file extension.
2. Supported types:
   - `application/pdf`
   - `text/plain`
   - `image/png`, `image/jpeg`, `image/tiff`

### Step 2: PDF Text Extraction Strategy
1. The document is opened using `pypdf.PdfReader`.
2. Text is extracted page-by-page.
3. **Threshold Check:** If extracted text count is greater than 50 characters per page, the document is tagged as **Digital PDF** and native extracted text is retained.
4. If the page returns less than 50 characters or empty whitespace, it is flagged as a **Scanned PDF**. The page image is rendered or converted, then passed to the OCR subsystem.

### Step 3: OCR Integration with Tesseract
- **Binary Path:** Defaults to `C:\Program Files\Tesseract-OCR\tesseract.exe` (validated and operational on system PATH).
- **Execution Mechanism:** Invoked via safe Python `subprocess.run` with timeout protection and non-blocking stdout capture.
- **Image Preprocessing via Pillow:**
  1. **Grayscale Conversion:** `image.convert('L')` removes color noise.
  2. **Contrast Enhancement:** `ImageEnhance.Contrast(img).enhance(2.0)` sharpens text edges.
  3. **Adaptive Binarization / Thresholding:** Converts faint or uneven document scans into high-contrast black-on-white text.
  4. **Orientation Detection:** Automatically aligns rotated pages via Tesseract OSD model (`osd.traineddata`).

### Step 4: Text Cleaning & Sanitization
1. Strips unprintable ASCII and binary control characters.
2. Normalizes multiple spaces, tabs, and inconsistent Windows (`\r\n`) / Unix (`\n`) line endings.
3. Repairs hyphenated word splits across line breaks (e.g. `re- \n sponsibility` ➔ `responsibility`).
4. Reconstructs paragraph breaks for cohesive LLM context ingestion.

### Step 5: AI Understanding & Cognition Layer
1. **Prompt Engineering:**
   The sanitized text is bound to a structured system prompt directing the AI to:
   - Act as an empathetic expert translator of complex documents.
   - Deconstruct dense jargon into simple 8th-grade vocabulary without diluting nuance.
   - Extract every numerical value, dollar amount, deadline, penalty, and percentage verbatim.
   - Flag every mandatory condition ("must", "shall", "provided that", "excluding").
   - Populate a formal Glossary with term + plain-language definition.
2. **Output Format:**
   Returns a strictly validated JSON object conforming to the `DocuMindAnalysis` Pydantic model.
3. **Deterministic Fallback Engine:**
   If no API key is provided, or when the system operates offline, an integrated rule-based heuristic engine extracts key sentences, regex patterns for currencies/dates/percentages, known legal/technical glossary terms, and high-frequency concepts so the application remains 100% functional without an active network connection.

---

## 4. Data Flow Specifications

| Phase | Input Data | Component | Output Data |
|---|---|---|---|
| **Upload** | `bytes` or `io.BytesIO` | `FileValidator` | Validated File Object + Metadata |
| **Routing** | File Metadata | `DocumentRouter` | Extractor Route (`PDF`, `TXT`, `OCR`) |
| **Extraction** | Raw File | `pypdf` / `Tesseract` | Raw Text String |
| **Sanitization** | Raw Text | `TextCleaner` | Normalized Clean Text |
| **Cognitive Processing** | Normalized Text | `AI Understanding Engine` | `DocuMindAnalysis` Data Object |
| **Visualization** | `DocuMindAnalysis` | Streamlit / FastAPI UI | Rendered Cards, Tables & Tabs |

---

## 5. Error Handling & Resilience Matrix

| Error Scenario | Root Cause | System Response | User Experience |
|---|---|---|---|
| **Corrupted PDF** | Damaged headers, truncated file stream | `pypdf.errors.PdfReadError` caught in `pdf_extractor.py` | Descriptive warning banner: *"File appears corrupted or unreadable. Please check file integrity."* |
| **Blank / Blurry Image** | User uploaded blank photo or out-of-focus camera image | Tesseract yields empty or < 5 characters | Informative notice: *"No legible text detected in image. Ensure image is well-lit and in focus."* |
| **Tesseract Process Timeout** | Huge image file or hangs | `subprocess.TimeoutExpired` (15s ceiling) | Graceful timeout interrupt, logs warning, returns partial text or error alert. |
| **LLM API Rate Limit / Quota** | HTTP 429 or network disconnect | Caught by `llm_client.py` retry handler | Automatic fallback to `fallback_engine.py` with badge: *"Generated via Offline Heuristic Engine"*. |
| **Unsupported File Type** | User dropped `.exe`, `.zip`, `.docx` | MIME / Extension validation filter | Immediate UI rejection: *"Format not supported. Please upload PDF, TXT, PNG, or JPG."* |
| **Excessive File Size** | File > 25MB | Size check before reading into memory | Early rejection with file size warning. |

---

## 6. Security & Privacy Safeguards
- **Local Sandbox Execution:** OCR and native PDF parsing execute entirely on the local host.
- **In-Memory Buffering:** Uploaded documents are processed in memory (`io.BytesIO`) where possible, minimizing disk artifacts.
- **Ephemeral Scratch Cleaning:** Any temporary preprocessed images are created in temporary directory structures and automatically cleaned up upon request completion.
- **API Key Isolation:** API credentials are read exclusively from environment variables or a local `.env` file, never committed to version control.
