"""
URL configuration for ELD Trip Planner project.

Complete API URL structure:
- /api/ - API root
- /api/health/ - Health check
- /api/routes/ - Route calculation service
- /api/trips/ - Trip management CRUD
- /api/eld/ - ELD log generation and storage
- /api/cycle/ - Cycle tracking (70h/8d)
- /api/config/ - HOS configuration
- /api/maps/ - Map proxy service
"""

from django.contrib import admin
from django.urls import path, include
from trips.views import (
    HealthCheckView,
    api_root,
    # Route Service
    RouteCalculateView,
    # ELD Service
    ELDGenerateView,
    ELDLogsByTripView,
    ELDLogDayDetailView,
    # Cycle Tracking
    CycleStatusView,
    CycleUpdateView,
    # HOS Config
    HOSConfigView,
    # Map Proxy
    MapProxyRouteView,
    MapProxyGeocodeView,
)

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API root - Documentation
    path('api/', api_root, name='api_root'),
    
    # Health check endpoint
    path('api/health/', HealthCheckView.as_view(), name='health_check'),
    
    # ==========================================================================
    # Route Service
    # ==========================================================================
    path('api/routes/calculate', RouteCalculateView.as_view(), name='route_calculate'),
    
    # ==========================================================================
    # Trip Management (CRUD) - Uses trips app urls
    # ==========================================================================
    path('api/trips/', include('trips.urls', namespace='trips')),
    
    # ==========================================================================
    # ELD Log Generation & Storage
    # ==========================================================================
    path('api/eld/generate', ELDGenerateView.as_view(), name='eld_generate'),
    path('api/eld/logs/<uuid:trip_id>/', ELDLogsByTripView.as_view(), name='eld_logs_by_trip'),
    path('api/eld/logs/<uuid:trip_id>/day/<int:day_number>/', ELDLogDayDetailView.as_view(), name='eld_log_day_detail'),
    
    # ==========================================================================
    # Cycle Tracking Service
    # ==========================================================================
    path('api/cycle/status', CycleStatusView.as_view(), name='cycle_status'),
    path('api/cycle/update', CycleUpdateView.as_view(), name='cycle_update'),
    
    # ==========================================================================
    # HOS Configuration Service
    # ==========================================================================
    path('api/config/hos', HOSConfigView.as_view(), name='config_hos'),
    
    # ==========================================================================
    # Map Proxy Service (Security - hides API keys)
    # ==========================================================================
    path('api/maps/route', MapProxyRouteView.as_view(), name='maps_route'),
    path('api/maps/geocode', MapProxyGeocodeView.as_view(), name='maps_geocode'),
]
