"""
URL configuration for trips app.

All endpoints prefixed with /api/trips/
"""

from django.urls import path
from .views import (
    TripPlanView,
    RouteOnlyView,
    ELDLogDetailView,
)

app_name = 'trips'

urlpatterns = [
    # Main trip planning endpoint
    path('plan/', TripPlanView.as_view(), name='plan_trip'),
    
    # Route-only endpoint (no HOS calculation)
    path('route/', RouteOnlyView.as_view(), name='get_route'),
    
    # ELD log detail (requires database persistence)
    path('<uuid:trip_id>/logs/<int:day_number>/', ELDLogDetailView.as_view(), name='eld_log_detail'),
]
