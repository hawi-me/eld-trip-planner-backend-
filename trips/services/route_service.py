"""
Route Calculation Service.

Uses free routing APIs (OSRM / OpenRouteService) for:
- Geocoding addresses to coordinates
- Calculating routes with distance, duration, and polyline
- Decoding polylines to coordinate arrays
"""

import requests
import logging
import polyline
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass
class Coordinates:
    """Geographic coordinates."""
    latitude: float
    longitude: float
    
    def as_tuple(self) -> Tuple[float, float]:
        return (self.latitude, self.longitude)
    
    def as_lonlat(self) -> Tuple[float, float]:
        """Return as (lon, lat) for routing APIs."""
        return (self.longitude, self.latitude)


@dataclass
class RouteSegment:
    """A segment of the route between two points."""
    start: Coordinates
    end: Coordinates
    distance_miles: float
    duration_hours: float
    polyline: str
    coordinates: List[Coordinates]


@dataclass
class FullRoute:
    """Complete route from origin through all waypoints."""
    total_distance_miles: float
    total_duration_hours: float
    segments: List[RouteSegment]
    all_coordinates: List[Coordinates]
    encoded_polyline: str


class RouteServiceError(Exception):
    """Custom exception for route service errors."""
    pass


class RouteService:
    """
    Service for geocoding and route calculation.
    
    Uses:
    - Nominatim for geocoding (free, no API key required)
    - OSRM for routing (free, no API key required)
    
    Alternative: OpenRouteService (requires free API key)
    """
    
    METERS_TO_MILES = 0.000621371
    SECONDS_TO_HOURS = 1 / 3600
    
    def __init__(self):
        self.config = getattr(settings, 'ROUTING_CONFIG', {})
        self.provider = self.config.get('PROVIDER', 'osrm')
        self.nominatim_url = self.config.get(
            'NOMINATIM_BASE_URL', 
            'https://nominatim.openstreetmap.org'
        )
        self.osrm_url = self.config.get(
            'OSRM_BASE_URL',
            'https://router.project-osrm.org'
        )
        self.ors_url = self.config.get(
            'OPENROUTESERVICE_BASE_URL',
            'https://api.openrouteservice.org'
        )
        self.ors_api_key = self.config.get('OPENROUTESERVICE_API_KEY', '')
        
        # Request headers to comply with Nominatim usage policy
        # Nominatim requires a valid User-Agent with contact info
        self.headers = {
            'User-Agent': 'ELDTripPlannerApp/1.0 (https://github.com/eld-trip-planner; eld.trip.planner.app@gmail.com)',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        
        # Session for connection pooling
        self.session = requests.Session()
        self.session.headers.update(self.headers)
    
    def geocode_address(self, address: str) -> Coordinates:
        """
        Convert an address to coordinates using Nominatim.
        
        Args:
            address: Human-readable address string
            
        Returns:
            Coordinates object with lat/lon
            
        Raises:
            RouteServiceError: If geocoding fails
        """
        try:
            url = f"{self.nominatim_url}/search"
            params = {
                'q': address,
                'format': 'json',
                'limit': 1,
                # Removed countrycodes restriction to allow worldwide addresses
            }
            
            # Add delay to respect Nominatim's rate limit (1 request per second)
            import time
            time.sleep(1.1)
            
            response = self.session.get(url, params=params, timeout=15)
            response.raise_for_status()
            
            data = response.json()
            
            if not data:
                raise RouteServiceError(f"Could not geocode address: {address}")
            
            result = data[0]
            coords = Coordinates(
                latitude=float(result['lat']),
                longitude=float(result['lon'])
            )
            
            logger.info(f"Geocoded '{address}' to {coords}")
            return coords
            
        except requests.RequestException as e:
            logger.error(f"Geocoding request failed: {e}")
            raise RouteServiceError(f"Geocoding service error: {str(e)}")
    
    def calculate_route(
        self,
        origin: Coordinates,
        destination: Coordinates,
        waypoints: Optional[List[Coordinates]] = None
    ) -> FullRoute:
        """
        Calculate route between points using OSRM.
        
        Args:
            origin: Starting point coordinates
            destination: Ending point coordinates
            waypoints: Optional intermediate points
            
        Returns:
            FullRoute object with distance, duration, and coordinates
        """
        if self.provider == 'openrouteservice' and self.ors_api_key:
            return self._calculate_route_ors(origin, destination, waypoints)
        return self._calculate_route_osrm(origin, destination, waypoints)
    
    def _calculate_route_osrm(
        self,
        origin: Coordinates,
        destination: Coordinates,
        waypoints: Optional[List[Coordinates]] = None
    ) -> FullRoute:
        """
        Calculate route using OSRM (Open Source Routing Machine).
        
        OSRM API format:
        GET /route/v1/{profile}/{coordinates}?overview=full&geometries=polyline
        
        Coordinates format: lon,lat;lon,lat;lon,lat
        """
        try:
            # Build coordinates string: lon,lat format
            points = [origin]
            if waypoints:
                points.extend(waypoints)
            points.append(destination)
            
            coords_str = ';'.join(
                f"{p.longitude},{p.latitude}" for p in points
            )
            
            url = f"{self.osrm_url}/route/v1/driving/{coords_str}"
            params = {
                'overview': 'full',
                'geometries': 'polyline',
                'steps': 'true'
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if data.get('code') != 'Ok':
                raise RouteServiceError(f"OSRM error: {data.get('message', 'Unknown error')}")
            
            route = data['routes'][0]
            
            # Extract route data
            total_distance_miles = route['distance'] * self.METERS_TO_MILES
            total_duration_hours = route['duration'] * self.SECONDS_TO_HOURS
            encoded = route['geometry']
            
            # Decode polyline to coordinates
            decoded = polyline.decode(encoded)
            all_coordinates = [
                Coordinates(latitude=lat, longitude=lon) 
                for lat, lon in decoded
            ]
            
            # Build segments from legs
            segments = []
            for i, leg in enumerate(route['legs']):
                segment = RouteSegment(
                    start=points[i],
                    end=points[i + 1],
                    distance_miles=leg['distance'] * self.METERS_TO_MILES,
                    duration_hours=leg['duration'] * self.SECONDS_TO_HOURS,
                    polyline=encoded,  # Simplified: using full polyline
                    coordinates=all_coordinates
                )
                segments.append(segment)
            
            full_route = FullRoute(
                total_distance_miles=total_distance_miles,
                total_duration_hours=total_duration_hours,
                segments=segments,
                all_coordinates=all_coordinates,
                encoded_polyline=encoded
            )
            
            logger.info(
                f"Route calculated: {total_distance_miles:.1f} miles, "
                f"{total_duration_hours:.1f} hours"
            )
            
            return full_route
            
        except requests.RequestException as e:
            logger.error(f"OSRM request failed: {e}")
            raise RouteServiceError(f"Routing service error: {str(e)}")
    
    def _calculate_route_ors(
        self,
        origin: Coordinates,
        destination: Coordinates,
        waypoints: Optional[List[Coordinates]] = None
    ) -> FullRoute:
        """
        Calculate route using OpenRouteService API.
        
        Requires API key (free tier available).
        """
        try:
            url = f"{self.ors_url}/v2/directions/driving-hgv"  # Heavy goods vehicle
            
            # Build coordinates array: [lon, lat] format
            coordinates = [[origin.longitude, origin.latitude]]
            if waypoints:
                for wp in waypoints:
                    coordinates.append([wp.longitude, wp.latitude])
            coordinates.append([destination.longitude, destination.latitude])
            
            headers = {
                **self.headers,
                'Authorization': self.ors_api_key,
                'Content-Type': 'application/json'
            }
            
            payload = {
                'coordinates': coordinates,
                'geometry': True,
                'instructions': True
            }
            
            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            route = data['routes'][0]
            summary = route['summary']
            
            total_distance_miles = summary['distance'] * self.METERS_TO_MILES
            total_duration_hours = summary['duration'] * self.SECONDS_TO_HOURS
            
            # Decode geometry
            encoded = route['geometry']
            decoded = polyline.decode(encoded)
            all_coordinates = [
                Coordinates(latitude=lat, longitude=lon)
                for lat, lon in decoded
            ]
            
            # Single segment for simplicity
            segments = [RouteSegment(
                start=origin,
                end=destination,
                distance_miles=total_distance_miles,
                duration_hours=total_duration_hours,
                polyline=encoded,
                coordinates=all_coordinates
            )]
            
            return FullRoute(
                total_distance_miles=total_distance_miles,
                total_duration_hours=total_duration_hours,
                segments=segments,
                all_coordinates=all_coordinates,
                encoded_polyline=encoded
            )
            
        except requests.RequestException as e:
            logger.error(f"OpenRouteService request failed: {e}")
            raise RouteServiceError(f"Routing service error: {str(e)}")
    
    def get_full_trip_route(
        self,
        current_location: str,
        pickup_location: str,
        dropoff_location: str
    ) -> Dict:
        """
        Calculate complete trip route with all segments.
        
        Args:
            current_location: Starting address
            pickup_location: Pickup address
            dropoff_location: Final destination address
            
        Returns:
            Dictionary with route data including coordinates and segments
        """
        # Geocode all locations
        current_coords = self.geocode_address(current_location)
        pickup_coords = self.geocode_address(pickup_location)
        dropoff_coords = self.geocode_address(dropoff_location)
        
        # Calculate full route through pickup
        route = self.calculate_route(
            origin=current_coords,
            destination=dropoff_coords,
            waypoints=[pickup_coords]
        )
        
        return {
            'locations': {
                'current': {
                    'address': current_location,
                    'latitude': current_coords.latitude,
                    'longitude': current_coords.longitude
                },
                'pickup': {
                    'address': pickup_location,
                    'latitude': pickup_coords.latitude,
                    'longitude': pickup_coords.longitude
                },
                'dropoff': {
                    'address': dropoff_location,
                    'latitude': dropoff_coords.latitude,
                    'longitude': dropoff_coords.longitude
                }
            },
            'total_distance_miles': route.total_distance_miles,
            'total_duration_hours': route.total_duration_hours,
            'segments': [
                {
                    'start': s.start.as_tuple(),
                    'end': s.end.as_tuple(),
                    'distance_miles': s.distance_miles,
                    'duration_hours': s.duration_hours
                }
                for s in route.segments
            ],
            'route_coordinates': [
                {'latitude': c.latitude, 'longitude': c.longitude}
                for c in route.all_coordinates
            ],
            'encoded_polyline': route.encoded_polyline
        }
    
    def find_location_at_distance(
        self,
        route_coordinates: List[Coordinates],
        target_miles: float,
        total_miles: float
    ) -> Coordinates:
        """
        Find approximate coordinates at a given distance along the route.
        
        Used for placing fuel stops, rest stops, etc.
        """
        if not route_coordinates:
            raise RouteServiceError("No route coordinates provided")
        
        if target_miles <= 0:
            return route_coordinates[0]
        
        if target_miles >= total_miles:
            return route_coordinates[-1]
        
        # Linear interpolation based on distance percentage
        percentage = target_miles / total_miles
        index = int(percentage * (len(route_coordinates) - 1))
        index = max(0, min(index, len(route_coordinates) - 1))
        
        return route_coordinates[index]


# Example usage and response format documentation
"""
Example Request:
----------------
route_service = RouteService()
result = route_service.get_full_trip_route(
    current_location="Chicago, IL",
    pickup_location="Indianapolis, IN",
    dropoff_location="Nashville, TN"
)

Example Response:
-----------------
{
    'locations': {
        'current': {
            'address': 'Chicago, IL',
            'latitude': 41.8781,
            'longitude': -87.6298
        },
        'pickup': {
            'address': 'Indianapolis, IN',
            'latitude': 39.7684,
            'longitude': -86.1581
        },
        'dropoff': {
            'address': 'Nashville, TN',
            'latitude': 36.1627,
            'longitude': -86.7816
        }
    },
    'total_distance_miles': 456.2,
    'total_duration_hours': 7.5,
    'segments': [
        {
            'start': (41.8781, -87.6298),
            'end': (39.7684, -86.1581),
            'distance_miles': 181.5,
            'duration_hours': 3.0
        },
        {
            'start': (39.7684, -86.1581),
            'end': (36.1627, -86.7816),
            'distance_miles': 274.7,
            'duration_hours': 4.5
        }
    ],
    'route_coordinates': [
        {'latitude': 41.8781, 'longitude': -87.6298},
        ...
    ],
    'encoded_polyline': 'encodedPolylineString...'
}
"""
