"""
Kvartplata+ API Integration Service

Provides functions to interact with the Kvartplata API (lk.kvp24.ru)
to retrieve RSO (Resource Supply Organizations) data based on contract numbers (ЛС).

API Documentation: https://lk.kvp24.ru/api/v2/api-docs
"""

from typing import List, Dict, Optional
import aiohttp
import logging
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import CommProvider, CommServiceType

logger = logging.getLogger(__name__)

# API Configuration
KVARTPLATA_API_BASE = "https://lk.kvp24.ru"
DEFAULT_TIMEOUT = 10  # seconds


class KvartplataAPIError(Exception):
    """Base exception for Kvartplata API errors"""
    pass


class ContractNotFoundError(KvartplataAPIError):
    """Raised when contract number is not found"""
    pass


async def search_by_address(
    address: str,
    timeout: int = DEFAULT_TIMEOUT
) -> List[Dict]:
    """
    Search for contracts (ЛС) by address.
    
    Uses T+ API endpoint: /tplus/v1/profile/search_real_estate
    
    Args:
        address: Full address string (e.g., "Южно-Сахалинск, проспект Мира, 373а, кв 20")
        timeout: Request timeout in seconds
    
    Returns:
        List of found contracts with details:
        [
            {
                "contract_number": "12345678",
                "address": "полный адрес",
                "client_id": "...",
                "real_estate_id": "...",
                ...
            }
        ]
        
    Raises:
        KvartplataAPIError: If API request fails
    """
    url = f"{KVARTPLATA_API_BASE}/tplus/v1/profile/search_real_estate"
    
    # API expects address components
    # For now, send full address string - API should handle it
    payload = {
        "address": address,
        "pageNum": 0,
        "pageSize": 100
    }
    
    logger.info(f"Searching for address: {address}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 404:
                    logger.warning(f"No results found for address: {address}")
                    return []
                elif response.status != 200:
                    error_text = await response.text()
                    raise KvartplataAPIError(
                        f"Search API returned status {response.status}: {error_text}"
                    )
                
                data = await response.json()
                
                # API returns PagedResponseExt structure
                results = data.get("content", [])
                logger.info(f"Found {len(results)} real estate objects")
                
                # For each real estate object, get associated contracts
                all_contracts = []
                for real_estate in results:
                    real_estate_id = real_estate.get("id")
                    if real_estate_id:
                        contracts = await _get_contracts_for_real_estate(
                            real_estate_id, 
                            session,
                            timeout
                        )
                        all_contracts.extend(contracts)
                
                return all_contracts
                
    except aiohttp.ClientError as e:
        raise KvartplataAPIError(f"Network error during search: {str(e)}") from e


async def _get_contracts_for_real_estate(
    real_estate_id: str,
    session: aiohttp.ClientSession,
    timeout: int
) -> List[Dict]:
    """
    Internal helper to get contracts for a real estate object.
    """
    url = f"{KVARTPLATA_API_BASE}/tplus/v1/profile/search_ls_extended"
    params = {"realEstateId": real_estate_id}
    
    try:
        async with session.get(
            url,
            params=params,
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as response:
            if response.status != 200:
                logger.warning(f"Failed to get contracts for real estate {real_estate_id}")
                return []
            
            contracts = await response.json()
            return contracts if isinstance(contracts, list) else []
            
    except Exception as e:
        logger.exception(f"Error fetching contracts for real estate {real_estate_id}: {e}")
        return []


async def get_charges_by_contract(
    contract_number: str,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    timeout: int = DEFAULT_TIMEOUT
) -> List[Dict]:
    """
    Fetch charges (начисления) for a contract from Kvartplata API.
    
    Uses unauthenticated endpoint: /v1/finance/unauth/{contract}/charges
    
    Args:
        contract_number: Contract/ЛС number (лицевой счет)
        from_date: Start date in ISO format (YYYY-MM-DD), defaults to 1 year ago
        to_date: End date in ISO format (YYYY-MM-DD), defaults to today
        timeout: Request timeout in seconds
    
    Returns:
        List of charge objects from API
        
    Raises:
        ContractNotFoundError: If contract number is invalid
        KvartplataAPIError: For other API errors
    """
    # Default date range: last 12 months
    if not to_date:
        to_date = datetime.now().date().isoformat()
    if not from_date:
        from_date = (datetime.now() - timedelta(days=365)).date().isoformat()
    
    url = f"{KVARTPLATA_API_BASE}/v1/finance/unauth/{contract_number}/charges"
    params = {
        "from": from_date,
        "to": to_date,
        "notShowAdvance": "true"  # Hide advance charges
    }
    
    logger.info(f"Fetching charges for contract {contract_number} from {from_date} to {to_date}")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, 
                params=params, 
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as response:
                if response.status == 404:
                    raise ContractNotFoundError(f"Contract {contract_number} not found")
                elif response.status != 200:
                    error_text = await response.text()
                    raise KvartplataAPIError(
                        f"API returned status {response.status}: {error_text}"
                    )
                
                data = await response.json()
                logger.info(f"Retrieved {len(data)} charge records")
                return data
                
    except aiohttp.ClientError as e:
        raise KvartplataAPIError(f"Network error: {str(e)}") from e


async def extract_rso_from_charges(charges: List[Dict]) -> Dict[str, Dict]:
    """
    Extract RSO providers and service types from charge data.
    
    Analyzes charge records to identify unique service providers
    and categorize them by service type (electricity, water, gas, heating, etc.)
    
    Args:
        charges: List of charge objects from get_charges_by_contract()
    
    Returns:
        Dictionary mapping service types to provider info:
        {
            "electricity": {"name": "ПАО Энергосбыт", "keywords": ["электр", ...]},
            "water": {"name": "Водоканал", "keywords": ["вод", ...]},
            ...
        }
    """
    rso_map: Dict[str, Dict] = {}
    
    for charge in charges:
        # Kvartplata API returns charges with service details
        # Structure may vary, common fields:
        # - serviceName or name: service type (e.g., "Электроэнергия")
        # - amount: charge amount
        # - provider: optional provider name
        
        service_name = charge.get("serviceName") or charge.get("name", "")
        provider_name = charge.get("provider") or charge.get("supplierName", "")
        
        if not service_name:
            continue
        
        # Map service names to CommServiceType
        service_type = _map_service_to_type(service_name)
        
        if service_type and service_type not in rso_map:
            rso_map[service_type] = {
                "name": provider_name or f"РСО {service_type}",
                "keywords": _extract_keywords(service_name),
                "service_type": service_type
            }
    
    logger.info(f"Extracted {len(rso_map)} RSO providers from charges")
    return rso_map


def _map_service_to_type(service_name: str) -> Optional[str]:
    """
    Map service name from Kvartplata to CommServiceType.
    
    Args:
        service_name: Service name from API (e.g., "Электроэнергия", "Водоснабжение")
    
    Returns:
        CommServiceType value or None if not recognized
    """
    service_lower = service_name.lower()
    
    # Mapping based on common service names
    if any(kw in service_lower for kw in ["электр", "элект", "энерг", "свет"]):
        return CommServiceType.ELECTRICITY
    elif any(kw in service_lower for kw in ["вод", "водоснаб", "гвс", "хвс"]):
        return CommServiceType.WATER
    elif any(kw in service_lower for kw in ["газ", "газоснаб"]):
        return CommServiceType.GAS
    elif any(kw in service_lower for kw in ["тепл", "отопл"]):
        return CommServiceType.HEATING
    elif any(kw in service_lower for kw in ["интернет", "связь"]):
        return CommServiceType.INTERNET
    elif any(kw in service_lower for kw in ["домофон"]):
        return CommServiceType.INTERCOM
    elif any(kw in service_lower for kw in ["охран", "безопасн"]):
        return CommServiceType.SECURITY
    elif any(kw in service_lower for kw in ["мусор", "тко", "тбо"]):
        return CommServiceType.WASTE
    elif any(kw in service_lower for kw in ["управлен", "содерж", "ремонт"]):
        return CommServiceType.MANAGEMENT
    
    # Default: OTHER
    logger.warning(f"Unknown service type: {service_name}")
    return CommServiceType.OTHER


def _extract_keywords(service_name: str) -> List[str]:
    """
    Extract search keywords from service name.
    
    Args:
        service_name: Full service name
    
    Returns:
        List of lowercase keywords for matching
    """
    # Simple tokenization
    words = service_name.lower().replace(",", " ").split()
    # Filter short words and common prefixes
    keywords = [w for w in words if len(w) > 2 and w not in ["для", "или", "при"]]
    return keywords[:5]  # Limit to 5 keywords


async def save_rso_to_db(
    session: AsyncSession,
    object_id: int,
    rso_data: Dict[str, Dict],
    source: str = "kvartplata"
) -> List[CommProvider]:
    """
    Save extracted RSO data to database.
    
    Args:
        session: Database session
        object_id: RentalObject ID to link RSOs to
        rso_data: RSO mapping from extract_rso_from_charges()
        source: Data source identifier (default: "kvartplata")
    
    Returns:
        List of created CommProvider records
    """
    created_providers = []
    
    for service_type, info in rso_data.items():
        provider = CommProvider(
            object_id=object_id,
            service_type=service_type,
            name=info["name"],
            short_keywords=info["keywords"],
            source=source,
            active=True
        )
        session.add(provider)
        created_providers.append(provider)
    
    await session.commit()
    logger.info(f"Saved {len(created_providers)} RSO providers to database")
    
    return created_providers


async def import_rso_for_contract(
    session: AsyncSession,
    object_id: int,
    contract_number: str
) -> Dict:
    """
    High-level function to import RSO data for a contract.
    
    Orchestrates the full workflow:
    1. Fetch charges from Kvartplata API
    2. Extract RSO information
    3. Save to database
    
    Args:
        session: Database session
        object_id: RentalObject ID
        contract_number: Contract/ЛС number
    
    Returns:
        Dictionary with results:
        {
            "success": bool,
            "providers": List[CommProvider],
            "error": Optional[str]
        }
    """
    try:
        # Step 1: Fetch charges
        charges = await get_charges_by_contract(contract_number)
        
        if not charges:
            return {
                "success": False,
                "providers": [],
                "error": "No charges found for this contract"
            }
        
        # Step 2: Extract RSO
        rso_data = await extract_rso_from_charges(charges)
        
        if not rso_data:
            return {
                "success": False,
                "providers": [],
                "error": "Could not identify RSO providers from charges"
            }
        
        # Step 3: Save to DB
        providers = await save_rso_to_db(session, object_id, rso_data)
        
        return {
            "success": True,
            "providers": providers,
            "error": None
        }
        
    except ContractNotFoundError as e:
        logger.warning(f"Contract not found: {e}")
        return {
            "success": False,
            "providers": [],
            "error": str(e)
        }
    except KvartplataAPIError as e:
        logger.error(f"Kvartplata API error: {e}")
        return {
            "success": False,
            "providers": [],
            "error": f"API error: {str(e)}"
        }
    except Exception as e:
        logger.exception(f"Unexpected error importing RSO: {e}")
        return {
            "success": False,
            "providers": [],
            "error": f"Unexpected error: {str(e)}"
        }
