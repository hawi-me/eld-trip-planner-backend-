"""
Trips app configuration.
"""

from django.apps import AppConfig


class TripsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'trips'
    verbose_name = 'ELD Trip Planner'
