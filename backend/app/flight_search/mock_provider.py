import hashlib
import random
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

from .provider import FlightProvider

# Static realistic airport database
AIRPORTS = [
    {"code": "LIS", "city": "Lisbon", "country": "Portugal", "name": "Humberto Delgado Airport"},
    {"code": "OPO", "city": "Porto", "country": "Portugal", "name": "Francisco Sá Carneiro Airport"},
    {"code": "GRU", "city": "São Paulo", "country": "Brazil", "name": "Guarulhos International Airport"},
    {"code": "CGH", "city": "São Paulo", "country": "Brazil", "name": "Congonhas Airport"},
    {"code": "GIG", "city": "Rio de Janeiro", "country": "Brazil", "name": "Galeão International Airport"},
    {"code": "SDU", "city": "Rio de Janeiro", "country": "Brazil", "name": "Santos Dumont Airport"},
    {"code": "JFK", "city": "New York", "country": "United States", "name": "John F. Kennedy International Airport"},
    {"code": "LGA", "city": "New York", "country": "United States", "name": "LaGuardia Airport"},
    {"code": "EWR", "city": "New York / Newark", "country": "United States", "name": "Newark Liberty International Airport"},
    {"code": "LHR", "city": "London", "country": "United Kingdom", "name": "Heathrow Airport"},
    {"code": "LGW", "city": "London", "country": "United Kingdom", "name": "Gatwick Airport"},
    {"code": "STN", "city": "London", "country": "United Kingdom", "name": "Stansted Airport"},
    {"code": "ORY", "city": "Paris", "country": "France", "name": "Orly Airport"},
    {"code": "CDG", "city": "Paris", "country": "France", "name": "Charles de Gaulle Airport"},
    {"code": "NRT", "city": "Tokyo", "country": "Japan", "name": "Narita International Airport"},
    {"code": "HND", "city": "Tokyo", "country": "Japan", "name": "Haneda Airport"},
    {"code": "FRA", "city": "Frankfurt", "country": "Germany", "name": "Frankfurt Airport"},
    {"code": "AMS", "city": "Amsterdam", "country": "Netherlands", "name": "Schiphol Airport"},
    {"code": "MAD", "city": "Madrid", "country": "Spain", "name": "Adolfo Suárez Madrid–Barajas Airport"},
    {"code": "FCO", "city": "Rome", "country": "Italy", "name": "Leonardo da Vinci–Fiumicino Airport"},
]

AIRLINES = [
    {"name": "TAP Air Portugal", "code": "TP", "type": "Legacy"},
    {"name": "Air France", "code": "AF", "type": "Legacy"},
    {"name": "British Airways", "code": "BA", "type": "Legacy"},
    {"name": "Lufthansa", "code": "LH", "type": "Legacy"},
    {"name": "LATAM Airlines", "code": "LA", "type": "Legacy"},
    {"name": "Emirates", "code": "EK", "type": "Premium"},
    {"name": "Ryanair", "code": "FR", "type": "LCC"},
    {"name": "EasyJet", "code": "U2", "type": "LCC"},
    {"name": "Delta Air Lines", "code": "DL", "type": "Legacy"},
    {"name": "United Airlines", "code": "UA", "type": "Legacy"},
]

class MockFlightProvider(FlightProvider):
    def _deterministic_seed(self, *args: Any) -> None:
        """Seed the random generator deterministically using arguments."""
        seed_str = "-".join(str(arg) for arg in args)
        seed_hash = hashlib.md5(seed_str.encode()).hexdigest()
        random.seed(int(seed_hash[:8], 16))

    def _get_route_base_price(self, origin: str, dest: str) -> float:
        """Get base price for a route depending on distances."""
        # Simple distance category simulation
        o, d = origin.upper(), dest.upper()
        
        # Intra-Europe
        europe = {"LIS", "OPO", "LHR", "LGW", "STN", "ORY", "CDG", "FRA", "AMS", "MAD", "FCO"}
        brazil = {"GRU", "CGH", "GIG", "SDU"}
        us = {"JFK", "LGA", "EWR"}
        japan = {"NRT", "HND"}
        
        if o in europe and d in europe:
            return 80.0
        elif o in brazil and d in brazil:
            return 120.0
        elif o in us and d in us:
            return 150.0
        # Transatlantic / Intercontinental
        elif (o in europe and d in us) or (o in us and d in europe):
            return 550.0
        elif (o in europe and d in brazil) or (o in brazil and d in europe):
            return 700.0
        elif (o in brazil and d in us) or (o in us and d in brazil):
            return 600.0
        elif (o in japan) or (d in japan):
            return 1000.0
        
        return 350.0

    def _calculate_price_factor(self, date_str: str) -> float:
        """Calculate price factor based on date (day of week, seasonality)."""
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            date_obj = datetime.now()
            
        day_of_week = date_obj.weekday()  # Monday is 0, Sunday is 6
        
        factor = 1.0
        # Weekend increase (Friday & Sunday are peak travel days)
        if day_of_week in (4, 6): # Fri, Sun
            factor += 0.15
        elif day_of_week == 5: # Sat
            factor += 0.05
        elif day_of_week in (1, 2): # Tue, Wed
            factor -= 0.10 # Cheaper mid-week
            
        # Seasonal variations (Summer / December peak)
        month = date_obj.month
        if month in (6, 7, 8):  # Summer
            factor += 0.20
        elif month == 12:  # Christmas / NY
            factor += 0.25
        elif month in (2, 3, 11): # Off-peak
            factor -= 0.15
            
        return factor

    async def search_flights(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        passengers: int = 1,
        max_price: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        origin = origin.upper()
        destination = destination.upper()
        
        # Base price calculation
        route_base = self._get_route_base_price(origin, destination)
        dep_factor = self._calculate_price_factor(departure_date)
        
        # Outbound options
        self._deterministic_seed(origin, destination, departure_date, "outbound")
        outbound_options = self._generate_options(
            origin, destination, departure_date, route_base * dep_factor, passengers
        )
        
        results = []
        if return_date:
            # Round trip
            ret_factor = self._calculate_price_factor(return_date)
            self._deterministic_seed(destination, origin, return_date, "inbound")
            inbound_options = self._generate_options(
                destination, origin, return_date, route_base * ret_factor, passengers
            )
            
            # Combine outbound & inbound
            opt_idx = 0
            for out in outbound_options:
                for inbound in inbound_options:
                    combined_price = out["price"] + inbound["price"]
                    if max_price and combined_price > max_price:
                        continue
                    
                    results.append({
                        "id": f"FL-{origin}-{destination}-{departure_date}-{return_date}-{opt_idx}",
                        "price": round(combined_price, 2),
                        "currency": "USD",
                        "passengers": passengers,
                        "outbound": out,
                        "inbound": inbound,
                        "total_duration_minutes": out["duration_minutes"] + inbound["duration_minutes"],
                        "stops": out["stops"] + inbound["stops"],
                    })
                    opt_idx += 1
        else:
            # One way
            for idx, out in enumerate(outbound_options):
                if max_price and out["price"] > max_price:
                    continue
                results.append({
                    "id": f"FL-{origin}-{destination}-{departure_date}-OW-{idx}",
                    "price": round(out["price"], 2),
                    "currency": "USD",
                    "passengers": passengers,
                    "outbound": out,
                    "inbound": None,
                    "total_duration_minutes": out["duration_minutes"],
                    "stops": out["stops"],
                })
                
        # Sort by price
        results.sort(key=lambda x: x["price"])
        return results

    def _generate_options(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        base_price: float,
        passengers: int
    ) -> List[Dict[str, Any]]:
        options = []
        
        # Define 4 unique flights for the day
        # 1. Early Budget (Low Cost Carrier, usually cheaper, maybe early morning or late)
        # 2. Midday Direct (Legacy, Premium time, direct)
        # 3. Quick Connect (1 stop, Legacy)
        # 4. Long Connect (Cheaper, long stopover)
        
        # Select compatible airlines
        lcc_airlines = [a for a in AIRLINES if a["type"] == "LCC"]
        legacy_airlines = [a for a in AIRLINES if a["type"] in ("Legacy", "Premium")]
        
        # Flight 1: Budget
        airline = random.choice(lcc_airlines) if lcc_airlines else random.choice(AIRLINES)
        duration = random.randint(120, 240) if base_price < 300 else random.randint(480, 800)
        options.append({
            "airline": airline["name"],
            "airline_code": airline["code"],
            "flight_number": f"{airline['code']}{random.randint(100, 999)}",
            "departure_time": "06:15",
            "arrival_time": self._add_minutes_to_time("06:15", duration),
            "price": round(base_price * 0.75 * passengers, 2),
            "stops": 0,
            "layovers": [],
            "duration_minutes": duration,
            "cabin": "Economy",
            "baggage_included": False
        })
        
        # Flight 2: Direct Legacy Premium
        airline = random.choice(legacy_airlines)
        duration = random.randint(110, 220) if base_price < 300 else random.randint(450, 750)
        options.append({
            "airline": airline["name"],
            "airline_code": airline["code"],
            "flight_number": f"{airline['code']}{random.randint(100, 999)}",
            "departure_time": "11:30",
            "arrival_time": self._add_minutes_to_time("11:30", duration),
            "price": round(base_price * 1.2 * passengers, 2),
            "stops": 0,
            "layovers": [],
            "duration_minutes": duration,
            "cabin": "Economy",
            "baggage_included": True
        })
        
        # Flight 3: Connecting Legacy
        airline = random.choice(legacy_airlines)
        layover_airport = "MAD" if origin != "MAD" and destination != "MAD" else "FRA"
        duration = (random.randint(110, 220) if base_price < 300 else random.randint(450, 750)) + 90  # Flight + layover time
        options.append({
            "airline": airline["name"],
            "airline_code": airline["code"],
            "flight_number": f"{airline['code']}{random.randint(100, 999)}",
            "departure_time": "15:45",
            "arrival_time": self._add_minutes_to_time("15:45", duration),
            "price": round(base_price * 0.9 * passengers, 2),
            "stops": 1,
            "layovers": [{"airport": layover_airport, "duration_minutes": 90}],
            "duration_minutes": duration,
            "cabin": "Economy",
            "baggage_included": True
        })
        
        # Flight 4: Evening Deal
        airline = random.choice(AIRLINES)
        duration = random.randint(120, 240) if base_price < 300 else random.randint(480, 800)
        options.append({
            "airline": airline["name"],
            "airline_code": airline["code"],
            "flight_number": f"{airline['code']}{random.randint(100, 999)}",
            "departure_time": "20:00",
            "arrival_time": self._add_minutes_to_time("20:00", duration),
            "price": round(base_price * 0.85 * passengers, 2),
            "stops": 0,
            "layovers": [],
            "duration_minutes": duration,
            "cabin": "Economy",
            "baggage_included": True
        })
        
        return options

    def _add_minutes_to_time(self, time_str: str, minutes: int) -> str:
        t = datetime.strptime(time_str, "%H:%M")
        t_new = t + timedelta(minutes=minutes)
        return t_new.strftime("%H:%M")

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
            center_dep = datetime.strptime(departure_date, "%Y-%m-%d")
        except ValueError:
            center_dep = datetime.now()
            
        dep_dates = [
            (center_dep + timedelta(days=d)).strftime("%Y-%m-%d")
            for d in range(-range_days, range_days + 1)
        ]
        
        ret_dates = []
        if return_date:
            try:
                center_ret = datetime.strptime(return_date, "%Y-%m-%d")
            except ValueError:
                center_ret = center_dep + timedelta(days=7)
            ret_dates = [
                (center_ret + timedelta(days=d)).strftime("%Y-%m-%d")
                for d in range(-range_days, range_days + 1)
            ]
            
        matrix = []
        cheapest_price = float("inf")
        cheapest_cell = None
        
        # Ensure dep date is before return date in matrix cells
        for dep in dep_dates:
            if return_date:
                for ret in ret_dates:
                    if datetime.strptime(dep, "%Y-%m-%d") >= datetime.strptime(ret, "%Y-%m-%d"):
                        continue  # Return must be after departure
                    
                    flights = await self.search_flights(origin, destination, dep, ret, passengers)
                    if flights:
                        price = flights[0]["price"]  # Cheapest for this combination
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
                # One way matrix (just single list of dep dates prices)
                flights = await self.search_flights(origin, destination, dep, None, passengers)
                if flights:
                    price = flights[0]["price"]
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
                    
        # Mark the cheapest option
        if cheapest_cell:
            cheapest_cell["is_cheapest"] = True
            
        return {
            "departure_dates": dep_dates,
            "return_dates": ret_dates,
            "matrix": matrix
        }

    async def get_airport_suggestions(self, query: str) -> List[Dict[str, str]]:
        query = query.lower().strip()
        if not query:
            return []
            
        matches = []
        for ap in AIRPORTS:
            if (query in ap["code"].lower() or 
                query in ap["city"].lower() or 
                query in ap["name"].lower() or
                query in ap["country"].lower()):
                matches.append(ap)
                
        return matches[:5]
