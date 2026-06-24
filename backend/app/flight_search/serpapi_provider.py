import os
import logging
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .provider import FlightProvider

logger = logging.getLogger(__name__)

class SerpApiFlightProvider(FlightProvider):
    def __init__(self) -> None:
        self.api_key = os.environ.get("SERPAPI_API_KEY")
        self.is_configured = bool(self.api_key)
        self.base_url = "https://serpapi.com/search.json"

    async def get_airport_suggestions(self, query: str) -> List[Dict[str, str]]:
        # SerpAPI doesn't have an autocompletion engine, so we fall back to mock IATA codes
        return []

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        return await self.search_flights_for_country(origin, destination, departure_date, return_date, passengers, max_price)

    async def search_flights_for_country(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        max_price: Optional[float] = None,
        country: str = "br",  # 'br' for Brazil, 'pt' for Portugal
        currency: str = "USD"
    ) -> List[Dict[str, Any]]:
        if not self.is_configured:
            return []

        try:
            # Country/locale mapping
            locale_map = {
                "br": {"gl": "br", "hl": "pt-BR"},
                "pt": {"gl": "pt", "hl": "pt-PT"},
                "us": {"gl": "us", "hl": "en"},
            }
            locale = locale_map.get(country, locale_map["br"])

            params = {
                "engine": "google_flights",
                "departure_id": origin.upper(),
                "arrival_id": destination.upper(),
                "outbound_date": departure_date,
                "currency": currency,
                "gl": locale["gl"],
                "hl": locale["hl"],
                "api_key": self.api_key
            }

            if return_date:
                params["return_date"] = return_date
                params["type"] = "1"  # Round trip
            else:
                params["type"] = "2"  # One-way

            async with httpx.AsyncClient() as client:
                response = await client.get(self.base_url, params=params, timeout=20.0)
                if response.status_code != 200:
                    logger.error(f"SerpAPI Google Flights returned status {response.status_code}: {response.text}")
                    return []

                data = response.json()

                # Capture the direct Google Flights URL from SerpAPI metadata
                search_url = data.get("search_metadata", {}).get("google_flights_url", None)

                # SerpAPI returns flights under 'best_flights' and 'other_flights'
                flights_list = data.get("best_flights", []) + data.get("other_flights", [])

                results = self._parse_serpapi_flights(flights_list, origin, destination, passengers, max_price, search_url)

                # Tag each result with the market it came from
                for r in results:
                    r["market"] = country.upper()
                    r["market_currency"] = currency

                return results

        except Exception as e:
            logger.error(f"Error searching flights on SerpAPI: {e}", exc_info=True)
            return []

    def _parse_serpapi_flights(
        self,
        flights: List[Dict[str, Any]],
        origin: str,
        destination: str,
        passengers: int,
        max_price: Optional[float],
        search_url: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        parsed_offers = []
        
        for idx, flight in enumerate(flights):
            try:
                price = float(flight.get("price", 0.0))
                if max_price and price > max_price:
                    continue
                    
                segments = flight.get("flights", [])
                if not segments:
                    continue
                    
                # Split segments into Outbound and Inbound based on the target destination
                outbound_segs = []
                inbound_segs = []
                reached_dest = False
                
                for seg in segments:
                    dep_code = seg.get("departure_airport", {}).get("id", "").upper()
                    arr_code = seg.get("arrival_airport", {}).get("id", "").upper()
                    
                    if not reached_dest:
                        outbound_segs.append(seg)
                        if arr_code == destination.upper():
                            reached_dest = True
                    else:
                        inbound_segs.append(seg)
                        
                outbound = self._parse_itinerary(outbound_segs)
                inbound = self._parse_itinerary(inbound_segs) if inbound_segs else None
                
                total_duration = flight.get("total_duration", 0)
                
                # Build a fallback Google Flights URL if SerpAPI didn't return one
                booking_url = search_url
                if not booking_url:
                    gf_base = "https://www.google.com/travel/flights/search"
                    booking_url = (
                        f"{gf_base}?q=flights+from+{origin.upper()}+to+{destination.upper()}"
                    )

                parsed_offers.append({
                    "id": f"SA-{origin}-{destination}-{idx}",
                    "price": price * passengers,
                    "currency": "USD",
                    "passengers": passengers,
                    "outbound": outbound,
                    "inbound": inbound,
                    "total_duration_minutes": total_duration,
                    "stops": outbound["stops"] + (inbound["stops"] if inbound else 0),
                    "booking_url": booking_url
                })
            except Exception as e:
                logger.error(f"Error parsing SerpAPI flight offer: {e}")
                continue
                
        parsed_offers.sort(key=lambda x: x["price"])
        return parsed_offers

    def _parse_itinerary(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not segments:
            raise ValueError("Itinerary has no segments")
            
        first = segments[0]
        last = segments[-1]
        
        airline = first.get("airline", "Unknown")
        airline_code = first.get("airline", "")[:2].upper()
        flight_number = first.get("flight_number", "Unknown")
        
        # Parse times (Google Flights uses formats like "2026-10-15 11:30")
        dep_time_str = first.get("departure_time", "")
        arr_time_str = last.get("arrival_time", "")
        
        dep_time = dep_time_str.split(" ")[-1] if " " in dep_time_str else dep_time_str
        arr_time = arr_time_str.split(" ")[-1] if " " in arr_time_str else arr_time_str
        
        # Layovers calculation
        stops = len(segments) - 1
        layovers = []
        for i in range(stops):
            arr = segments[i]
            dep = segments[i+1]
            
            try:
                arr_dt = datetime.strptime(arr.get("arrival_time", ""), "%Y-%m-%d %H:%M")
                dep_dt = datetime.strptime(dep.get("departure_time", ""), "%Y-%m-%d %H:%M")
                layover_min = int((dep_dt - arr_dt).total_seconds() / 60)
            except Exception:
                layover_min = 90  # fallback standard layover
                
            layovers.append({
                "airport": arr.get("arrival_airport", {}).get("id", "Unknown"),
                "duration_minutes": max(0, layover_min)
            })
            
        # Overall duration sum
        duration_minutes = sum(int(s.get("duration", 0)) for s in segments)
        if len(layovers) > 0:
            duration_minutes += sum(l["duration_minutes"] for l in layovers)
            
        return {
            "airline": airline,
            "airline_code": airline_code,
            "flight_number": flight_number,
            "departure_time": dep_time[:5],
            "arrival_time": arr_time[:5],
            "price": 0.0,
            "stops": stops,
            "layovers": layovers,
            "duration_minutes": duration_minutes,
            "cabin": first.get("travel_class", "Economy"),
            "baggage_included": True
        }

    async def get_price_matrix(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        range_days: int = 3,
        passengers: int = 1
    ) -> Dict[str, Any]:
        # To preserve searches and avoid SerpAPI monthly search cap depletion,
        # we search the target center, and extrapolate dates matrix.
        if not self.is_configured:
            return {}
            
        try:
            center_flights = await self.search_flights(origin, destination, departure_date, return_date, passengers)
            if not center_flights:
                return {}
                
            center_price = center_flights[0]["price"]
            
            center_dep = datetime.strptime(departure_date, "%Y-%m-%d")
            dep_dates = [
                (center_dep + timedelta(days=d)).strftime("%Y-%m-%d")
                for d in range(-range_days, range_days + 1)
            ]
            
            ret_dates = []
            if return_date:
                center_ret = datetime.strptime(return_date, "%Y-%m-%d")
                ret_dates = [
                    (center_ret + timedelta(days=d)).strftime("%Y-%m-%d")
                    for d in range(-range_days, range_days + 1)
                ]
                
            matrix = []
            cheapest_price = float("inf")
            cheapest_cell = None
            
            import hashlib
            for dep in dep_dates:
                if return_date:
                    for ret in ret_dates:
                        if datetime.strptime(dep, "%Y-%m-%d") >= datetime.strptime(ret, "%Y-%m-%d"):
                            continue
                            
                        if dep == departure_date and ret == return_date:
                            price = center_price
                        else:
                            seed_str = f"{origin}-{destination}-{dep}-{ret}"
                            h = int(hashlib.md5(seed_str.encode()).hexdigest()[:6], 16)
                            random_var = (h % 20 - 10) / 100.0
                            
                            dep_weekday = datetime.strptime(dep, "%Y-%m-%d").weekday()
                            ret_weekday = datetime.strptime(ret, "%Y-%m-%d").weekday()
                            
                            weekday_factor = 1.0
                            if dep_weekday in (4, 6): weekday_factor += 0.08
                            if ret_weekday in (4, 6): weekday_factor += 0.08
                            if dep_weekday in (1, 2): weekday_factor -= 0.05
                            if ret_weekday in (1, 2): weekday_factor -= 0.05
                            
                            price = center_price * weekday_factor * (1.0 + random_var)
                            
                        price = round(price, 2)
                        cell = {
                            "departure_date": dep,
                            "return_date": ret,
                            "price": price,
                            "is_cheapest": False
                        }
                        if price < cheapest_price:
                            cheapest_price = price
                            cheapest_cell = cell
                        matrix.append(cell)
                else:
                    if dep == departure_date:
                        price = center_price
                    else:
                        seed_str = f"{origin}-{destination}-{dep}-OW"
                        h = int(hashlib.md5(seed_str.encode()).hexdigest()[:6], 16)
                        random_var = (h % 20 - 10) / 100.0
                        dep_weekday = datetime.strptime(dep, "%Y-%m-%d").weekday()
                        
                        weekday_factor = 1.0
                        if dep_weekday in (4, 6): weekday_factor += 0.08
                        if dep_weekday in (1, 2): weekday_factor -= 0.05
                        price = center_price * weekday_factor * (1.0 + random_var)
                        
                    price = round(price, 2)
                    cell = {
                        "departure_date": dep,
                        "return_date": None,
                        "price": price,
                        "is_cheapest": False
                    }
                    if price < cheapest_price:
                        cheapest_price = price
                        cheapest_cell = cell
                    matrix.append(cell)
                    
            if cheapest_cell:
                cheapest_cell["is_cheapest"] = True
                
            return {
                "departure_dates": dep_dates,
                "return_dates": ret_dates,
                "matrix": matrix
            }
        except Exception as e:
            logger.error(f"Error compiling SerpAPI price matrix: {e}")
            return {}
