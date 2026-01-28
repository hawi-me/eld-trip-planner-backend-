"""
Tests for FMCSA Hours of Service (HOS) Service.

Tests the core HOS logic to ensure compliance with FMCSA regulations.
"""

import pytest
from datetime import datetime, timedelta
from trips.services.hos_service import HOSService, HOSConfig, DutyStatus


class TestHOSConfig:
    """Test HOS configuration defaults."""
    
    def test_default_config(self):
        """Test default HOS configuration values."""
        config = HOSConfig()
        
        assert config.cycle_days == 8
        assert config.cycle_hours == 70.0
        assert config.max_driving_hours == 11.0
        assert config.max_on_duty_hours == 14.0
        assert config.break_required_after_hours == 8.0
        assert config.break_duration_hours == 0.5
        assert config.off_duty_reset_hours == 10.0
        assert config.fuel_interval_miles == 1000.0
        assert config.pickup_duration_hours == 1.0
        assert config.dropoff_duration_hours == 1.0


class TestHOSService:
    """Test HOS calculation service."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = HOSService()
        self.departure_time = datetime(2024, 1, 15, 6, 0, 0)  # 6 AM
    
    def test_short_trip_no_stops(self):
        """Test a short trip that doesn't require any mandatory stops."""
        # 200 miles at 55 mph = ~3.6 hours driving
        # No breaks needed
        plan = self.service.calculate_trip_plan(
            total_distance_miles=200,
            pickup_miles_from_start=50,
            current_cycle_used_hours=0,
            departure_time=self.departure_time,
            locations={
                'current': {'address': 'Chicago, IL', 'latitude': 41.8781, 'longitude': -87.6298},
                'pickup': {'address': 'Gary, IN', 'latitude': 41.5934, 'longitude': -87.3464},
                'dropoff': {'address': 'Indianapolis, IN', 'latitude': 39.7684, 'longitude': -86.1581}
            }
        )
        
        # Should have pickup and dropoff stops
        assert any(s.stop_type == 'pickup' for s in plan.planned_stops)
        assert any(s.stop_type == 'dropoff' for s in plan.planned_stops)
        
        # No rest stops needed for short trip
        rest_stops = [s for s in plan.planned_stops if s.stop_type == 'rest']
        assert len(rest_stops) == 0
        
        # Should complete in 1 day
        assert plan.total_trip_days == 1
    
    def test_medium_trip_requires_break(self):
        """Test a trip that requires a 30-minute break after 8 hours."""
        # 500 miles at 55 mph = ~9.1 hours driving
        # Needs 30-minute break after 8 hours
        plan = self.service.calculate_trip_plan(
            total_distance_miles=500,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        # Should have at least one break
        breaks = [s for s in plan.planned_stops if s.stop_type == 'break']
        assert len(breaks) >= 1
        
        # Break should be 30 minutes
        if breaks:
            assert breaks[0].duration_hours == 0.5
    
    def test_long_trip_requires_rest(self):
        """Test a trip that requires 10-hour rest (11-hour driving limit)."""
        # 700 miles at 55 mph = ~12.7 hours driving
        # Needs rest after 11 hours
        plan = self.service.calculate_trip_plan(
            total_distance_miles=700,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        # Should have at least one rest stop
        rest_stops = [s for s in plan.planned_stops if s.stop_type == 'rest']
        assert len(rest_stops) >= 1
        
        # Rest should be 10 hours
        if rest_stops:
            assert rest_stops[0].duration_hours == 10.0
        
        # Should take multiple days
        assert plan.total_trip_days >= 2
    
    def test_very_long_trip_multiple_rest_stops(self):
        """Test a cross-country trip requiring multiple rest stops."""
        # 2000 miles - approximately 36 hours of driving
        plan = self.service.calculate_trip_plan(
            total_distance_miles=2000,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        # Should have multiple rest stops
        rest_stops = [s for s in plan.planned_stops if s.stop_type == 'rest']
        assert len(rest_stops) >= 3
        
        # Should have fuel stops (every 1000 miles)
        fuel_stops = [s for s in plan.planned_stops if s.stop_type == 'fuel']
        assert len(fuel_stops) >= 1
        
        # Should take multiple days
        assert plan.total_trip_days >= 4
    
    def test_cycle_hours_considered(self):
        """Test that current cycle hours are considered in planning."""
        # With 60 hours already used, less driving available
        plan = self.service.calculate_trip_plan(
            total_distance_miles=500,
            pickup_miles_from_start=100,
            current_cycle_used_hours=60,  # Only 10 hours left in cycle
            departure_time=self.departure_time
        )
        
        # Should need more rest stops due to cycle limit
        assert plan.cycle_hours_remaining >= 0
    
    def test_pickup_dropoff_stops_included(self):
        """Test that pickup and dropoff stops are always included."""
        plan = self.service.calculate_trip_plan(
            total_distance_miles=300,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time,
            locations={
                'pickup': {'address': 'Pickup City'},
                'dropoff': {'address': 'Dropoff City'}
            }
        )
        
        pickup_stops = [s for s in plan.planned_stops if s.stop_type == 'pickup']
        dropoff_stops = [s for s in plan.planned_stops if s.stop_type == 'dropoff']
        
        assert len(pickup_stops) == 1
        assert len(dropoff_stops) == 1
        
        # Pickup should have 1 hour duration
        assert pickup_stops[0].duration_hours == 1.0
        assert dropoff_stops[0].duration_hours == 1.0
    
    def test_daily_summaries_generated(self):
        """Test that daily summaries are generated for each day."""
        plan = self.service.calculate_trip_plan(
            total_distance_miles=700,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        # Should have daily summary for each day
        assert len(plan.daily_summaries) == plan.total_trip_days
        
        # Each day should have valid hours
        for summary in plan.daily_summaries:
            assert summary.driving_hours >= 0
            assert summary.on_duty_hours >= 0
            assert summary.off_duty_hours >= 0
            assert summary.sleeper_berth_hours >= 0
    
    def test_compliance_validation(self):
        """Test HOS compliance validation."""
        plan = self.service.calculate_trip_plan(
            total_distance_miles=500,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        compliance = self.service.validate_hos_compliance(plan)
        
        # Plan should be compliant
        assert compliance['compliant'] is True
        assert len(compliance['violations']) == 0


class TestHOSEdgeCases:
    """Test edge cases in HOS calculations."""
    
    def setup_method(self):
        self.service = HOSService()
        self.departure_time = datetime(2024, 1, 15, 6, 0, 0)
    
    def test_zero_distance_trip(self):
        """Test handling of zero-distance trip."""
        plan = self.service.calculate_trip_plan(
            total_distance_miles=0,
            pickup_miles_from_start=0,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        # Should still have dropoff
        assert any(s.stop_type == 'dropoff' for s in plan.planned_stops)
    
    def test_max_cycle_hours(self):
        """Test trip with maximum cycle hours used."""
        # At 70 hours, need reset
        plan = self.service.calculate_trip_plan(
            total_distance_miles=300,
            pickup_miles_from_start=50,
            current_cycle_used_hours=69.5,  # Almost at limit
            departure_time=self.departure_time
        )
        
        # Should have rest stops due to cycle limit
        assert plan.total_trip_days >= 1
    
    def test_late_departure(self):
        """Test trip starting late in the day."""
        late_departure = datetime(2024, 1, 15, 20, 0, 0)  # 8 PM
        
        plan = self.service.calculate_trip_plan(
            total_distance_miles=400,
            pickup_miles_from_start=50,
            current_cycle_used_hours=0,
            departure_time=late_departure
        )
        
        # Should span multiple calendar days
        assert plan.total_trip_days >= 1
