import re
import random
from typing import Optional, Tuple
from datetime import date
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from bot.database.models import (
    TenantStay, RentCharge, CommCharge, Payment, PaymentReceipt, 
    PaymentType, PaymentStatus, ReceiptDecision, ChargeStatus, RentReceiver, CommProvider
)

# --- Charge Generation ---
async def ensure_rent_charge(session: AsyncSession, stay: TenantStay, for_month: date) -> RentCharge:
    """Ensure a rent charge exists for the given month."""
    stmt = select(RentCharge).where(
        RentCharge.stay_id == stay.id,
        RentCharge.month == for_month
    )
    result = await session.execute(stmt)
    charge = result.scalar_one_or_none()
    
    if not charge:
        # Calculate Tax
        tax_percent = float(stay.tax_rate or 0)
        base_val = float(stay.rent_amount)
        tax_val = base_val * (tax_percent / 100.0)
        total_val = base_val + tax_val

        charge = RentCharge(
            stay_id=stay.id,
            month=for_month,
            amount=total_val, # Total to pay including tax
            base_amount=base_val,
            tax_amount=tax_val,
            tax_rate_snapshot=tax_percent,
            status=ChargeStatus.pending.value
        )
        session.add(charge)
        await session.commit()
    return charge

# --- Receipt Parsing ---
class ParsedReceipt:
    def __init__(self, text: str, amount: Optional[float], parsed_date: Optional[date], 
                 receiver: str = "", purpose: str = "", confidence: float = 0.0):
        self.ocr_text = text
        self.amount = amount
        self.date = parsed_date
        self.receiver_raw = receiver
        self.purpose_raw = purpose
        self.confidence = confidence


def extract_amount_from_text(text: str) -> Optional[float]:
    """Extract monetary amount from text using regex patterns"""
    import re
    
    # Common patterns for amounts in Russian receipts
    patterns = [
        r'(?:итого|сумма|к оплате|всего)[:\s]*(\d[\d\s]*[.,]?\d*)\s*(?:руб|₽|р\.?)?',
        r'(\d{1,3}(?:[\s,]\d{3})*(?:[.,]\d{2})?)\s*(?:руб|₽|р\.)',
        r'(?:amount|sum)[:\s]*(\d+[.,]?\d*)',
        r'(\d{4,})[.,](\d{2})',  # Large number with decimals (e.g., 30000.00)
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


def extract_date_from_text(text: str) -> Optional[date]:
    """Extract date from text"""
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


def extract_receiver_from_text(text: str) -> str:
    """Extract receiver/payee name"""
    import re
    
    patterns = [
        r'(?:получатель|payee|кому)[:\s]*([А-ЯЁа-яёA-Za-z\s\.]+)',
        r'(?:ИП|ООО|АО)\s+[«"]?([^»"\n]+)[»"]?',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:100]
    
    return ""


async def parse_receipt_with_ollama(file_bytes: bytes) -> Optional[ParsedReceipt]:
    """Parse receipt using local Ollama instance (LLaVA/Llama-Vision)"""
    import base64
    import json
    import aiohttp
    import logging
    from bot.config import config
    from datetime import datetime

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
            "model": config.OLLAMA_MODEL,
            "prompt": prompt,
            "images": [encoded_image],
            "stream": False,
            "format": "json"  # Force JSON mode
        }

        async with aiohttp.ClientSession() as session:
            # Short timeout to not hang bot if Ollama is cold
            async with session.post(f"{config.OLLAMA_HOST}/api/generate", json=payload, timeout=20) as response:
                if response.status != 200:
                    logging.warning(f"Ollama returned {response.status}")
                    return None
                
                data = await response.json()
                response_text = data.get("response", "").strip()
                
                if not response_text:
                    return None
                    
                # Parse JSON
                try:
                    res = json.loads(response_text)
                    
                    amount = res.get("amount")
                    if amount:
                        amount = float(amount)
                    
                    date_str = res.get("date")
                    parsed_date = None
                    if date_str:
                         # Try couple formats
                         for fmt in ["%Y-%m-%d", "%d.%m.%Y", "%Y/%m/%d"]:
                             try:
                                 parsed_date = datetime.strptime(date_str, fmt).date()
                                 break
                             except ValueError:
                                 pass
                    
                    receiver = res.get("receiver") or ""
                    
                    # If we got amount, we good
                    if amount:
                        return ParsedReceipt(
                            text=f"Ollama: {response_text}",
                            amount=amount,
                            parsed_date=parsed_date,
                            receiver=receiver,
                            confidence=0.9 if amount else 0.5
                        )
                except Exception as e:
                    logging.error(f"Ollama JSON parse error: {e}, Text: {response_text}")
                    return None

    except Exception as e:
        logging.warning(f"Ollama unavailable or error: {e}")
        return None
        
    return None


async def parse_receipt(file_bytes: bytes) -> ParsedReceipt:
    """
    Parse receipt image using Ollama (Primary) or Tesseract OCR (Fallback).
    """
    import logging
    import io
    
    # 1. Try Ollama
    ollama_res = await parse_receipt_with_ollama(file_bytes)
    if ollama_res:
        logging.info("Receipt parsed by Ollama successfully")
        return ollama_res

    logging.info("Ollama failed/skipped, falling back to Tesseract")

    # 2. Fallback to Tesseract
    ocr_text = ""
    try:
        import pytesseract
        from PIL import Image
        
        # Load image from bytes
        try:
             image = Image.open(io.BytesIO(file_bytes))
             # Convert to RGB to handle alpha or indexed (sometimes issues)
             # image = image.convert('RGB') 
             
             # Perform OCR
             custom_config = r'--oem 3 --psm 6'
             ocr_text = pytesseract.image_to_string(image, lang='rus+eng', config=custom_config)
        except Exception:
             # Could be PDF or Corrupt image passed to PIL
             pass
        
    except ImportError:
        logging.warning("pytesseract or Pillow not installed. OCR skipped.")
        ocr_text = ""
    except Exception as e:
        logging.error(f"OCR Error: {e}")
        ocr_text = ""

    # ... Extract Amount/Date from OCR text (Legacy logic) ...
    amount = extract_amount_from_text(ocr_text)
    parsed_date = extract_date_from_text(ocr_text)
    receiver = extract_receiver_from_text(ocr_text)
    
    # Calculate confidence
    confidence = 0.0
    if amount:
        confidence += 0.4
    if parsed_date:
        confidence += 0.3
    if receiver:
        confidence += 0.3
        
    # If text exists but nothing found -> low confidence
    if ocr_text and confidence == 0:
        confidence = 0.1
    
    return ParsedReceipt(
        text=ocr_text,
        amount=amount, 
        parsed_date=parsed_date,
        receiver=receiver,
        purpose="",
        confidence=confidence
    )

# --- Validation Logic ---
async def validate_receipt_logic(
    session: AsyncSession, 
    stay: TenantStay, 
    receipt: ParsedReceipt
) -> Tuple[ReceiptDecision, str, Optional[PaymentType], Optional[float]]:
    """
    Returns: (Decision, Reason, PredictedType, Amount)
    """
    
    # 1. Check Quality (Mock / OCR Fail)
    if receipt.confidence < 0.65:
        # Fallback to manual review instead of rejecting
        # return ReceiptDecision.rejected, "Изображение плохо читается.", None, 0.0
        return ReceiptDecision.accepted, "На ручную проверку", None, 0.0

    # 2. Determine Type (Rent vs Comm)
    # Simple keyword heuristic
    text_lower = (receipt.ocr_text + " " + receipt.purpose_raw).lower()
    
    is_rent = any(w in text_lower for w in ["аренд", "наем", "жиль", "rent"])
    is_comm = any(w in text_lower for w in ["свет", "вода", "жкх", "internet", "интернет"])
    
    payment_type = None
    if is_rent:
        payment_type = PaymentType.rent
    elif is_comm:
        payment_type = PaymentType.comm
    else:
        # Default fallback or strict reject?
        # Let's reject for now if we strictly require keywords, but maybe be lenient for MVP.
        # If amount matches Rent exactly, it's Rent.
        # If amount matches Expected Rent (Base + Tax) exactly
        expected_rent = float(stay.rent_amount) * (1 + (float(stay.tax_rate or 0) / 100.0))
        if receipt.amount and abs(expected_rent - receipt.amount) < 100:
            payment_type = PaymentType.rent
        else:
            return ReceiptDecision.rejected, "Не удалось определить тип платежа (аренда или коммуналка).", None, 0.0

    # 3. Check Receiver
    # (Skip complex fuzzy check for MVP, assume if type is found, it's okay)
    
    # 4. Check Amount
    if not receipt.amount:
         # return ReceiptDecision.rejected, "Не удалось найти сумму в чеке.", payment_type, 0.0
         return ReceiptDecision.accepted, "Сумма не найдена (на ручную проверку)", payment_type, 0.0
         
    # Find Pending Charges
    # ... logic to fetch pending charges for this stay and type
    # For now, just compare against Rent Amount if Rent
    
    if payment_type == PaymentType.rent:
        # Expected = Base + Tax
        base = float(stay.rent_amount)
        tax = float(stay.tax_rate or 0)
        expected = base * (1 + tax / 100.0)
        diff = abs(expected - receipt.amount)
        if diff > (expected * 0.1): # 10% tolerance
             return ReceiptDecision.rejected, f"Сумма {receipt.amount} не соответствует аренде {expected}", payment_type, receipt.amount
    
    return ReceiptDecision.accepted, "OK", payment_type, receipt.amount

async def create_payment_from_receipt(
    session: AsyncSession,
    stay_id: int,
    file_id: str,
    parsed: ParsedReceipt,
    decision: ReceiptDecision,
    pay_type: PaymentType,
    reject_reason: Optional[str] = None
) -> Tuple[Optional[Payment], PaymentReceipt]:
    
    # Create Payment if Accepted
    payment = None
    if decision == ReceiptDecision.accepted:
        payment = Payment(
            stay_id=stay_id,
            type=pay_type.value if pay_type else "other",
            amount=parsed.amount or 0.0,
            status=PaymentStatus.pending_manual.value,
            source="photo"
        )
        session.add(payment)
        await session.flush()
    
    # Create Receipt Record
    receipt_record = PaymentReceipt(
        payment_id=payment.id if payment else None,
        stay_id=stay_id,
        file_id=file_id,
        file_type="photo",
        ocr_text=parsed.ocr_text,
        ocr_conf=parsed.confidence,
        parsed_amount=parsed.amount,
        parsed_receiver=parsed.receiver_raw,
        parsed_purpose=parsed.purpose_raw,
        decision=decision.value,
        reject_reason=reject_reason
    )
    session.add(receipt_record)
    await session.commit()
    
    return payment, receipt_record
