"""
Tests for Trip Planning API Views.
"""

import pytest
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status


class TestHealthCheckEndpoint(TestCase):
    """Test health check endpoint."""
    
    def setUp(self):
        self.client = APIClient()
    
    def test_health_check_returns_200(self):
        """Test that health check returns 200 OK."""
        response = self.client.get('/api/health/')
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data['status'] == 'healthy'
        assert 'version' in response.data
        assert 'timestamp' in response.data


class TestApiRootEndpoint(TestCase):
    """Test API root endpoint."""
    
    def setUp(self):
        self.client = APIClient()
    
    def test_api_root_returns_endpoints(self):
        """Test that API root lists available endpoints."""
        response = self.client.get('/api/')
        
        assert response.status_code == status.HTTP_200_OK
        assert 'endpoints' in response.data
        assert 'health' in response.data['endpoints']
        assert 'plan_trip' in response.data['endpoints']


class TestTripPlanEndpoint(TestCase):
    """Test trip planning endpoint."""
    
    def setUp(self):
        self.client = APIClient()
        self.valid_payload = {
            'current_location': 'Chicago, IL',
            'pickup_location': 'Indianapolis, IN',
            'dropoff_location': 'Nashville, TN',
            'current_cycle_used_hours': 0
        }
    
    def test_plan_trip_missing_fields(self):
        """Test that missing required fields return 400."""
        response = self.client.post('/api/trips/plan/', {}, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data
    
    def test_plan_trip_invalid_cycle_hours(self):
        """Test that invalid cycle hours are rejected."""
        payload = {**self.valid_payload, 'current_cycle_used_hours': 100}  # Max is 70
        response = self.client.post('/api/trips/plan/', payload, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_plan_trip_same_locations(self):
        """Test that same pickup and current location is rejected."""
        payload = {
            'current_location': 'Chicago, IL',
            'pickup_location': 'Chicago, IL',  # Same as current
            'dropoff_location': 'Nashville, TN',
            'current_cycle_used_hours': 0
        }
        response = self.client.post('/api/trips/plan/', payload, format='json')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST


class TestRouteEndpoint(TestCase):
    """Test route-only endpoint."""
    
    def setUp(self):
        self.client = APIClient()
    
    def test_route_missing_params(self):
        """Test that missing query params return 400."""
        response = self.client.get('/api/trips/route/')
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert 'error' in response.data


class TestSerializers(TestCase):
    """Test serializer validation."""
    
    def test_trip_input_serializer_valid(self):
        """Test valid input passes validation."""
        from trips.serializers import TripPlanInputSerializer
        
        data = {
            'current_location': 'Chicago, IL',
            'pickup_location': 'Indianapolis, IN',
            'dropoff_location': 'Nashville, TN',
            'current_cycle_used_hours': 10
        }
        
        serializer = TripPlanInputSerializer(data=data)
        assert serializer.is_valid()
    
    def test_trip_input_serializer_invalid_hours(self):
        """Test invalid hours fails validation."""
        from trips.serializers import TripPlanInputSerializer
        
        data = {
            'current_location': 'Chicago, IL',
            'pickup_location': 'Indianapolis, IN',
            'dropoff_location': 'Nashville, TN',
            'current_cycle_used_hours': 75  # Invalid: max is 70
        }
        
        serializer = TripPlanInputSerializer(data=data)
        assert not serializer.is_valid()
        assert 'current_cycle_used_hours' in serializer.errors
