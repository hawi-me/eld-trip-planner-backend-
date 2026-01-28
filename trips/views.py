"""
Trip Planning API Views.

Provides REST API endpoints for:
- Health check
- Trip planning with HOS calculations
- ELD log generation
"""

import logging
import uuid
from datetime import datetime
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .serializers import (
    TripPlanInputSerializer,
    TripPlanOutputSerializer,
    HealthCheckSerializer
)
from .services import RouteService, HOSService, ELDLogService
from .services.route_service import RouteServiceError

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """
    Health check endpoint for monitoring and load balancers.
    
    GET /api/health/
    """
    
    def get(self, request):
        """Return health status of the API."""
        data = {
            'status': 'healthy',
            'message': 'ELD Trip Planner API is running',
            'version': '1.0.0',
            'timestamp': datetime.now()
        }
        serializer = HealthCheckSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


class TripPlanView(APIView):
    """
    Main trip planning endpoint.
    
    POST /api/trips/plan/
    
    Takes trip inputs and returns:
    - Route with coordinates
    - HOS-compliant stop schedule
    - ELD daily log sheets
    """
    
    def post(self, request):
        """
        Plan a trip with HOS calculations and ELD log generation.
        
        Request Body:
        {
            "current_location": "Chicago, IL",
            "pickup_location": "Indianapolis, IN",
            "dropoff_location": "Nashville, TN",
            "current_cycle_used_hours": 0
        }
        
        Response:
        {
            "trip_id": "uuid",
            "total_distance_miles": 456.2,
            "total_trip_duration_hours": 12.5,
            "estimated_days": 2,
            "route_coordinates": [...],
            "planned_stops": [...],
            "daily_logs": [...]
        }
        """
        # Validate input
        input_serializer = TripPlanInputSerializer(data=request.data)
        if not input_serializer.is_valid():
            return Response(
                {'error': 'Validation failed', 'details': input_serializer.errors},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        validated_data = input_serializer.validated_data
        
        try:
            # Step 1: Calculate route
            logger.info(
                f"Planning trip: {validated_data['current_location']} -> "
                f"{validated_data['pickup_location']} -> "
                f"{validated_data['dropoff_location']}"
            )
            
            route_service = RouteService()
            route_data = route_service.get_full_trip_route(
                current_location=validated_data['current_location'],
                pickup_location=validated_data['pickup_location'],
                dropoff_location=validated_data['dropoff_location']
            )
            
            # Calculate pickup distance (first segment)
            pickup_miles = route_data['segments'][0]['distance_miles'] if route_data['segments'] else 0
            
            # Step 2: Calculate HOS-compliant schedule
            hos_service = HOSService()
            hos_plan = hos_service.calculate_trip_plan(
                total_distance_miles=route_data['total_distance_miles'],
                pickup_miles_from_start=pickup_miles,
                current_cycle_used_hours=validated_data['current_cycle_used_hours'],
                departure_time=datetime.now(),
                locations=route_data['locations'],
                route_coordinates=route_data['route_coordinates'],
                adverse_conditions=validated_data.get('use_adverse_driving_conditions', False),
                short_haul_cdl=validated_data.get('use_short_haul_cdl', False),
                split_sleeper=validated_data.get('use_split_sleeper', False)
            )
            
            # Step 3: Generate ELD logs
            eld_service = ELDLogService()
            daily_logs = eld_service.generate_logs_json(
                hos_plan=hos_plan,
                locations=route_data['locations']
            )
            
            # Step 4: Build response
            response_data = {
                'trip_id': str(uuid.uuid4()),
                'total_distance_miles': round(route_data['total_distance_miles'], 1),
                'total_trip_duration_hours': round(
                    (hos_plan.arrival_time - hos_plan.departure_time).total_seconds() / 3600, 1
                ),
                'estimated_days': hos_plan.total_trip_days,
                'route_coordinates': route_data['route_coordinates'],
                'route_polyline': route_data['encoded_polyline'],
                'planned_stops': [
                    {
                        'stop_type': stop.stop_type,
                        'location': stop.location,
                        'latitude': stop.latitude,
                        'longitude': stop.longitude,
                        'arrival_time': stop.arrival_time.isoformat(),
                        'departure_time': stop.departure_time.isoformat(),
                        'duration_hours': stop.duration_hours,
                        'miles_from_start': round(stop.miles_from_start, 1),
                        'day_number': stop.day_number,
                        'remarks': stop.remarks
                    }
                    for stop in hos_plan.planned_stops
                ],
                'daily_logs': daily_logs,
                'total_driving_hours': round(hos_plan.total_driving_hours, 1),
                'total_on_duty_hours': round(hos_plan.total_on_duty_hours, 1),
                'total_rest_stops': sum(
                    1 for s in hos_plan.planned_stops if s.stop_type == 'rest'
                ),
                'total_fuel_stops': sum(
                    1 for s in hos_plan.planned_stops if s.stop_type == 'fuel'
                ),
                'departure_time': hos_plan.departure_time.isoformat(),
                'estimated_arrival_time': hos_plan.arrival_time.isoformat(),
                'cycle_hours_remaining': round(hos_plan.cycle_hours_remaining, 1)
            }
            
            logger.info(
                f"Trip planned successfully: {response_data['total_distance_miles']} miles, "
                f"{response_data['estimated_days']} days"
            )
            
            return Response(response_data, status=status.HTTP_200_OK)
            
        except RouteServiceError as e:
            logger.error(f"Route calculation failed: {e}")
            return Response(
                {'error': 'Route calculation failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.exception(f"Trip planning failed: {e}")
            return Response(
                {'error': 'Trip planning failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class RouteOnlyView(APIView):
    """
    Route calculation endpoint (without HOS/ELD).
    
    GET /api/trips/route/
    
    Useful for map preview before full trip planning.
    """
    
    def get(self, request):
        """
        Get route coordinates for map display.
        
        Query params:
        - current_location: Starting address
        - pickup_location: Pickup address
        - dropoff_location: Destination address
        """
        current_location = request.query_params.get('current_location')
        pickup_location = request.query_params.get('pickup_location')
        dropoff_location = request.query_params.get('dropoff_location')
        
        if not all([current_location, pickup_location, dropoff_location]):
            return Response(
                {'error': 'Missing required parameters: current_location, pickup_location, dropoff_location'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            route_service = RouteService()
            route_data = route_service.get_full_trip_route(
                current_location=current_location,
                pickup_location=pickup_location,
                dropoff_location=dropoff_location
            )
            
            return Response({
                'locations': route_data['locations'],
                'total_distance_miles': round(route_data['total_distance_miles'], 1),
                'total_duration_hours': round(route_data['total_duration_hours'], 1),
                'route_coordinates': route_data['route_coordinates'],
                'encoded_polyline': route_data['encoded_polyline'],
                'segments': route_data['segments']
            }, status=status.HTTP_200_OK)
            
        except RouteServiceError as e:
            logger.error(f"Route calculation failed: {e}")
            return Response(
                {'error': 'Route calculation failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ELDLogDetailView(APIView):
    """
    Get detailed ELD log for a specific day.
    
    GET /api/trips/{trip_id}/logs/{day_number}/
    
    Returns detailed log data for rendering.
    """
    
    def get(self, request, trip_id, day_number):
        """Get ELD log for a specific day of a trip."""
        # In production, this would fetch from database
        # For now, return example structure
        return Response({
            'message': 'This endpoint requires trip data to be stored in database',
            'trip_id': trip_id,
            'day_number': day_number,
            'note': 'Implement Trip model persistence for full functionality'
        }, status=status.HTTP_501_NOT_IMPLEMENTED)


@api_view(['GET'])
def api_root(request):
    """
    API root endpoint with available endpoints list.
    
    GET /api/
    """
    return Response({
        'status': 'ELD Trip Planner API v1.0',
        'endpoints': {
            'health': '/api/health/',
            'plan_trip': '/api/trips/plan/',
            'get_route': '/api/trips/route/',
        },
        'documentation': {
            'plan_trip': {
                'method': 'POST',
                'body': {
                    'current_location': 'string - Starting address',
                    'pickup_location': 'string - Pickup address',
                    'dropoff_location': 'string - Destination address',
                    'current_cycle_used_hours': 'number - Hours used in 70h/8-day cycle (0-70)'
                }
            }
        }
    })
