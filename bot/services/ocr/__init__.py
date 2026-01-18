"""OCR Provider abstraction for receipt recognition"""

from .base import OCRProvider, OCRResult
from .manager import ocr_manager

__all__ = ['OCRProvider', 'OCRResult', 'ocr_manager']
