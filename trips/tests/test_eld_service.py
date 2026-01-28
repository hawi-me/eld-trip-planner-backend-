"""
Tests for ELD Log Generator Service.
"""

import pytest
from datetime import datetime, timedelta
from trips.services.eld_service import ELDLogService, ELDLogEntry
from trips.services.hos_service import HOSService, DutyStatus


class TestELDLogService:
    """Test ELD log generation."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.service = ELDLogService(
            carrier_name="Test Carrier",
            driver_name="Test Driver"
        )
        self.hos_service = HOSService()
        self.departure_time = datetime(2024, 1, 15, 6, 0, 0)
    
    def test_generate_daily_logs(self):
        """Test that daily logs are generated correctly."""
        # Create HOS plan first
        hos_plan = self.hos_service.calculate_trip_plan(
            total_distance_miles=400,
            pickup_miles_from_start=50,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        # Generate ELD logs
        logs = self.service.generate_logs(hos_plan)
        
        # Should have logs for each day
        assert len(logs) == hos_plan.total_trip_days
        
        # Each log should have entries
        for log in logs:
            assert len(log.entries) > 0
            assert log.carrier_name == "Test Carrier"
            assert log.driver_name == "Test Driver"
    
    def test_log_entries_format(self):
        """Test that log entries have correct format."""
        hos_plan = self.hos_service.calculate_trip_plan(
            total_distance_miles=200,
            pickup_miles_from_start=50,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        logs = self.service.generate_logs(hos_plan)
        
        for log in logs:
            for entry in log.entries:
                # Check time format
                assert ':' in entry.start_time
                assert ':' in entry.end_time
                
                # Check hours are valid
                assert 0 <= entry.start_hour <= 24
                assert 0 <= entry.end_hour <= 24
                
                # Check duration
                assert entry.duration_hours >= 0
                
                # Check grid row is valid (1-4)
                assert 1 <= entry.grid_row <= 4
    
    def test_summary_hours_add_to_24(self):
        """Test that summary hours add up to 24 for each day."""
        hos_plan = self.hos_service.calculate_trip_plan(
            total_distance_miles=500,
            pickup_miles_from_start=100,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        logs = self.service.generate_logs(hos_plan)
        
        for log in logs:
            total = (
                log.total_hours['off_duty'] +
                log.total_hours['sleeper_berth'] +
                log.total_hours['driving'] +
                log.total_hours['on_duty_not_driving']
            )
            # Allow small floating point variance
            assert abs(total - 24.0) < 0.1, f"Total hours {total} != 24"
    
    def test_grid_data_structure(self):
        """Test that grid data is properly structured for frontend."""
        hos_plan = self.hos_service.calculate_trip_plan(
            total_distance_miles=200,
            pickup_miles_from_start=50,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        logs = self.service.generate_logs(hos_plan)
        
        for log in logs:
            grid = log.grid_data
            
            # Check structure
            assert 'segments' in grid
            assert 'transitions' in grid
            assert 'hours' in grid
            assert 'rows' in grid
            
            # Check hours (0-24)
            assert grid['hours'] == list(range(25))
            
            # Check rows
            assert len(grid['rows']) == 4
            
            # Check segments have required fields
            for segment in grid['segments']:
                assert 'row' in segment
                assert 'start_x' in segment
                assert 'end_x' in segment
                assert 'status' in segment
    
    def test_json_output(self):
        """Test JSON serialization of logs."""
        hos_plan = self.hos_service.calculate_trip_plan(
            total_distance_miles=200,
            pickup_miles_from_start=50,
            current_cycle_used_hours=0,
            departure_time=self.departure_time
        )
        
        json_logs = self.service.generate_logs_json(hos_plan)
        
        # Should be a list of dicts
        assert isinstance(json_logs, list)
        
        for log in json_logs:
            assert isinstance(log, dict)
            assert 'date' in log
            assert 'entries' in log
            assert 'summary' in log
            assert 'grid_data' in log


class TestELDLogEntry:
    """Test ELDLogEntry dataclass."""
    
    def test_entry_creation(self):
        """Test creating a log entry."""
        entry = ELDLogEntry(
            start_time='06:00',
            end_time='14:00',
            start_hour=6.0,
            end_hour=14.0,
            duration_hours=8.0,
            duty_status='driving',
            duty_status_display='Driving',
            location='En route',
            remarks='Test drive',
            grid_row=3
        )
        
        assert entry.start_time == '06:00'
        assert entry.end_time == '14:00'
        assert entry.duration_hours == 8.0
        assert entry.grid_row == 3
    
    def test_entry_to_dict(self):
        """Test entry serialization to dict."""
        entry = ELDLogEntry(
            start_time='06:00',
            end_time='14:00',
            start_hour=6.0,
            end_hour=14.0,
            duration_hours=8.0,
            duty_status='driving',
            duty_status_display='Driving',
            location='En route',
            remarks='',
            grid_row=3
        )
        
        d = entry.to_dict()
        
        assert isinstance(d, dict)
        assert d['start_time'] == '06:00'
        assert d['duty_status'] == 'driving'
