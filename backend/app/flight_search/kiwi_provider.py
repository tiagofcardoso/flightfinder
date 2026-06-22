import os
import logging
import httpx
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .provider import FlightProvider

logger = logging.getLogger(__name__)

class KiwiFlightProvider(FlightProvider):
    def __init__(self) -> None:
        self.api_key = os.environ.get("KIWI_API_KEY")
        self.is_configured = bool(self.api_key)
        
        self.base_url = "https://api.tequila.kiwi.com"
        self.headers = {
            "apikey": self.api_key or "",
            "accept": "application/json"
        }

    def _convert_date(self, date_str: str) -> str:
        """Convert YYYY-MM-DD to DD/MM/YYYY for Kiwi API."""
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%d/%m/%Y")
        except Exception:
            return date_str

    async def get_airport_suggestions(self, query: str) -> List[Dict[str, str]]:
        if not self.is_configured:
            return []
            
        try:
            # Kiwi locations API
            url = f"{self.base_url}/locations/query"
            params = {
                "term": query,
                "locale": "en-US",
                "location_types": "airport",
                "limit": 5
            }
            
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, params=params)
                if response.status_code != 200:
                    logger.error(f"Kiwi Locations API returned status {response.status_code}: {response.text}")
                    return []
                    
                data = response.json()
                results = []
                for loc in data.get("locations", []):
                    results.append({
                        "code": loc.get("code"),
                        "city": loc.get("city", {}).get("name"),
                        "country": loc.get("city", {}).get("country", {}).get("name"),
                        "name": loc.get("name")
                    })
                return results
        except Exception as e:
            logger.error(f"Error fetching Kiwi airport suggestions: {e}")
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
        if not self.is_configured:
            return []
            
        try:
            url = f"{self.base_url}/v2/search"
            
            # Format dates to DD/MM/YYYY
            kiwi_dep = self._convert_date(departure_date)
            
            params = {
                "fly_from": origin.upper(),
                "fly_to": destination.upper(),
                "date_from": kiwi_dep,
                "date_to": kiwi_dep,
                "adults": passengers,
                "curr": "USD",
                "limit": 10
            }
            
            if return_date:
                kiwi_ret = self._convert_date(return_date)
                params["return_from"] = kiwi_ret
                params["return_to"] = kiwi_ret
                
            if max_price:
                params["price_to"] = int(max_price)
                
            async with httpx.AsyncClient() as client:
                response = await client.get(url, headers=self.headers, params=params, timeout=15.0)
                if response.status_code != 200:
                    logger.error(f"Kiwi Search API returned status {response.status_code}: {response.text}")
                    return []
                    
                data = response.json()
                return self._parse_kiwi_results(data.get("data", []), passengers)
                
        except Exception as e:
            logger.error(f"Error in Kiwi flight search: {e}")
            return []

    def _parse_kiwi_results(self, raw_flights: List[Dict[str, Any]], passengers: int) -> List[Dict[str, Any]]:
        parsed_offers = []
        
        for idx, flight in enumerate(raw_flights):
            try:
                price = float(flight.get("price", 0))
                
                # Kiwi route includes all flights (outbound and inbound mixed)
                route = flight.get("route", [])
                
                outbound_route = [s for s in route if s.get("return") == 0]
                inbound_route = [s for s in route if s.get("return") == 1]
                
                # If no return marker, fallback: if single route and return_date expected?
                # Usually return == 0 is outbound, return == 1 is inbound.
                
                outbound = self._parse_route_segments(outbound_route)
                inbound = self._parse_route_segments(inbound_route) if inbound_route else None
                
                # Calculate total durations
                total_duration = flight.get("duration", {}).get("departure", 0) / 60.0
                if inbound:
                    total_duration += flight.get("duration", {}).get("return", 0) / 60.0
                    
                parsed_offers.append({
                    "id": flight.get("id", f"KI-{idx}"),
                    "price": price,
                    "currency": "USD",
                    "passengers": passengers,
                    "outbound": outbound,
                    "inbound": inbound,
                    "total_duration_minutes": int(total_duration),
                    "stops": len(outbound_route) - 1 + (len(inbound_route) - 1 if inbound_route else 0)
                })
            except Exception as e:
                logger.error(f"Failed parsing Kiwi flight option: {e}")
                continue
                
        # Sort by price
        parsed_offers.sort(key=lambda x: x["price"])
        return parsed_offers

    def _parse_route_segments(self, segments: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not segments:
            raise ValueError("Empty segments list")
            
        first = segments[0]
        last = segments[-1]
        
        # Flight numbers and airlines
        airline_code = first.get("airline")
        # In mock or simple parsing, keep code as airline name or lookup
        airline_name = first.get("airline", "")  # API returns code
        flight_number = f"{airline_code}{first.get('flight_no')}"
        
        # Format times: "2026-10-15T11:30:00.000Z" -> "11:30"
        dep_time = first.get("local_departure", "")
        arr_time = last.get("local_arrival", "")
        
        dep_time_formatted = dep_time.split("T")[-1][:5] if "T" in dep_time else dep_time
        arr_time_formatted = arr_time.split("T")[-1][:5] if "T" in arr_time else arr_time
        
        # Duration
        # Calculate local difference or Kiwi duration
        dep_dt = datetime.fromisoformat(dep_time.replace("Z", "+00:00"))
        arr_dt = datetime.fromisoformat(arr_time.replace("Z", "+00:00"))
        duration_minutes = int((arr_dt - dep_dt).total_seconds() / 60)
        
        stops = len(segments) - 1
        layovers = []
        
        for i in range(stops):
            arr = segments[i]
            dep = segments[i+1]
            
            arr_dt = datetime.fromisoformat(arr.get("local_arrival", "").replace("Z", "+00:00"))
            dep_dt = datetime.fromisoformat(dep.get("local_departure", "").replace("Z", "+00:00"))
            
            layover_min = int((dep_dt - arr_dt).total_seconds() / 60)
            layovers.append({
                "airport": arr.get("flyTo"),
                "duration_minutes": max(0, layover_min)
            })
            
        return {
            "airline": airline_name,
            "airline_code": airline_code,
            "flight_number": flight_number,
            "departure_time": dep_time_formatted,
            "arrival_time": arr_time_formatted,
            "price": 0.0,
            "stops": stops,
            "layovers": layovers,
            "duration_minutes": duration_minutes,
            "cabin": "Economy",
            "baggage_included": True  # Defaults to True for simple display
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
        # To avoid rate limits or multiple calls, we search the center flight,
        # then extrapolate the grid deterministically (same approach as Amadeus).
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
                            random_var = (h % 20 - 10) / 100.0  # -10% to +10%
                            
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
            logger.error(f"Error compiling Kiwi price matrix: {e}")
            return {}
