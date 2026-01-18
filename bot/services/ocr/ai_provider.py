"""AI Model OCR Provider (Ollama/LLaVA)"""

import logging
import base64
import json
from typing import Optional
from datetime import date, datetime
from .base import OCRProvider, OCRResult


class AIModelProvider(OCRProvider):
    """AI Model OCR provider - uses Ollama with vision models"""
    
    def __init__(self, ollama_host: str, model_name: str):
        self.ollama_host = ollama_host
        self.model_name = model_name
        self.available = False
    
    async def check_availability(self) -> bool:
        """Check if Ollama is available"""
        import aiohttp
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.ollama_host}/api/tags", timeout=2) as resp:
                    self.available = resp.status == 200
                    return self.available
        except Exception as e:
            logging.debug(f"Ollama not available: {e}")
            self.available = False
            return False
    
    def is_available(self) -> bool:
        return self.available
    
    @property
    def name(self) -> str:
        return f"ollama_{self.model_name}"
    
    async def recognize_image(self, file_bytes: bytes) -> OCRResult:
        """Recognize receipt using Ollama vision model"""
        import aiohttp
        
        try:
            encoded_image = base64.b64encode(file_bytes).decode('utf-8')
            
            prompt = (
                "You are a receipt scanner. Look at the image and extract:\n"
                "1. Total Amount (numeric value of transaction)\n"
                "2. Date of transaction (YYYY-MM-DD)\n"
                "3. Receiver/Payee Name\n"
                "Return JSON object with keys: 'amount' (float/null), 'date' (string YYYY-MM-DD/null), 'receiver' (string/null).\n"
                "If value not found, use null. Output ONLY raw JSON."
            )
            
            payload = {
                "model": self.model_name,
                "prompt": prompt,
                "images": [encoded_image],
                "stream": False,
                "format": "json"
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.ollama_host}/api/generate",
                    json=payload,
                    timeout=20
                ) as response:
                    if response.status != 200:
                        logging.warning(f"Ollama returned {response.status}")
                        return self._empty_result("http_error")
                    
                    data = await response.json()
                    response_text = data.get("response", "").strip()
                    
                    if not response_text:
                        return self._empty_result("empty_response")
                    
                    # Parse JSON response
                    try:
                        res = json.loads(response_text)
                        
                        amount = res.get("amount")
                        if amount:
                            amount = float(amount)
                        
                        date_str = res.get("date")
                        parsed_date = self._parse_date(date_str) if date_str else None
                        
                        receiver = res.get("receiver") or ""
                        
                        return OCRResult(
                            text=f"Ollama: {response_text}",
                            amount=amount,
                            date=parsed_date,
                            confidence=0.9 if amount else 0.5,
                            metadata={
                                'provider': 'ollama',
                                'model': self.model_name,
                                'receiver': receiver
                            }
                        )
                    except json.JSONDecodeError as e:
                        logging.error(f"Ollama JSON parse error: {e}, Text: {response_text}")
                        return self._empty_result("json_error")
        
        except Exception as e:
            logging.warning(f"Ollama recognition failed: {e}")
            return self._empty_result(str(e))
    
    async def recognize_pdf(self, file_bytes: bytes) -> OCRResult:
        """PDF recognition - convert to image first or use same method"""
        # For now, treat PDF same as image
        # In future, could convert PDF to images first
        return await self.recognize_image(file_bytes)
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date from various formats"""
        formats = ["%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d", "%d/%m/%Y"]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        
        return None
    
    def _empty_result(self, error: str) -> OCRResult:
        """Return empty result with error"""
        return OCRResult(
            text="",
            amount=None,
            date=None,
            confidence=0.0,
            metadata={'provider': 'ollama', 'error': error}
        )
