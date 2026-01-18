"""Base OCR provider interface"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from datetime import date


@dataclass
class OCRResult:
    """Unified OCR result from any provider"""
    text: str
    amount: Optional[float]
    date: Optional[date]
    confidence: float
    metadata: dict


class OCRProvider(ABC):
    """Abstract OCR provider interface"""
    
    @abstractmethod
    async def recognize_image(self, file_bytes: bytes) -> OCRResult:
        """Recognize text from image (JPG, PNG)"""
        pass
    
    @abstractmethod
    async def recognize_pdf(self, file_bytes: bytes) -> OCRResult:
        """Recognize text from PDF document"""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available and ready"""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging"""
        pass
