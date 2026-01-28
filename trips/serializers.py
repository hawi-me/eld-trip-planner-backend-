"""
Serializers for the Trip Planning API.

Handles validation and serialization of trip data, stops, and ELD logs.
"""

from rest_framework import serializers
from .models import Trip, TripStop, ELDLogEntry, DailyLogSummary


class TripPlanInputSerializer(serializers.Serializer):
    """
    Input serializer for trip planning requests.
    """
    current_location = serializers.CharField(
        max_length=500,
        help_text="Starting location address (e.g., 'Chicago, IL')"
    )
    pickup_location = serializers.CharField(
        max_length=500,
        help_text="Pickup location address"
    )
    dropoff_location = serializers.CharField(
        max_length=500,
        help_text="Dropoff location address"
    )
    current_cycle_used_hours = serializers.FloatField(
        min_value=0,
        max_value=70,
        default=0,
        help_text="Hours already used in the 8-day/70-hour cycle"
    )

    # Optional planning flags to reflect FMCSA exceptions/config
    use_adverse_driving_conditions = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Apply the adverse driving conditions exception (+2h driving/window)"
    )
    use_short_haul_cdl = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Use CDL short-haul exception (no 30-min break, 150 air-mile ops)"
    )
    use_split_sleeper = serializers.BooleanField(
        required=False,
        default=False,
        help_text="Allow split sleeper berth pair (7/3 or 8/2) that doesn't count to 14h window"
    )

    def validate(self, data):
        """Validate that all locations are different."""
        locations = [
            data['current_location'].lower().strip(),
            data['pickup_location'].lower().strip(),
            data['dropoff_location'].lower().strip()
        ]
        
        if locations[0] == locations[1]:
            raise serializers.ValidationError({
                'pickup_location': 'Pickup location cannot be the same as current location.'
            })
        
        if locations[1] == locations[2]:
            raise serializers.ValidationError({
                'dropoff_location': 'Dropoff location cannot be the same as pickup location.'
            })
        
        return data


class StopSerializer(serializers.Serializer):
    """
    Serializer for planned stops in the trip response.
    """
    stop_type = serializers.CharField()
    location = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    arrival_time = serializers.DateTimeField()
    departure_time = serializers.DateTimeField()
    duration_hours = serializers.FloatField()
    miles_from_start = serializers.FloatField()
    day_number = serializers.IntegerField()
    remarks = serializers.CharField(required=False, allow_blank=True)


class ELDLogEntrySerializer(serializers.Serializer):
    """
    Serializer for individual ELD log entries.
    """
    start_time = serializers.CharField(help_text="Start time in HH:MM format")
    end_time = serializers.CharField(help_text="End time in HH:MM format")
    duty_status = serializers.ChoiceField(choices=[
        ('off_duty', 'Off Duty'),
        ('sleeper_berth', 'Sleeper Berth'),
        ('driving', 'Driving'),
        ('on_duty_not_driving', 'On Duty (Not Driving)'),
    ])
    duration_hours = serializers.FloatField()
    location = serializers.CharField(required=False, allow_blank=True)
    remarks = serializers.CharField(required=False, allow_blank=True)


class DailyLogSerializer(serializers.Serializer):
    """
    Serializer for daily ELD log sheets.
    """
    date = serializers.DateField()
    day_number = serializers.IntegerField()
    entries = ELDLogEntrySerializer(many=True)
    summary = serializers.DictField(child=serializers.FloatField())
    total_miles = serializers.FloatField()
    starting_location = serializers.CharField()
    ending_location = serializers.CharField()


class RouteCoordinateSerializer(serializers.Serializer):
    """
    Serializer for route coordinates.
    """
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()


class TripPlanOutputSerializer(serializers.Serializer):
    """
    Output serializer for trip planning response.
    """
    trip_id = serializers.UUIDField()
    total_distance_miles = serializers.FloatField()
    total_trip_duration_hours = serializers.FloatField()
    estimated_days = serializers.IntegerField()
    route_coordinates = RouteCoordinateSerializer(many=True)
    route_polyline = serializers.CharField(
        required=False,
        help_text="Encoded polyline for the route"
    )
    planned_stops = StopSerializer(many=True)
    daily_logs = DailyLogSerializer(many=True)
    
    # Summary information
    total_driving_hours = serializers.FloatField()
    total_on_duty_hours = serializers.FloatField()
    total_rest_stops = serializers.IntegerField()
    total_fuel_stops = serializers.IntegerField()
    
    # Departure and arrival
    departure_time = serializers.DateTimeField()
    estimated_arrival_time = serializers.DateTimeField()


class TripModelSerializer(serializers.ModelSerializer):
    """
    Full model serializer for Trip persistence.
    """
    class Meta:
        model = Trip
        fields = '__all__'
        read_only_fields = ['id', 'created_at', 'updated_at']


class TripStopModelSerializer(serializers.ModelSerializer):
    """
    Model serializer for TripStop persistence.
    """
    class Meta:
        model = TripStop
        fields = '__all__'
        read_only_fields = ['id']


class ELDLogEntryModelSerializer(serializers.ModelSerializer):
    """
    Model serializer for ELDLogEntry persistence.
    """
    duration_hours = serializers.ReadOnlyField()
    
    class Meta:
        model = ELDLogEntry
        fields = '__all__'
        read_only_fields = ['id']


class DailyLogSummaryModelSerializer(serializers.ModelSerializer):
    """
    Model serializer for DailyLogSummary persistence.
    """
    class Meta:
        model = DailyLogSummary
        fields = '__all__'
        read_only_fields = ['id']


class HealthCheckSerializer(serializers.Serializer):
    """
    Serializer for health check response.
    """
    status = serializers.CharField()
    message = serializers.CharField()
    version = serializers.CharField()
    timestamp = serializers.DateTimeField()
