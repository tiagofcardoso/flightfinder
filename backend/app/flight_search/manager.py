import logging
from typing import List, Dict, Any, Optional

from .provider import FlightProvider
from .mock_provider import MockFlightProvider
from .amadeus_provider import AmadeusFlightProvider
from .kiwi_provider import KiwiFlightProvider
from .serpapi_provider import SerpApiFlightProvider

logger = logging.getLogger(__name__)

class FlightSearchManager:
    def __init__(self) -> None:
        self.serpapi_provider = SerpApiFlightProvider()
        self.kiwi_provider = KiwiFlightProvider()
        self.amadeus_provider = AmadeusFlightProvider()
        self.mock_provider = MockFlightProvider()
        
        if self.serpapi_provider.is_configured:
            self.active_provider: FlightProvider = self.serpapi_provider
            logger.info("FlightSearchManager: Using real Google Flights API (via SerpAPI).")
        elif self.kiwi_provider.is_configured:
            self.active_provider: FlightProvider = self.kiwi_provider
            logger.info("FlightSearchManager: Using real Kiwi Tequila Flight API.")
        elif self.amadeus_provider.is_configured:
            self.active_provider = self.amadeus_provider
            logger.info("FlightSearchManager: Using real Amadeus Flight API.")
        else:
            self.active_provider = self.mock_provider
            logger.info("FlightSearchManager: Real API credentials not set. Falling back to Mock Flight Engine.")

    async def get_airport_suggestions(self, query: str) -> List[Dict[str, str]]:
        # Try active provider first
        return await self.active_provider.get_airport_suggestions(query)

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        try:
            return await self.active_provider.search_flights(
                origin, destination, departure_date, return_date, passengers, max_price
            )
        except Exception as e:
            logger.error(f"Error searching flights on active provider: {e}")
            if self.active_provider != self.mock_provider:
                logger.info("Error occurred. Falling back to Mock Flight Engine.")
                return await self.mock_provider.search_flights(
                    origin, destination, departure_date, return_date, passengers, max_price
                )
            return []

    async def get_price_matrix(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        range_days: int = 3,
        passengers: int = 1
    ) -> Dict[str, Any]:
        try:
            return await self.active_provider.get_price_matrix(
                origin, destination, departure_date, return_date, range_days, passengers
            )
        except Exception as e:
            logger.error(f"Error generating price matrix: {e}")
            if self.active_provider != self.mock_provider:
                logger.info("Error occurred. Falling back to Mock Flight Engine.")
                return await self.mock_provider.get_price_matrix(
                    origin, destination, departure_date, return_date, range_days, passengers
                )
            return {}
