"""
Trip Models for ELD Trip Planner.

Stores trip data, stops, and ELD log entries for persistence and historical tracking.
"""

from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
import uuid


class Trip(models.Model):
    """
    Represents a planned trip with origin, pickup, and dropoff locations.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    
    # Location inputs
    current_location = models.CharField(max_length=500, help_text="Starting location address")
    pickup_location = models.CharField(max_length=500, help_text="Pickup location address")
    dropoff_location = models.CharField(max_length=500, help_text="Dropoff location address")
    
    # Coordinates (stored after geocoding)
    current_location_lat = models.FloatField(null=True, blank=True)
    current_location_lon = models.FloatField(null=True, blank=True)
    pickup_location_lat = models.FloatField(null=True, blank=True)
    pickup_location_lon = models.FloatField(null=True, blank=True)
    dropoff_location_lat = models.FloatField(null=True, blank=True)
    dropoff_location_lon = models.FloatField(null=True, blank=True)
    
    # HOS tracking
    current_cycle_used_hours = models.FloatField(
        default=0,
        validators=[MinValueValidator(0), MaxValueValidator(70)],
        help_text="Hours already used in the 8-day cycle"
    )
    
    # Calculated route data
    total_distance_miles = models.FloatField(null=True, blank=True)
    total_trip_duration_hours = models.FloatField(null=True, blank=True)
    estimated_days = models.IntegerField(null=True, blank=True)
    route_polyline = models.TextField(null=True, blank=True, help_text="Encoded route polyline")
    
    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Trip'
        verbose_name_plural = 'Trips'
    
    def __str__(self):
        return f"Trip {self.id}: {self.current_location} → {self.dropoff_location}"


class TripStop(models.Model):
    """
    Represents a planned stop during a trip (rest stops, fuel stops, etc.).
    """
    STOP_TYPE_CHOICES = [
        ('rest', 'Rest Stop (10-hour off-duty)'),
        ('break', '30-Minute Break'),
        ('fuel', 'Fuel Stop'),
        ('pickup', 'Pickup'),
        ('dropoff', 'Dropoff'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='stops')
    
    stop_type = models.CharField(max_length=20, choices=STOP_TYPE_CHOICES)
    location_name = models.CharField(max_length=500)
    latitude = models.FloatField()
    longitude = models.FloatField()
    
    # Timing
    arrival_time = models.DateTimeField(help_text="Expected arrival time")
    departure_time = models.DateTimeField(help_text="Expected departure time")
    duration_hours = models.FloatField(help_text="Stop duration in hours")
    
    # Distance tracking
    miles_from_start = models.FloatField(help_text="Miles from trip start")
    miles_from_previous = models.FloatField(help_text="Miles from previous stop")
    
    # Order in the trip
    sequence = models.IntegerField(help_text="Order of this stop in the trip")
    
    class Meta:
        ordering = ['trip', 'sequence']
        verbose_name = 'Trip Stop'
        verbose_name_plural = 'Trip Stops'
    
    def __str__(self):
        return f"{self.get_stop_type_display()} at {self.location_name}"


class ELDLogEntry(models.Model):
    """
    Represents a single ELD log entry for a specific time period.
    Used to generate the daily log sheets.
    """
    DUTY_STATUS_CHOICES = [
        ('off_duty', 'Off Duty'),
        ('sleeper_berth', 'Sleeper Berth'),
        ('driving', 'Driving'),
        ('on_duty_not_driving', 'On Duty (Not Driving)'),
    ]
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='eld_logs')
    
    # Date and time
    log_date = models.DateField(help_text="Date of this log entry")
    start_time = models.TimeField(help_text="Start time of this status")
    end_time = models.TimeField(help_text="End time of this status")
    
    # Status
    duty_status = models.CharField(max_length=25, choices=DUTY_STATUS_CHOICES)
    
    # Location
    location = models.CharField(max_length=500, blank=True)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    
    # Notes/remarks
    remarks = models.TextField(blank=True)
    
    # Order within the day
    sequence = models.IntegerField(help_text="Order within the day")
    
    class Meta:
        ordering = ['log_date', 'sequence']
        verbose_name = 'ELD Log Entry'
        verbose_name_plural = 'ELD Log Entries'
    
    def __str__(self):
        return f"{self.log_date} {self.start_time}-{self.end_time}: {self.get_duty_status_display()}"
    
    @property
    def duration_hours(self):
        """Calculate duration in hours."""
        from datetime import datetime, timedelta
        start = datetime.combine(self.log_date, self.start_time)
        end = datetime.combine(self.log_date, self.end_time)
        if end < start:  # Crosses midnight
            end += timedelta(days=1)
        return (end - start).total_seconds() / 3600


class DailyLogSummary(models.Model):
    """
    Summary of daily HOS for a trip.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name='daily_summaries')
    
    log_date = models.DateField()
    day_number = models.IntegerField(help_text="Day number of the trip (1, 2, 3...)")
    
    # Hours breakdown
    driving_hours = models.FloatField(default=0)
    on_duty_hours = models.FloatField(default=0)
    off_duty_hours = models.FloatField(default=0)
    sleeper_berth_hours = models.FloatField(default=0)
    
    # Cumulative tracking
    total_miles_driven = models.FloatField(default=0)
    cycle_hours_remaining = models.FloatField(default=70)
    
    class Meta:
        ordering = ['trip', 'day_number']
        unique_together = ['trip', 'log_date']
        verbose_name = 'Daily Log Summary'
        verbose_name_plural = 'Daily Log Summaries'
    
    def __str__(self):
        return f"Day {self.day_number} - {self.log_date}: {self.driving_hours}h driving"
