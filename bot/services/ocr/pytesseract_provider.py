"""Pytesseract OCR Provider (fallback)"""

import logging
from typing import Optional
from datetime import date
from .base import OCRProvider, OCRResult


class PytesseractProvider(OCRProvider):
    """Pytesseract OCR provider - fallback when AI unavailable"""
    
    def __init__(self):
        self.available = self._check_availability()
    
    def _check_availability(self) -> bool:
        """Check if pytesseract is available"""
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logging.warning(f"Pytesseract not available: {e}")
            return False
    
    def is_available(self) -> bool:
        return self.available
    
    @property
    def name(self) -> str:
        return "pytesseract"
    
    async def recognize_image(self, file_bytes: bytes) -> OCRResult:
        """Recognize text from image using pytesseract"""
        import pytesseract
        from PIL import Image
        import io
        
        try:
            # Open image
            image = Image.open(io.BytesIO(file_bytes))
            
            # OCR
            text = pytesseract.image_to_string(image, lang='rus')
            
            # Extract amount and date
            amount = self._extract_amount(text)
            parsed_date = self._extract_date(text)
            
            return OCRResult(
                text=text,
                amount=amount,
                date=parsed_date,
                confidence=0.7 if amount else 0.3,
                metadata={'provider': 'pytesseract'}
            )
        except Exception as e:
            logging.error(f"Pytesseract recognition failed: {e}")
            return OCRResult(
                text="",
                amount=None,
                date=None,
                confidence=0.0,
                metadata={'provider': 'pytesseract', 'error': str(e)}
            )
    
    async def recognize_pdf(self, file_bytes: bytes) -> OCRResult:
        """PDF not supported by pytesseract"""
        return OCRResult(
            text="",
            amount=None,
            date=None,
            confidence=0.0,
            metadata={'provider': 'pytesseract', 'pdf_not_supported': True}
        )
    
    def _extract_amount(self, text: str) -> Optional[float]:
        """Extract amount from OCR text"""
        import re
        
        patterns = [
            r'(?:итого|сумма|к оплате|всего)[:\s]*(\d[\d\s]*[.,]?\d*)\s*(?:руб|₽|р\.?)?',
            r'(\d{1,3}(?:[\s,]\d{3})*(?:[.,]\d{2})?)\s*(?:руб|₽|р\.)',
            r'(\d{4,})[.,](\d{2})',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text.lower(), re.IGNORECASE)
            if match:
                amount_str = match.group(1).replace(' ', '').replace(',', '.')
                try:
                    return float(amount_str)
                except ValueError:
                    continue
        
        return None
    
    def _extract_date(self, text: str) -> Optional[date]:
        """Extract date from OCR text"""
        import re
        from datetime import datetime
        
        patterns = [
            (r'(\d{2})[./](\d{2})[./](\d{4})', '%d.%m.%Y'),
            (r'(\d{2})[./](\d{2})[./](\d{2})', '%d.%m.%y'),
            (r'(\d{4})-(\d{2})-(\d{2})', '%Y-%m-%d'),
        ]
        
        for pattern, fmt in patterns:
            match = re.search(pattern, text)
            if match:
                try:
                    return datetime.strptime(match.group(0), fmt).date()
                except ValueError:
                    continue
        
        return None
