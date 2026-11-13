"""
Image Preprocessor for OCR Optimization using Pillow.
Applies grayscale conversion, contrast enhancement, noise reduction, and scaling for Tesseract OCR.
"""

import io
from typing import Union
from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def load_image(image_input: Union[bytes, io.BytesIO, Image.Image]) -> Image.Image:
    """Load an image from bytes, BytesIO, or return existing Image object."""
    if isinstance(image_input, Image.Image):
        return image_input
    if isinstance(image_input, (bytes, bytearray)):
        return Image.open(io.BytesIO(image_input))
    if isinstance(image_input, io.BytesIO):
        return Image.open(image_input)
    raise ValueError(f"Unsupported image input type: {type(image_input)}")


def preprocess_image_for_ocr(
    image_input: Union[bytes, io.BytesIO, Image.Image],
    enhance_contrast: bool = True,
    contrast_factor: float = 2.0,
    min_dimension: int = 1000,
) -> Image.Image:
    """
    Preprocess an image to maximize Tesseract OCR character recognition accuracy.
    
    Processing steps:
    1. Flatten transparency (RGBA/LA) onto a white background.
    2. Convert to grayscale ('L').
    3. Auto-orient image based on EXIF tag if present.
    4. Upscale small images to ensure characters are tall enough for OCR.
    5. Enhance contrast to sharpen faint text against background.
    6. Apply slight unsharp mask filter to sharpen character edges.
    """
    img = load_image(image_input)

    # 1. Handle EXIF rotation if present
    try:
        img = ImageOps.exif_transpose(img)
    except Exception:
        pass  # Ignore EXIF errors

    # 2. Handle transparency / alpha channels (composite on solid white background)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        background = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(background, img).convert("RGB")

    # 3. Convert to Grayscale
    gray = img.convert("L")

    # 4. Upscale if image is too small for reliable character detection
    w, h = gray.size
    if max(w, h) < min_dimension and max(w, h) > 0:
        scale_ratio = min_dimension / max(w, h)
        new_w = int(w * scale_ratio)
        new_h = int(h * scale_ratio)
        resample_filter = getattr(Image, "Resampling", Image).LANCZOS
        gray = gray.resize((new_w, new_h), resample=resample_filter)

    # 5. Enhance Contrast
    if enhance_contrast:
        enhancer = ImageEnhance.Contrast(gray)
        gray = enhancer.enhance(contrast_factor)

    # 6. Apply mild sharpening
    gray = gray.filter(ImageFilter.SHARPEN)

    return gray
