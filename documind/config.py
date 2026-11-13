"""
Central Configuration for DocuMind-AI.
"""

import os
import shutil
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Tesseract OCR Executable Discovery
_DEFAULT_WIN_TESSERACT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

def get_tesseract_path() -> str:
    """Resolve the Tesseract binary path from env, standard Windows path, or PATH."""
    env_path = os.environ.get("TESSERACT_PATH")
    if env_path and Path(env_path).is_file():
        return env_path
    if _DEFAULT_WIN_TESSERACT.is_file():
        return str(_DEFAULT_WIN_TESSERACT)
    which_path = shutil.which("tesseract")
    if which_path:
        return which_path
    return str(_DEFAULT_WIN_TESSERACT)

TESSERACT_CMD = get_tesseract_path()

# Document Limits & Settings
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_FILE_SIZE_BYTES", 25 * 1024 * 1024))  # 25 MB
OCR_TIMEOUT_SECONDS = int(os.environ.get("OCR_TIMEOUT_SECONDS", 15))
DEFAULT_ENCODING = "utf-8"

# Supported Formats
SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
}

# AI Settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
