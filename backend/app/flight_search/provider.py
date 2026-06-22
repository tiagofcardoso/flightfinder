from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class FlightProvider(ABC):
    @abstractmethod
    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for flights between origin and destination on a specific date (or date range).
        Returns a list of flight options.
        """
        pass

    @abstractmethod
    async def get_price_matrix(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        range_days: int = 3,
        passengers: int = 1
    ) -> Dict[str, Any]:
        """
        Generate a matrix of flight prices for variations in departure and return dates.
        """
        pass

    @abstractmethod
    async def get_airport_suggestions(self, query: str) -> List[Dict[str, str]]:
        """
        Fetch airport suggestion codes and names for a given search query (city or code).
        """
        pass
