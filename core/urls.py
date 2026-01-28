"""
URL configuration for ELD Trip Planner project.

Base URL: /api/
"""

from django.contrib import admin
from django.urls import path, include
from trips.views import HealthCheckView, api_root

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # API root
    path('api/', api_root, name='api_root'),
    
    # Health check endpoint
    path('api/health/', HealthCheckView.as_view(), name='health_check'),
    
    # Trip planning endpoints
    path('api/trips/', include('trips.urls', namespace='trips')),
]
