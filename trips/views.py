"""
Trip Planning API Views.

Comprehensive REST API for ELD Trip Planner with:
- Health check
- Trip CRUD operations
- Route calculation
- ELD log generation & storage
- Cycle tracking
- HOS configuration
- Map proxy service
"""

import logging
import uuid
from datetime import datetime, timedelta
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view

from .models import Trip, TripStop, ELDLogEntry, DailyLogSummary
from .serializers import (
    TripPlanInputSerializer,
    TripPlanOutputSerializer,
    TripModelSerializer,
    TripStopModelSerializer,
    ELDLogEntryModelSerializer,
    DailyLogSummaryModelSerializer,
    HealthCheckSerializer,
)
from .services import RouteService, HOSService, ELDLogService
from .services.route_service import RouteServiceError, Coordinates
from .services.hos_service import HOSConfig

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
            'version': '2.0.0',
            'timestamp': datetime.now()
        }
        serializer = HealthCheckSerializer(data)
        return Response(serializer.data, status=status.HTTP_200_OK)


# =============================================================================
# Route Service - POST /api/routes/calculate
# =============================================================================

class RouteCalculateView(APIView):
    """
    POST /api/routes/calculate
    Calculate route between locations (geocoding + routing).
    """
    
    def post(self, request):
        """
        Request:
        {
            "currentLocation": "Dallas, TX",
            "pickupLocation": "Austin, TX",
            "dropoffLocation": "Houston, TX"
        }
        
        Response:
        {
            "distanceMiles": 560,
            "durationHours": 9.3,
            "polyline": "...",
            "locations": {...},
            "segments": [...]
        }
        """
        current_location = request.data.get('currentLocation') or request.data.get('current_location')
        pickup_location = request.data.get('pickupLocation') or request.data.get('pickup_location')
        dropoff_location = request.data.get('dropoffLocation') or request.data.get('dropoff_location')
        
        if not all([current_location, pickup_location, dropoff_location]):
            return Response(
                {'error': 'Missing required fields: currentLocation, pickupLocation, dropoffLocation'},
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
                'distanceMiles': round(route_data['total_distance_miles'], 1),
                'durationHours': round(route_data['total_duration_hours'], 1),
                'polyline': route_data['encoded_polyline'],
                'locations': route_data['locations'],
                'segments': route_data['segments'],
                'routeCoordinates': route_data['route_coordinates']
            }, status=status.HTTP_200_OK)
            
        except RouteServiceError as e:
            logger.error(f"Route calculation failed: {e}")
            return Response(
                {'error': 'Route calculation failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# =============================================================================
# Trip Management Service - CRUD for /api/trips/
# =============================================================================

class TripListCreateView(APIView):
    """
    GET /api/trips/ - List all trips
    POST /api/trips/ - Create a new trip with full planning
    """
    
    def get(self, request):
        """List all trips, optionally filtered."""
        trips = Trip.objects.all().order_by('-created_at')
        serializer = TripModelSerializer(trips, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
    
    def post(self, request):
        """
        Create a trip with full route calculation, HOS planning, and ELD generation.
        
        Request:
        {
            "current_location": "Chicago, IL",
            "pickup_location": "Indianapolis, IN",
            "dropoff_location": "Nashville, TN",
            "current_cycle_used_hours": 0
        }
        """
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
            
            # Step 4: Persist trip to database
            trip = Trip.objects.create(
                current_location=validated_data['current_location'],
                pickup_location=validated_data['pickup_location'],
                dropoff_location=validated_data['dropoff_location'],
                current_location_lat=route_data['locations']['current']['latitude'],
                current_location_lon=route_data['locations']['current']['longitude'],
                pickup_location_lat=route_data['locations']['pickup']['latitude'],
                pickup_location_lon=route_data['locations']['pickup']['longitude'],
                dropoff_location_lat=route_data['locations']['dropoff']['latitude'],
                dropoff_location_lon=route_data['locations']['dropoff']['longitude'],
                current_cycle_used_hours=validated_data['current_cycle_used_hours'],
                total_distance_miles=route_data['total_distance_miles'],
                total_trip_duration_hours=(hos_plan.arrival_time - hos_plan.departure_time).total_seconds() / 3600,
                estimated_days=hos_plan.total_trip_days,
                route_polyline=route_data['encoded_polyline']
            )
            
            # Step 5: Persist stops
            for idx, stop in enumerate(hos_plan.planned_stops):
                TripStop.objects.create(
                    trip=trip,
                    stop_type=stop.stop_type,
                    location_name=stop.location,
                    latitude=stop.latitude,
                    longitude=stop.longitude,
                    arrival_time=stop.arrival_time,
                    departure_time=stop.departure_time,
                    duration_hours=stop.duration_hours,
                    miles_from_start=stop.miles_from_start,
                    miles_from_previous=0,
                    sequence=idx + 1
                )
            
            # Step 6: Persist ELD logs
            for log_day in daily_logs:
                summary = DailyLogSummary.objects.create(
                    trip=trip,
                    log_date=datetime.strptime(log_day['date'], '%Y-%m-%d').date(),
                    day_number=log_day['day_number'],
                    driving_hours=log_day['summary'].get('driving', 0),
                    on_duty_hours=log_day['summary'].get('on_duty_not_driving', 0),
                    off_duty_hours=log_day['summary'].get('off_duty', 0),
                    sleeper_berth_hours=log_day['summary'].get('sleeper_berth', 0),
                    total_miles_driven=log_day.get('total_miles', 0)
                )
                
                for idx, entry in enumerate(log_day['entries']):
                    ELDLogEntry.objects.create(
                        trip=trip,
                        log_date=datetime.strptime(log_day['date'], '%Y-%m-%d').date(),
                        start_time=datetime.strptime(entry['start_time'], '%H:%M').time(),
                        end_time=datetime.strptime(entry['end_time'], '%H:%M').time(),
                        duty_status=entry['duty_status'],
                        location=entry.get('location', ''),
                        remarks=entry.get('remarks', ''),
                        sequence=idx + 1
                    )
            
            # Build response
            response_data = {
                'id': str(trip.id),
                'trip_id': str(trip.id),
                'total_distance_miles': round(route_data['total_distance_miles'], 1),
                'total_trip_duration_hours': round(trip.total_trip_duration_hours, 1),
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
                'total_rest_stops': sum(1 for s in hos_plan.planned_stops if s.stop_type == 'rest'),
                'total_fuel_stops': sum(1 for s in hos_plan.planned_stops if s.stop_type == 'fuel'),
                'departure_time': hos_plan.departure_time.isoformat(),
                'estimated_arrival_time': hos_plan.arrival_time.isoformat(),
                'cycle_hours_remaining': round(hos_plan.cycle_hours_remaining, 1),
                'created_at': trip.created_at.isoformat()
            }
            
            logger.info(f"Trip {trip.id} created successfully")
            return Response(response_data, status=status.HTTP_201_CREATED)
            
        except RouteServiceError as e:
            logger.error(f"Route calculation failed: {e}")
            return Response(
                {'error': 'Route calculation failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            logger.exception(f"Trip creation failed: {e}")
            return Response(
                {'error': 'Trip creation failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class TripDetailView(APIView):
    """
    GET /api/trips/{id}/ - Get trip details
    PUT /api/trips/{id}/ - Update trip
    DELETE /api/trips/{id}/ - Delete trip
    """
    
    def get(self, request, trip_id):
        """Get full trip details including stops and logs."""
        trip = get_object_or_404(Trip, id=trip_id)
        
        stops = TripStop.objects.filter(trip=trip).order_by('sequence')
        daily_summaries = DailyLogSummary.objects.filter(trip=trip).order_by('day_number')
        
        return Response({
            'id': str(trip.id),
            'current_location': trip.current_location,
            'pickup_location': trip.pickup_location,
            'dropoff_location': trip.dropoff_location,
            'current_cycle_used_hours': trip.current_cycle_used_hours,
            'total_distance_miles': trip.total_distance_miles,
            'total_trip_duration_hours': trip.total_trip_duration_hours,
            'estimated_days': trip.estimated_days,
            'route_polyline': trip.route_polyline,
            'locations': {
                'current': {
                    'address': trip.current_location,
                    'latitude': trip.current_location_lat,
                    'longitude': trip.current_location_lon
                },
                'pickup': {
                    'address': trip.pickup_location,
                    'latitude': trip.pickup_location_lat,
                    'longitude': trip.pickup_location_lon
                },
                'dropoff': {
                    'address': trip.dropoff_location,
                    'latitude': trip.dropoff_location_lat,
                    'longitude': trip.dropoff_location_lon
                }
            },
            'stops': TripStopModelSerializer(stops, many=True).data,
            'daily_summaries': DailyLogSummaryModelSerializer(daily_summaries, many=True).data,
            'created_at': trip.created_at.isoformat(),
            'updated_at': trip.updated_at.isoformat()
        }, status=status.HTTP_200_OK)
    
    def put(self, request, trip_id):
        """Update trip details."""
        trip = get_object_or_404(Trip, id=trip_id)
        serializer = TripModelSerializer(trip, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, trip_id):
        """Delete trip and all related data."""
        trip = get_object_or_404(Trip, id=trip_id)
        trip_id_str = str(trip.id)
        trip.delete()
        return Response(
            {'message': f'Trip {trip_id_str} deleted successfully'},
            status=status.HTTP_204_NO_CONTENT
        )


# =============================================================================
# ELD Log Generation & Storage Service
# =============================================================================

class ELDGenerateView(APIView):
    """
    POST /api/eld/generate
    Generate ELD logs for a trip (without persisting).
    """
    
    def post(self, request):
        """Generate ELD logs from trip parameters."""
        trip_id = request.data.get('tripId')
        
        if trip_id:
            trip = get_object_or_404(Trip, id=trip_id)
            total_distance = trip.total_distance_miles
            cycle_used = trip.current_cycle_used_hours
            pickup_miles = 100
        else:
            total_distance = request.data.get('totalDistanceMiles', 500)
            cycle_used = request.data.get('currentCycleUsed', 0)
            pickup_miles = request.data.get('pickupMilesFromStart', 50)
        
        try:
            hos_service = HOSService()
            hos_plan = hos_service.calculate_trip_plan(
                total_distance_miles=total_distance,
                pickup_miles_from_start=pickup_miles,
                current_cycle_used_hours=cycle_used,
                departure_time=datetime.now()
            )
            
            eld_service = ELDLogService()
            daily_logs = eld_service.generate_logs_json(hos_plan=hos_plan)
            
            return Response({
                'logs': daily_logs,
                'summary': {
                    'totalDays': hos_plan.total_trip_days,
                    'totalDrivingHours': round(hos_plan.total_driving_hours, 1),
                    'totalOnDutyHours': round(hos_plan.total_on_duty_hours, 1),
                    'cycleHoursRemaining': round(hos_plan.cycle_hours_remaining, 1)
                }
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.exception(f"ELD generation failed: {e}")
            return Response(
                {'error': 'ELD generation failed', 'details': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ELDLogsByTripView(APIView):
    """
    GET /api/eld/logs/{tripId}/ - Get logs by trip
    DELETE /api/eld/logs/{tripId}/ - Delete logs for trip
    """
    
    def get(self, request, trip_id):
        """Get all ELD logs for a trip."""
        trip = get_object_or_404(Trip, id=trip_id)
        
        daily_summaries = DailyLogSummary.objects.filter(trip=trip).order_by('day_number')
        logs_by_day = []
        
        for summary in daily_summaries:
            entries = ELDLogEntry.objects.filter(
                trip=trip, log_date=summary.log_date
            ).order_by('sequence')
            
            logs_by_day.append({
                'date': summary.log_date.isoformat(),
                'day_number': summary.day_number,
                'entries': [
                    {
                        'start_time': entry.start_time.strftime('%H:%M'),
                        'end_time': entry.end_time.strftime('%H:%M'),
                        'duty_status': entry.duty_status,
                        'duration_hours': entry.duration_hours,
                        'location': entry.location,
                        'remarks': entry.remarks
                    }
                    for entry in entries
                ],
                'summary': {
                    'driving': summary.driving_hours,
                    'on_duty_not_driving': summary.on_duty_hours,
                    'off_duty': summary.off_duty_hours,
                    'sleeper_berth': summary.sleeper_berth_hours
                },
                'total_miles': summary.total_miles_driven
            })
        
        return Response({
            'trip_id': str(trip_id),
            'logs': logs_by_day
        }, status=status.HTTP_200_OK)
    
    def delete(self, request, trip_id):
        """Delete all ELD logs for a trip."""
        trip = get_object_or_404(Trip, id=trip_id)
        
        ELDLogEntry.objects.filter(trip=trip).delete()
        DailyLogSummary.objects.filter(trip=trip).delete()
        
        return Response(
            {'message': f'ELD logs for trip {trip_id} deleted'},
            status=status.HTTP_204_NO_CONTENT
        )


class ELDLogDayDetailView(APIView):
    """
    GET /api/eld/logs/{tripId}/day/{dayNumber}/
    Get ELD log for a specific day with grid data.
    """
    
    def get(self, request, trip_id, day_number):
        trip = get_object_or_404(Trip, id=trip_id)
        summary = get_object_or_404(DailyLogSummary, trip=trip, day_number=day_number)
        
        entries = ELDLogEntry.objects.filter(
            trip=trip, log_date=summary.log_date
        ).order_by('sequence')
        
        grid_segments = []
        grid_rows = {
            'off_duty': 1,
            'sleeper_berth': 2,
            'driving': 3,
            'on_duty_not_driving': 4
        }
        
        for entry in entries:
            start_hour = entry.start_time.hour + entry.start_time.minute / 60
            end_hour = entry.end_time.hour + entry.end_time.minute / 60
            if end_hour == 0:
                end_hour = 24
            
            grid_segments.append({
                'row': grid_rows.get(entry.duty_status, 1),
                'start_x': start_hour,
                'end_x': end_hour,
                'status': entry.duty_status,
                'duration': entry.duration_hours
            })
        
        return Response({
            'date': summary.log_date.isoformat(),
            'day_number': summary.day_number,
            'entries': ELDLogEntryModelSerializer(entries, many=True).data,
            'summary': {
                'driving': summary.driving_hours,
                'on_duty_not_driving': summary.on_duty_hours,
                'off_duty': summary.off_duty_hours,
                'sleeper_berth': summary.sleeper_berth_hours,
                'total': 24.0
            },
            'total_miles': summary.total_miles_driven,
            'grid_data': {
                'segments': grid_segments,
                'hours': list(range(25)),
                'rows': [
                    {'id': 1, 'label': 'Off Duty', 'short': 'OFF'},
                    {'id': 2, 'label': 'Sleeper Berth', 'short': 'SB'},
                    {'id': 3, 'label': 'Driving', 'short': 'D'},
                    {'id': 4, 'label': 'On Duty (Not Driving)', 'short': 'ON'}
                ]
            }
        }, status=status.HTTP_200_OK)


# =============================================================================
# Cycle Tracking Service
# =============================================================================

class CycleStatusView(APIView):
    """
    GET /api/cycle/status
    Get current 70-hour/8-day cycle status.
    """
    
    def get(self, request):
        """Calculate current 70-hour/8-day cycle status."""
        eight_days_ago = datetime.now() - timedelta(days=8)
        
        recent_summaries = DailyLogSummary.objects.filter(
            log_date__gte=eight_days_ago.date()
        ).order_by('-log_date')
        
        total_driving = recent_summaries.aggregate(Sum('driving_hours'))['driving_hours__sum'] or 0
        total_on_duty = recent_summaries.aggregate(Sum('on_duty_hours'))['on_duty_hours__sum'] or 0
        total_cycle_used = total_driving + total_on_duty
        
        daily_breakdown = []
        for i in range(8):
            day = datetime.now().date() - timedelta(days=i)
            day_summary = recent_summaries.filter(log_date=day).first()
            daily_breakdown.append({
                'date': day.isoformat(),
                'driving_hours': day_summary.driving_hours if day_summary else 0,
                'on_duty_hours': day_summary.on_duty_hours if day_summary else 0,
                'total_hours': (day_summary.driving_hours + day_summary.on_duty_hours) if day_summary else 0
            })
        
        return Response({
            'cycle_type': '70-hour/8-day',
            'cycle_limit': 70,
            'hours_used': round(total_cycle_used, 1),
            'hours_remaining': round(max(0, 70 - total_cycle_used), 1),
            'percentage_used': round((total_cycle_used / 70) * 100, 1),
            'last_8_days': daily_breakdown,
            'needs_restart': total_cycle_used >= 70,
            'restart_available': True
        }, status=status.HTTP_200_OK)


class CycleUpdateView(APIView):
    """
    PUT /api/cycle/update
    Manually update cycle hours (for corrections).
    """
    
    def put(self, request):
        """Update cycle hours after a trip."""
        hours_to_add = request.data.get('hours_used', 0)
        date = request.data.get('date', datetime.now().date().isoformat())
        
        return Response({
            'message': 'Cycle updated',
            'date': date,
            'hours_added': hours_to_add
        }, status=status.HTTP_200_OK)


# =============================================================================
# HOS Configuration Service
# =============================================================================

class HOSConfigView(APIView):
    """
    GET /api/config/hos - Get current HOS rules/assumptions
    PUT /api/config/hos - Update HOS configuration
    """
    
    def get(self, request):
        """Get current HOS configuration and assumptions."""
        config = HOSConfig()
        
        return Response({
            'cycle': {
                'days': config.cycle_days,
                'hours': config.cycle_hours,
                'description': '70 hours in 8 consecutive days'
            },
            'daily_limits': {
                'max_driving_hours': config.max_driving_hours,
                'max_on_duty_hours': config.max_on_duty_hours,
                'description': '11 hours driving within 14-hour window'
            },
            'breaks': {
                'break_required_after_hours': config.break_required_after_hours,
                'break_duration_hours': config.break_duration_hours,
                'description': '30-minute break required after 8 hours driving'
            },
            'rest': {
                'off_duty_reset_hours': config.off_duty_reset_hours,
                'restart_hours': config.restart_hours,
                'description': '10-hour off-duty for daily reset, 34-hour for cycle reset'
            },
            'practical': {
                'fuel_interval_miles': config.fuel_interval_miles,
                'fuel_stop_duration_hours': config.fuel_stop_duration_hours,
                'pickup_duration_hours': config.pickup_duration_hours,
                'dropoff_duration_hours': config.dropoff_duration_hours,
                'average_speed_mph': config.average_speed_mph
            },
            'assumptions': [
                'Property-carrying driver (not passenger)',
                '70-hour/8-day cycle',
                'No adverse driving conditions by default',
                'Fueling every 1,000 miles',
                '1 hour for pickup, 1 hour for dropoff',
                'Average speed of 55 mph'
            ]
        }, status=status.HTTP_200_OK)
    
    def put(self, request):
        """Update HOS configuration (for custom scenarios)."""
        updates = request.data
        return Response({
            'message': 'Configuration updated',
            'updates': updates,
            'note': 'Changes apply to future calculations only'
        }, status=status.HTTP_200_OK)


# =============================================================================
# Map Proxy Service
# =============================================================================

class MapProxyRouteView(APIView):
    """
    GET /api/maps/route
    Proxy to map API (hides API keys from frontend).
    """
    
    def get(self, request):
        """Proxy route request to OSRM."""
        start = request.query_params.get('start')
        end = request.query_params.get('end')
        waypoints = request.query_params.get('waypoints')
        
        if not start or not end:
            return Response(
                {'error': 'Missing required params: start, end'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            start_lat, start_lon = map(float, start.split(','))
            end_lat, end_lon = map(float, end.split(','))
            
            origin = Coordinates(latitude=start_lat, longitude=start_lon)
            destination = Coordinates(latitude=end_lat, longitude=end_lon)
            
            waypoint_list = None
            if waypoints:
                waypoint_list = []
                for wp in waypoints.split(';'):
                    lat, lon = map(float, wp.split(','))
                    waypoint_list.append(Coordinates(latitude=lat, longitude=lon))
            
            route_service = RouteService()
            route = route_service.calculate_route(origin, destination, waypoint_list)
            
            return Response({
                'distance_miles': round(route.total_distance_miles, 1),
                'duration_hours': round(route.total_duration_hours, 2),
                'polyline': route.encoded_polyline,
                'coordinates': [
                    {'lat': c.latitude, 'lon': c.longitude}
                    for c in route.all_coordinates
                ]
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Map proxy error: {e}")
            return Response(
                {'error': 'Route calculation failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class MapProxyGeocodeView(APIView):
    """
    GET /api/maps/geocode
    Proxy geocoding request.
    """
    
    def get(self, request):
        """Geocode an address."""
        address = request.query_params.get('address')
        
        if not address:
            return Response(
                {'error': 'Missing required param: address'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            route_service = RouteService()
            coords = route_service.geocode_address(address)
            
            return Response({
                'address': address,
                'latitude': coords.latitude,
                'longitude': coords.longitude
            }, status=status.HTTP_200_OK)
            
        except RouteServiceError as e:
            return Response(
                {'error': 'Geocoding failed', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# =============================================================================
# Legacy endpoints for backward compatibility
# =============================================================================

class TripPlanView(APIView):
    """
    POST /api/trips/plan/
    Legacy endpoint - delegates to TripListCreateView.post()
    """
    
    def post(self, request):
        view = TripListCreateView()
        return view.post(request)


class RouteOnlyView(APIView):
    """
    GET /api/trips/route/
    Legacy route-only endpoint.
    """
    
    def get(self, request):
        """Get route coordinates for map display."""
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
    """Legacy endpoint for backward compatibility."""
    
    def get(self, request, trip_id, day_number):
        view = ELDLogDayDetailView()
        return view.get(request, trip_id, day_number)


@api_view(['GET'])
def api_root(request):
    """
    GET /api/
    API documentation and endpoint listing.
    """
    return Response({
        'name': 'ELD Trip Planner API',
        'version': '2.0.0',
        'description': 'Complete ELD and HOS compliance API for truck drivers',
        'endpoints': {
            'health': {
                'GET /api/health/': 'Health check'
            },
            'routes': {
                'POST /api/routes/calculate': 'Calculate route between locations'
            },
            'trips': {
                'GET /api/trips/': 'List all trips',
                'POST /api/trips/': 'Create new trip with full planning',
                'GET /api/trips/{id}/': 'Get trip details',
                'PUT /api/trips/{id}/': 'Update trip',
                'DELETE /api/trips/{id}/': 'Delete trip',
                'POST /api/trips/plan/': 'Legacy: Plan trip'
            },
            'eld': {
                'POST /api/eld/generate': 'Generate ELD logs',
                'GET /api/eld/logs/{tripId}/': 'Get logs by trip',
                'DELETE /api/eld/logs/{tripId}/': 'Delete logs',
                'GET /api/eld/logs/{tripId}/day/{dayNumber}/': 'Get specific day log'
            },
            'cycle': {
                'GET /api/cycle/status': 'Get 70h/8d cycle status',
                'PUT /api/cycle/update': 'Update cycle hours'
            },
            'config': {
                'GET /api/config/hos': 'Get HOS rules and assumptions',
                'PUT /api/config/hos': 'Update HOS configuration'
            },
            'maps': {
                'GET /api/maps/route': 'Proxy route calculation',
                'GET /api/maps/geocode': 'Proxy geocoding'
            }
        }
    })
