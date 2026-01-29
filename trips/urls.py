"""
URL configuration for trips app.

Comprehensive URL patterns for ELD Trip Planner API.
"""

from django.urls import path
from .views import (
    # Trip Management
    TripListCreateView,
    TripDetailView,
    TripPlanView,
    RouteOnlyView,
    
    # Route Service
    RouteCalculateView,
    
    # ELD Service
    ELDGenerateView,
    ELDLogsByTripView,
    ELDLogDayDetailView,
    ELDLogDetailView,
    
    # Cycle Tracking
    CycleStatusView,
    CycleUpdateView,
    
    # HOS Config
    HOSConfigView,
    
    # Map Proxy
    MapProxyRouteView,
    MapProxyGeocodeView,
)

app_name = 'trips'

urlpatterns = [
    # ==========================================================================
    # Trip Management CRUD
    # ==========================================================================
    # GET /api/trips/ - List all trips
    # POST /api/trips/ - Create new trip with full planning
    path('', TripListCreateView.as_view(), name='trip_list_create'),
    
    # GET/PUT/DELETE /api/trips/{id}/
    path('<uuid:trip_id>/', TripDetailView.as_view(), name='trip_detail'),
    
    # Legacy: POST /api/trips/plan/
    path('plan/', TripPlanView.as_view(), name='plan_trip'),
    
    # Legacy: GET /api/trips/route/
    path('route/', RouteOnlyView.as_view(), name='get_route'),
    
    # Legacy ELD log detail
    path('<uuid:trip_id>/logs/<int:day_number>/', ELDLogDetailView.as_view(), name='eld_log_detail'),
]
