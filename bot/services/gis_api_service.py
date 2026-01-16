"""
GIS ЖКХ Official API Integration Service
SOAP Client for dom.gosuslugi.ru

This module provides integration with the official GIS ЖКХ API.
Requires:
- Registration on dom.gosuslugi.ru
- API certificate or token
- zeep library: pip install zeep

Documentation: https://open-gkh.ru
"""
import logging
from typing import List, Dict, Optional
from dataclasses import dataclass
from datetime import date

# Uncomment when ready to use:
# from zeep import Client
# from zeep.wsse.signature import Signature
# from zeep.transports import Transport


@dataclass
class RSOContract:
    """РСО договор из ГИС ЖКХ"""
    rso_name: str
    rso_inn: str
    resource_type: str  # "Электричество", "Водоснабжение", etc.
    contract_number: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


@dataclass
class HouseInfo:
    """Информация о доме из ГИС ЖКХ"""
    house_guid: str  # ГИС ЖКХ ID
    fias_guid: str  # ФИАС ID
    address: str
    uk_name: Optional[str] = None
    uk_inn: Optional[str] = None
    total_area: Optional[float] = None
    floors: Optional[int] = None
    year_built: Optional[int] = None
    rso_contracts: List[RSOContract] = None


class GISGKHAPIService:
    """
    Service for working with GIS ЖКХ SOAP API.
    
    Usage:
        service = GISGKHAPIService(
            cert_path="/path/to/cert.pem",
            key_path="/path/to/key.pem"
        )
        
        house = await service.get_house_by_fias("abc-123-def")
        rso_list = house.rso_contracts
    """
    
    # WSDL endpoints (change based on version)
    WSDL_HOUSE_MANAGEMENT = "https://dom.gosuslugi.ru/hcs-services/organizations/houseManagement?wsdl"
    WSDL_PAYMENTS = "https://dom.gosuslugi.ru/hcs-services/bills/paymentDocuments?wsdl"
    
    # Test environment
    WSDL_TEST_HOUSE = "https://test.dom.gosuslugi.ru/hcs-services/organizations/houseManagement?wsdl"
    
    def __init__(
        self, 
        cert_path: Optional[str] = None,
        key_path: Optional[str] = None,
        token: Optional[str] = None,
        use_test_env: bool = False
    ):
        """
        Initialize GIS ЖКХ API client.
        
        Args:
            cert_path: Path to SSL certificate (.pem)
            key_path: Path to private key (.pem)
            token: API token (alternative to certificate)
            use_test_env: Use test environment instead of production
        """
        self.cert_path = cert_path
        self.key_path = key_path
        self.token = token
        self.use_test_env = use_test_env
        
        # Uncomment when zeep is installed:
        # self.client = self._create_client()
    
    def _create_client(self):
        """Create SOAP client with authentication"""
        # PLACEHOLDER - Implement when zeep is available
        
        # Example:
        # wsdl = self.WSDL_TEST_HOUSE if self.use_test_env else self.WSDL_HOUSE_MANAGEMENT
        # 
        # if self.cert_path:
        #     transport = Transport(
        #         cert=(self.cert_path, self.key_path),
        #         verify=True
        #     )
        #     client = Client(wsdl, transport=transport)
        # elif self.token:
        #     # Token-based auth
        #     transport = Transport()
        #     transport.session.headers.update({'Authorization': f'Bearer {self.token}'})
        #     client = Client(wsdl, transport=transport)
        # else:
        #     raise ValueError("Either cert_path or token must be provided")
        # 
        # return client
        
        logging.warning("SOAP client not implemented - zeep library required")
        return None
    
    async def get_house_by_fias(self, fias_guid: str) -> Optional[HouseInfo]:
        """
        Get house information by FIAS GUID.
        
        Args:
            fias_guid: FIAS house identifier (from DaData)
        
        Returns:
            HouseInfo object with УК and РСО data
        """
        if not self.client:
            logging.error("GIS ЖКХ client not initialized")
            return None
        
        try:
            # SOAP request
            # response = self.client.service.getHouseByAddress(
            #     FIASHouseGuid=fias_guid
            # )
            
            # Parse response
            # house_data = response['HouseData']
            # 
            # rso_contracts = []
            # if 'SupplyResourceContracts' in response:
            #     for contract in response['SupplyResourceContracts']:
            #         rso_contracts.append(RSOContract(
            #             rso_name=contract.get('SupplierName'),
            #             rso_inn=contract.get('SupplierINN'),
            #             resource_type=contract.get('ResourceType'),
            #             contract_number=contract.get('ContractNumber'),
            #         ))
            # 
            # house = HouseInfo(
            #     house_guid=house_data['HouseGUID'],
            #     fias_guid=fias_guid,
            #     address=house_data['Address'],
            #     uk_name=house_data.get('ManagementOrganizationName'),
            #     uk_inn=house_data.get('ManagementOrganizationINN'),
            #     rso_contracts=rso_contracts
            # )
            # 
            # return house
            
            # PLACEHOLDER
            logging.warning("get_house_by_fias not implemented")
            return None
            
        except Exception as e:
            logging.error(f"GIS ЖКХ API error: {e}")
            return None
    
    async def search_house_by_address(self, address: str) -> List[HouseInfo]:
        """
        Search houses by address string.
        
        Note: It's better to use DaData first to get FIAS ID,
        then call get_house_by_fias().
        """
        logging.warning("Direct address search not recommended - use DaData → FIAS → GIS ЖКХ flow")
        return []
    
    async def get_payment_documents(
        self, 
        account_guid: str, 
        month: int, 
        year: int
    ) -> List[Dict]:
        """
        Get payment documents for account in specific period.
        
        Returns list of payment details (charges, payments, balance).
        """
        if not self.client:
            return []
        
        try:
            # response = self.client.service.exportPaymentDocumentDetailsRequest(
            #     AccountGuid=account_guid,
            #     PeriodMonth=str(month).zfill(2),
            #     PeriodYear=str(year)
            # )
            # 
            # return response['PaymentDocuments']
            
            logging.warning("get_payment_documents not implemented")
            return []
            
        except Exception as e:
            logging.error(f"Payment documents error: {e}")
            return []


# ===== Integration with HouseBot =====

async def fetch_rso_for_house_from_gis(fias_id: str) -> List[Dict]:
    """
    Helper function to get RSO list for a house using GIS ЖКХ API.
    
    This is a bridge between DaData and our bot's database.
    
    Workflow:
    1. User enters address
    2. DaData normalizes → FIAS ID
    3. This function calls GIS ЖКХ API → RSO list
    4. Bot saves RSO to database
    
    Returns:
        List of dicts with 'name', 'inn', 'service_type'
    """
    from bot.config import config
    
    # Get credentials from config
    cert_path = getattr(config, 'GIS_CERT_PATH', None)
    key_path = getattr(config, 'GIS_KEY_PATH', None)
    token = getattr(config, 'GIS_API_TOKEN', None)
    
    if not (cert_path or token):
        logging.warning("GIS ЖКХ credentials not configured")
        return []
    
    service = GISGKHAPIService(
        cert_path=cert_path,
        key_path=key_path,
        token=token,
        use_test_env=getattr(config, 'GIS_USE_TEST', False)
    )
    
    house = await service.get_house_by_fias(fias_id)
    
    if not house or not house.rso_contracts:
        return []
    
    return [
        {
            'name': contract.rso_name,
            'inn': contract.rso_inn,
            'service_type': contract.resource_type
        }
        for contract in house.rso_contracts
    ]


# ===== Configuration Example =====

"""
Add to bot/config.py:

class Config:
    ...
    
    # GIS ЖКХ API Settings
    GIS_CERT_PATH = os.getenv("GIS_CERT_PATH")  # /path/to/cert.pem
    GIS_KEY_PATH = os.getenv("GIS_KEY_PATH")    # /path/to/key.pem
    GIS_API_TOKEN = os.getenv("GIS_API_TOKEN")  # Alternative to cert
    GIS_USE_TEST = os.getenv("GIS_USE_TEST", "false").lower() == "true"

Add to .env:

# GIS ЖКХ API
GIS_CERT_PATH=/path/to/your/cert.pem
GIS_KEY_PATH=/path/to/your/key.pem
# OR
GIS_API_TOKEN=your_token_here
GIS_USE_TEST=true  # Use test environment
"""
