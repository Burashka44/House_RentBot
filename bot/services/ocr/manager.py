"""OCR Manager - manages providers with fallback"""

import logging
from typing import Optional
from .base import OCRProvider, OCRResult
from .pytesseract_provider import PytesseractProvider
from .ai_provider import AIModelProvider


class OCRManager:
    """Manages OCR providers with automatic fallback"""
    
    def __init__(self):
        self.primary_provider: Optional[OCRProvider] = None
        self.fallback_provider: Optional[OCRProvider] = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize providers (call once at startup)"""
        if self._initialized:
            return
        
        from bot.config import config
        
        # Try AI model first (if configured)
        if hasattr(config, 'OLLAMA_HOST') and hasattr(config, 'OLLAMA_MODEL'):
            ai_provider = AIModelProvider(config.OLLAMA_HOST, config.OLLAMA_MODEL)
            if await ai_provider.check_availability():
                self.primary_provider = ai_provider
                logging.info(f"AI OCR provider initialized: {ai_provider.name}")
        
        # Pytesseract as fallback
        pytesseract_provider = PytesseractProvider()
        if pytesseract_provider.is_available():
            if not self.primary_provider:
                self.primary_provider = pytesseract_provider
                logging.info("Pytesseract set as primary OCR provider")
            else:
                self.fallback_provider = pytesseract_provider
                logging.info("Pytesseract set as fallback OCR provider")
        
        self._initialized = True
        
        if not self.primary_provider:
            logging.warning("No OCR providers available!")
    
    async def recognize(self, file_bytes: bytes, is_pdf: bool = False) -> OCRResult:
        """Recognize with automatic fallback"""
        
        # Ensure initialized
        if not self._initialized:
            await self.initialize()
        
        # Try primary provider
        if self.primary_provider:
            try:
                logging.info(f"Trying primary OCR provider: {self.primary_provider.name}")
                if is_pdf:
                    result = await self.primary_provider.recognize_pdf(file_bytes)
                else:
                    result = await self.primary_provider.recognize_image(file_bytes)
                
                # If got amount, success
                if result.amount is not None:
                    logging.info(f"Primary OCR success: amount={result.amount}")
                    return result
                
                logging.info("Primary OCR returned no amount, trying fallback")
            except Exception as e:
                logging.error(f"Primary OCR failed: {e}")
        
        # Fallback to secondary
        if self.fallback_provider:
            try:
                logging.info(f"Trying fallback OCR provider: {self.fallback_provider.name}")
                if is_pdf:
                    result = await self.fallback_provider.recognize_pdf(file_bytes)
                else:
                    result = await self.fallback_provider.recognize_image(file_bytes)
                
                logging.info(f"Fallback OCR result: amount={result.amount}")
                return result
            except Exception as e:
                logging.error(f"Fallback OCR failed: {e}")
        
        # No providers available or all failed
        logging.warning("All OCR providers failed or unavailable")
        return OCRResult(
            text="",
            amount=None,
            date=None,
            confidence=0.0,
            metadata={'error': 'No OCR providers available'}
        )


# Global instance
ocr_manager = OCRManager()
