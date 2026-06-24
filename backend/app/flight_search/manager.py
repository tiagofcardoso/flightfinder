import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple

from .provider import FlightProvider
from .mock_provider import MockFlightProvider
from .amadeus_provider import AmadeusFlightProvider
from .kiwi_provider import KiwiFlightProvider
from .serpapi_provider import SerpApiFlightProvider

logger = logging.getLogger(__name__)

# Nearby/alternative airports for major hubs — used for smart route suggestions
NEARBY_AIRPORTS: Dict[str, List[str]] = {
    "GRU": ["CGH", "VCP"],   # São Paulo
    "CGH": ["GRU", "VCP"],
    "VCP": ["GRU", "CGH"],
    "SDU": ["GIG"],           # Rio de Janeiro
    "GIG": ["SDU"],
    "LIS": ["OPO", "FAO"],   # Portugal
    "OPO": ["LIS"],
    "MAD": ["BCN"],           # Spain
    "BCN": ["MAD"],
    "JFK": ["EWR", "LGA"],   # New York
    "EWR": ["JFK", "LGA"],
    "LGA": ["JFK", "EWR"],
    "LAX": ["BUR", "LGB", "SNA"],
    "ORD": ["MDW"],
    "CDG": ["ORY"],           # Paris
    "ORY": ["CDG"],
    "LHR": ["LGW", "STN"],   # London
    "LGW": ["LHR", "STN"],
    "MIA": ["FLL", "PBI"],   # Miami
    "FLL": ["MIA"],
    "FCO": ["CIA"],           # Rome
    "FRA": ["HHN"],           # Frankfurt
}

# Smart hub routes: common intermediate hubs for BR↔Europe / BR↔US
HUB_ROUTES: Dict[Tuple[str, str], List[str]] = {
    # Brazil → Europe
    ("GRU", "LIS"): ["MAD", "LHR", "CDG", "FCO", "AMS"],
    ("GRU", "OPO"): ["LIS", "MAD", "LHR"],
    ("GRU", "CDG"): ["LIS", "MAD", "AMS"],
    ("GRU", "LHR"): ["LIS", "MAD", "CDG"],
    ("GRU", "MAD"): ["LIS", "CDG"],
    # Brazil → US
    ("GRU", "JFK"): ["MIA", "GRU", "BOG"],
    ("GRU", "MIA"): ["BOG", "PTY"],
    ("GRU", "ORD"): ["MIA", "JFK", "GRU"],
    # Portugal → Brazil
    ("LIS", "GRU"): ["MAD", "CDG"],
    ("LIS", "GIG"): ["MAD"],
    # Portugal → US
    ("LIS", "JFK"): ["MAD", "LHR", "CDG"],
    ("LIS", "MIA"): ["MAD", "LHR"],
}


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
            self.active_provider = self.kiwi_provider
            logger.info("FlightSearchManager: Using real Kiwi Tequila Flight API.")
        elif self.amadeus_provider.is_configured:
            self.active_provider = self.amadeus_provider
            logger.info("FlightSearchManager: Using real Amadeus Flight API.")
        else:
            self.active_provider = self.mock_provider
            logger.info("FlightSearchManager: Real API credentials not set. Falling back to Mock Flight Engine.")

    async def get_airport_suggestions(self, query: str) -> List[Dict[str, str]]:
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
        """Standard single-market search (Brazil perspective, USD)."""
        try:
            return await self.active_provider.search_flights(
                origin, destination, departure_date, return_date, passengers, max_price
            )
        except Exception as e:
            logger.error(f"Error searching flights on active provider: {e}")
            if self.active_provider != self.mock_provider:
                logger.info("Falling back to Mock Flight Engine.")
                return await self.mock_provider.search_flights(
                    origin, destination, departure_date, return_date, passengers, max_price
                )
            return []

    async def search_flights_multi_market(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        max_price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Searches from BOTH Brazil (BRL) and Portugal (EUR) market perspectives in parallel.
        Returns a dict with results from each market and a recommendation.
        """
        if not isinstance(self.active_provider, SerpApiFlightProvider):
            # Non-SerpAPI providers don't support multi-market
            results = await self.search_flights(origin, destination, departure_date, return_date, passengers, max_price)
            return {"br": results, "pt": [], "recommendation": "br"}

        # Run both market searches in parallel
        br_task = self.active_provider.search_flights_for_country(
            origin, destination, departure_date, return_date, passengers, max_price,
            country="br", currency="USD"
        )
        pt_task = self.active_provider.search_flights_for_country(
            origin, destination, departure_date, return_date, passengers, max_price,
            country="pt", currency="USD"  # Keep USD for fair comparison
        )

        br_results, pt_results = await asyncio.gather(br_task, pt_task, return_exceptions=True)

        if isinstance(br_results, Exception):
            logger.error(f"BR market search failed: {br_results}")
            br_results = []
        if isinstance(pt_results, Exception):
            logger.error(f"PT market search failed: {pt_results}")
            pt_results = []

        # Determine recommendation
        br_cheapest = br_results[0]["price"] if br_results else float("inf")
        pt_cheapest = pt_results[0]["price"] if pt_results else float("inf")

        recommendation = "br" if br_cheapest <= pt_cheapest else "pt"
        savings = abs(br_cheapest - pt_cheapest)

        return {
            "br": br_results,
            "pt": pt_results,
            "br_cheapest": br_cheapest if br_results else None,
            "pt_cheapest": pt_cheapest if pt_results else None,
            "recommendation": recommendation,
            "savings": round(savings, 2)
        }

    async def search_alternative_routes(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Searches for nearby origin/destination airports and known hub alternatives
        to find cheaper options. Returns a ranked list of alternatives.
        """
        if not isinstance(self.active_provider, SerpApiFlightProvider):
            return []

        origin = origin.upper()
        destination = destination.upper()

        # Collect candidate route pairs
        candidate_origins = [origin] + NEARBY_AIRPORTS.get(origin, [])[:1]  # Max 1 nearby origin
        candidate_dests = [destination] + NEARBY_AIRPORTS.get(destination, [])[:1]  # Max 1 nearby dest

        # Build unique route combinations (skip the original route)
        route_pairs = []
        for org in candidate_origins:
            for dst in candidate_dests:
                if org == origin and dst == destination:
                    continue  # Skip the original route
                route_pairs.append((org, dst))

        if not route_pairs:
            return []

        # Search all alternatives in parallel (limit to 2 to save API calls)
        tasks = [
            self.active_provider.search_flights_for_country(
                org, dst, departure_date, return_date, passengers,
                country="br", currency="USD"
            )
            for org, dst in route_pairs[:2]
        ]

        results_list = await asyncio.gather(*tasks, return_exceptions=True)

        alternatives = []
        for (org, dst), results in zip(route_pairs[:2], results_list):
            if isinstance(results, Exception) or not results:
                continue
            cheapest = results[0]
            cheapest["alt_origin"] = org
            cheapest["alt_destination"] = dst
            cheapest["is_alternative"] = True
            alternatives.append(cheapest)

        # Sort by price
        alternatives.sort(key=lambda x: x["price"])
        return alternatives

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
                logger.info("Falling back to Mock Flight Engine.")
                return await self.mock_provider.get_price_matrix(
                    origin, destination, departure_date, return_date, range_days, passengers
                )
            return {}
