"""
Admin configuration for Trip models.
"""

from django.contrib import admin
from .models import Trip, TripStop, ELDLogEntry, DailyLogSummary


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = ['id', 'current_location', 'dropoff_location', 'total_distance_miles', 'created_at']
    list_filter = ['created_at']
    search_fields = ['current_location', 'pickup_location', 'dropoff_location']
    readonly_fields = ['id', 'created_at', 'updated_at']


@admin.register(TripStop)
class TripStopAdmin(admin.ModelAdmin):
    list_display = ['trip', 'stop_type', 'location_name', 'sequence', 'arrival_time']
    list_filter = ['stop_type']
    search_fields = ['location_name']


@admin.register(ELDLogEntry)
class ELDLogEntryAdmin(admin.ModelAdmin):
    list_display = ['trip', 'log_date', 'start_time', 'end_time', 'duty_status']
    list_filter = ['duty_status', 'log_date']


@admin.register(DailyLogSummary)
class DailyLogSummaryAdmin(admin.ModelAdmin):
    list_display = ['trip', 'log_date', 'day_number', 'driving_hours', 'total_miles_driven']
    list_filter = ['log_date']
