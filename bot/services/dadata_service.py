"""
DaData API Integration for Address Normalization and Enrichment
Docs: https://dadata.ru/api/suggest/address/
"""
import aiohttp
import logging
from typing import Optional, List, Dict
from bot.config import config

class DaDataService:
    """Service for working with DaData API"""
    
    BASE_URL = "https://suggestions.dadata.ru/suggestions/api/4_1/rs"
    CLEAN_URL = "https://cleaner.dadata.ru/api/v1/clean"
    
    def __init__(self, api_key: str, secret_key: Optional[str] = None):
        self.api_key = api_key
        self.secret_key = secret_key or api_key
        
    def _get_headers(self, use_secret: bool = False) -> dict:
        """Get request headers with auth"""
        token = self.secret_key if use_secret else self.api_key
        return {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json"
        }
    
    async def suggest_address(
        self, 
        query: str, 
        count: int = 5,
        locations: Optional[List[Dict]] = None
    ) -> List[Dict]:
        """
        Get address suggestions (autocomplete).
        
        Args:
            query: User input (e.g., "Москва Ленина 5")
            count: Max suggestions to return
            locations: Optional location filters (e.g., [{"city": "Москва"}])
        
        Returns:
            List of suggestion dicts with 'value' and 'data' keys
        """
        url = f"{self.BASE_URL}/suggest/address"
        payload = {
            "query": query,
            "count": count
        }
        
        if locations:
            payload["locations"] = locations
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url, 
                    headers=self._get_headers(), 
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logging.error(f"DaData error: {resp.status} - {await resp.text()}")
                        return []
                    
                    data = await resp.json()
                    return data.get("suggestions", [])
        
        except Exception as e:
            logging.error(f"DaData request failed: {e}")
            return []
    
    async def clean_address(self, raw_address: str) -> Optional[Dict]:
        """
        Clean and normalize a single address.
        
        Args:
            raw_address: Raw address string
        
        Returns:
            Normalized address data dict or None if failed
        """
        url = f"{self.CLEAN_URL}/address"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    headers=self._get_headers(use_secret=True),
                    json=[raw_address],
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status != 200:
                        logging.error(f"DaData clean error: {resp.status}")
                        return None
                    
                    data = await resp.json()
                    return data[0] if data else None
        
        except Exception as e:
            logging.error(f"DaData clean failed: {e}")
            return None
    
    async def get_house_info(self, query: str) -> Optional[Dict]:
        """
        Get detailed info about a house (including UK, coords, etc.)
        
        Returns dict with keys:
            - address: Full normalized address
            - fias_id: FIAS code (unique ID)
            - house_fias_id: House FIAS code
            - postal_code: ZIP
            - coords: {"lat": ..., "lon": ...}
            - management_company: UK name (if available)
            - region, city, street, house, block, flat
        """
        suggestions = await self.suggest_address(query, count=1)
        
        if not suggestions:
            return None
        
        first = suggestions[0]
        data = first.get("data", {})
        
        return {
            "address": first.get("value", ""),
            "unrestricted_address": first.get("unrestricted_value", ""),
            "fias_id": data.get("fias_id"),
            "house_fias_id": data.get("house_fias_id"),
            "postal_code": data.get("postal_code"),
            "coords": {
                "lat": data.get("geo_lat"),
                "lon": data.get("geo_lon")
            },
            "management_company": data.get("management_company"),
            "region": data.get("region_with_type"),
            "city": data.get("city") or data.get("settlement"),
            "street": data.get("street_with_type"),
            "house": data.get("house"),
            "block": data.get("block"),
            "flat": data.get("flat"),
            "kladr_id": data.get("kladr_id")
        }


# Global instance (initialized in main.py or config)
dadata_service: Optional[DaDataService] = None


def get_dadata_service() -> Optional[DaDataService]:
    """Get DaData service instance"""
    global dadata_service
    
    if dadata_service is None:
        api_key = getattr(config, 'DADATA_API_KEY', None)
        secret_key = getattr(config, 'DADATA_SECRET_KEY', None)
        
        if api_key:
            dadata_service = DaDataService(api_key, secret_key)
        else:
            logging.warning("DADATA_API_KEY not configured")
    
    return dadata_service
