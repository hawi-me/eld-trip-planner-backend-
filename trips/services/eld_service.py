"""
ELD (Electronic Logging Device) Log Generator Service.

Generates ELD-compliant daily log sheets based on trip and HOS calculations.
Outputs structured JSON for frontend rendering of the grid-based log display.

ELD Log Format:
==============
Each day's log contains a 24-hour timeline divided into 15-minute increments.
Status blocks show:
- Start time
- End time  
- Duty status (Off Duty, Sleeper Berth, Driving, On Duty Not Driving)

The output is structured for rendering a visual ELD log grid similar to
paper logs used before electronic logging became mandatory.
"""

import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from .hos_service import HOSPlan, DailyHOSSummary, DutyStatus, DutyPeriod

logger = logging.getLogger(__name__)


@dataclass
class ELDLogEntry:
    """
    Single entry on the ELD log representing a time block.
    
    Represents a continuous period of a single duty status.
    """
    start_time: str      # HH:MM format (24-hour)
    end_time: str        # HH:MM format (24-hour)
    start_hour: float    # Decimal hour (e.g., 8.5 = 8:30 AM)
    end_hour: float      # Decimal hour
    duration_hours: float
    duty_status: str     # off_duty, sleeper_berth, driving, on_duty_not_driving
    duty_status_display: str  # Human-readable status
    location: str
    remarks: str
    # For grid rendering
    grid_row: int        # 1=Off Duty, 2=Sleeper, 3=Driving, 4=On Duty
    
    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class ELDDailyLog:
    """
    Complete ELD log for a single day.
    
    Contains all entries and summary information needed for rendering.
    """
    date: str           # YYYY-MM-DD format
    day_number: int
    day_of_week: str    # Monday, Tuesday, etc.
    entries: List[ELDLogEntry]
    
    # Summary hours (for the right side of the log)
    total_hours: Dict[str, float]  # off_duty, sleeper_berth, driving, on_duty
    
    # Running totals
    total_miles: float
    
    # Location info
    starting_location: str
    ending_location: str
    
    # Carrier info (can be customized)
    carrier_name: str
    driver_name: str
    
    # Grid rendering data
    grid_data: List[Dict]  # Pre-processed for easy frontend rendering
    
    def to_dict(self) -> Dict:
        return {
            'date': self.date,
            'day_number': self.day_number,
            'day_of_week': self.day_of_week,
            'entries': [e.to_dict() for e in self.entries],
            'summary': self.total_hours,
            'total_miles': self.total_miles,
            'starting_location': self.starting_location,
            'ending_location': self.ending_location,
            'carrier_name': self.carrier_name,
            'driver_name': self.driver_name,
            'grid_data': self.grid_data
        }


class ELDLogService:
    """
    Service for generating ELD daily log sheets.
    
    Takes HOS plan output and generates structured data for
    rendering ELD logs in the frontend.
    """
    
    # Grid row mapping for duty statuses
    GRID_ROWS = {
        DutyStatus.OFF_DUTY: 1,
        DutyStatus.SLEEPER_BERTH: 2,
        DutyStatus.DRIVING: 3,
        DutyStatus.ON_DUTY_NOT_DRIVING: 4,
        'off_duty': 1,
        'sleeper_berth': 2,
        'driving': 3,
        'on_duty_not_driving': 4,
    }
    
    DUTY_STATUS_DISPLAY = {
        'off_duty': 'Off Duty',
        'sleeper_berth': 'Sleeper Berth',
        'driving': 'Driving',
        'on_duty_not_driving': 'On Duty (Not Driving)',
    }
    
    def __init__(
        self,
        carrier_name: str = "ELD Trip Planner Demo",
        driver_name: str = "Demo Driver"
    ):
        self.carrier_name = carrier_name
        self.driver_name = driver_name
    
    def generate_logs(
        self,
        hos_plan: HOSPlan,
        locations: Optional[Dict] = None
    ) -> List[ELDDailyLog]:
        """
        Generate ELD daily logs from HOS plan.
        
        Args:
            hos_plan: Complete HOS plan from HOSService
            locations: Location information for the trip
            
        Returns:
            List of ELDDailyLog objects, one per day
        """
        locations = locations or {}
        daily_logs = []
        
        for summary in hos_plan.daily_summaries:
            daily_log = self._generate_daily_log(summary, locations)
            daily_logs.append(daily_log)
        
        logger.info(f"Generated {len(daily_logs)} daily ELD logs")
        return daily_logs
    
    def _generate_daily_log(
        self,
        summary: DailyHOSSummary,
        locations: Dict
    ) -> ELDDailyLog:
        """Generate ELD log for a single day."""
        
        entries = []
        
        # Convert duty periods to log entries
        for period in summary.duty_periods:
            entry = self._create_log_entry(period)
            entries.append(entry)
        
        # Sort entries by start time
        entries.sort(key=lambda e: e.start_hour)
        
        # Fill gaps with off-duty time
        entries = self._fill_gaps(entries)
        
        # Calculate summary hours
        total_hours = self._calculate_summary_hours(entries)
        
        # Generate grid data for frontend rendering
        grid_data = self._generate_grid_data(entries)
        
        # Determine locations
        starting_location = self._get_period_location(
            summary.duty_periods, 'first', locations
        )
        ending_location = self._get_period_location(
            summary.duty_periods, 'last', locations
        )
        
        return ELDDailyLog(
            date=summary.date.strftime('%Y-%m-%d'),
            day_number=summary.day_number,
            day_of_week=summary.date.strftime('%A'),
            entries=entries,
            total_hours=total_hours,
            total_miles=round(summary.miles_driven, 1),
            starting_location=starting_location,
            ending_location=ending_location,
            carrier_name=self.carrier_name,
            driver_name=self.driver_name,
            grid_data=grid_data
        )
    
    def _create_log_entry(self, period: DutyPeriod) -> ELDLogEntry:
        """Create a log entry from a duty period."""
        
        # Get status string
        if isinstance(period.status, DutyStatus):
            status_str = period.status.value
        else:
            status_str = str(period.status)
        
        start_hour = period.start_time.hour + period.start_time.minute / 60
        end_hour = period.end_time.hour + period.end_time.minute / 60
        
        # Handle midnight crossing
        if end_hour < start_hour:
            end_hour = 24.0
        
        return ELDLogEntry(
            start_time=period.start_time.strftime('%H:%M'),
            end_time=period.end_time.strftime('%H:%M'),
            start_hour=round(start_hour, 2),
            end_hour=round(end_hour, 2),
            duration_hours=round(period.duration_hours, 2),
            duty_status=status_str,
            duty_status_display=self.DUTY_STATUS_DISPLAY.get(
                status_str, status_str
            ),
            location=period.location,
            remarks=period.remarks,
            grid_row=self.GRID_ROWS.get(status_str, 1)
        )
    
    def _fill_gaps(self, entries: List[ELDLogEntry]) -> List[ELDLogEntry]:
        """Fill gaps in the log with off-duty status."""
        
        if not entries:
            # Full day off-duty
            return [ELDLogEntry(
                start_time='00:00',
                end_time='24:00',
                start_hour=0.0,
                end_hour=24.0,
                duration_hours=24.0,
                duty_status='off_duty',
                duty_status_display='Off Duty',
                location='',
                remarks='',
                grid_row=1
            )]
        
        filled_entries = []
        current_hour = 0.0
        
        for entry in entries:
            # If there's a gap before this entry
            if entry.start_hour > current_hour:
                gap_entry = ELDLogEntry(
                    start_time=self._hour_to_time_str(current_hour),
                    end_time=self._hour_to_time_str(entry.start_hour),
                    start_hour=current_hour,
                    end_hour=entry.start_hour,
                    duration_hours=round(entry.start_hour - current_hour, 2),
                    duty_status='off_duty',
                    duty_status_display='Off Duty',
                    location='',
                    remarks='',
                    grid_row=1
                )
                filled_entries.append(gap_entry)
            
            filled_entries.append(entry)
            current_hour = entry.end_hour
        
        # Fill remaining time until midnight
        if current_hour < 24.0:
            gap_entry = ELDLogEntry(
                start_time=self._hour_to_time_str(current_hour),
                end_time='24:00',
                start_hour=current_hour,
                end_hour=24.0,
                duration_hours=round(24.0 - current_hour, 2),
                duty_status='off_duty',
                duty_status_display='Off Duty',
                location='',
                remarks='',
                grid_row=1
            )
            filled_entries.append(gap_entry)
        
        return filled_entries
    
    def _hour_to_time_str(self, hour: float) -> str:
        """Convert decimal hour to HH:MM string."""
        h = int(hour)
        m = int((hour - h) * 60)
        if h >= 24:
            h = 0
        return f"{h:02d}:{m:02d}"
    
    def _calculate_summary_hours(
        self,
        entries: List[ELDLogEntry]
    ) -> Dict[str, float]:
        """Calculate total hours for each duty status."""
        
        summary = {
            'off_duty': 0.0,
            'sleeper_berth': 0.0,
            'driving': 0.0,
            'on_duty_not_driving': 0.0,
            'total': 0.0
        }
        
        for entry in entries:
            status = entry.duty_status
            if status in summary:
                summary[status] += entry.duration_hours
            summary['total'] += entry.duration_hours
        
        # Round all values
        return {k: round(v, 2) for k, v in summary.items()}
    
    def _generate_grid_data(
        self,
        entries: List[ELDLogEntry]
    ) -> List[Dict]:
        """
        Generate grid data for frontend rendering.
        
        Creates a structure optimized for drawing the ELD log grid
        with horizontal lines showing status changes.
        
        The grid has:
        - X-axis: 24 hours (0-24), typically shown in 1-hour increments
        - Y-axis: 4 rows (Off Duty, Sleeper Berth, Driving, On Duty Not Driving)
        - Horizontal lines connecting status periods
        - Vertical lines at status changes
        """
        
        grid_segments = []
        
        for entry in entries:
            segment = {
                'row': entry.grid_row,
                'start_x': entry.start_hour,
                'end_x': entry.end_hour,
                'status': entry.duty_status,
                'status_display': entry.duty_status_display,
                'duration': entry.duration_hours,
                # Additional data for tooltips
                'start_time': entry.start_time,
                'end_time': entry.end_time,
                'remarks': entry.remarks
            }
            grid_segments.append(segment)
        
        # Add vertical transition lines
        transitions = self._calculate_transitions(entries)
        
        return {
            'segments': grid_segments,
            'transitions': transitions,
            'hours': list(range(25)),  # 0 to 24 for grid lines
            'rows': [
                {'id': 1, 'label': 'Off Duty', 'short': 'OFF'},
                {'id': 2, 'label': 'Sleeper Berth', 'short': 'SB'},
                {'id': 3, 'label': 'Driving', 'short': 'D'},
                {'id': 4, 'label': 'On Duty (Not Driving)', 'short': 'ON'}
            ]
        }
    
    def _calculate_transitions(
        self,
        entries: List[ELDLogEntry]
    ) -> List[Dict]:
        """Calculate vertical line positions for status transitions."""
        
        transitions = []
        
        for i in range(len(entries) - 1):
            current = entries[i]
            next_entry = entries[i + 1]
            
            if current.grid_row != next_entry.grid_row:
                transitions.append({
                    'x': current.end_hour,
                    'from_row': current.grid_row,
                    'to_row': next_entry.grid_row,
                    'from_status': current.duty_status,
                    'to_status': next_entry.duty_status
                })
        
        return transitions
    
    def _get_period_location(
        self,
        periods: List[DutyPeriod],
        position: str,
        locations: Dict
    ) -> str:
        """Get location for first or last period."""
        
        if not periods:
            return "Unknown"
        
        if position == 'first':
            period = periods[0]
            if period.location:
                return period.location
            # Try to get from locations dict
            return locations.get('current', {}).get('address', 'Starting Location')
        else:
            period = periods[-1]
            if period.location:
                return period.location
            return locations.get('dropoff', {}).get('address', 'Ending Location')
    
    def generate_logs_json(
        self,
        hos_plan: HOSPlan,
        locations: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Generate ELD logs and return as JSON-serializable dictionaries.
        
        This is the main method for API responses.
        """
        logs = self.generate_logs(hos_plan, locations)
        return [log.to_dict() for log in logs]
    
    def generate_printable_log(
        self,
        daily_log: ELDDailyLog
    ) -> Dict:
        """
        Generate a printable version of the ELD log.
        
        Includes all required fields for DOT compliance when printed.
        """
        return {
            'header': {
                'date': daily_log.date,
                'day_of_week': daily_log.day_of_week,
                'carrier_name': daily_log.carrier_name,
                'driver_name': daily_log.driver_name,
                'from': daily_log.starting_location,
                'to': daily_log.ending_location,
                'total_miles': daily_log.total_miles,
            },
            'graph': {
                'grid': daily_log.grid_data,
                'entries': [e.to_dict() for e in daily_log.entries]
            },
            'summary': daily_log.total_hours,
            'remarks': [
                e.remarks for e in daily_log.entries 
                if e.remarks
            ]
        }


# Example usage and response format documentation
"""
Example Response Format:
========================

{
    "date": "2024-01-15",
    "day_number": 1,
    "day_of_week": "Monday",
    "entries": [
        {
            "start_time": "00:00",
            "end_time": "06:00",
            "start_hour": 0.0,
            "end_hour": 6.0,
            "duration_hours": 6.0,
            "duty_status": "off_duty",
            "duty_status_display": "Off Duty",
            "location": "Chicago, IL",
            "remarks": "",
            "grid_row": 1
        },
        {
            "start_time": "06:00",
            "end_time": "06:30",
            "start_hour": 6.0,
            "end_hour": 6.5,
            "duration_hours": 0.5,
            "duty_status": "on_duty_not_driving",
            "duty_status_display": "On Duty (Not Driving)",
            "location": "Chicago, IL",
            "remarks": "Pre-trip inspection",
            "grid_row": 4
        },
        {
            "start_time": "06:30",
            "end_time": "14:30",
            "start_hour": 6.5,
            "end_hour": 14.5,
            "duration_hours": 8.0,
            "duty_status": "driving",
            "duty_status_display": "Driving",
            "location": "En route",
            "remarks": "Driving to Indianapolis",
            "grid_row": 3
        }
        // ... more entries
    ],
    "summary": {
        "off_duty": 10.0,
        "sleeper_berth": 0.0,
        "driving": 11.0,
        "on_duty_not_driving": 3.0,
        "total": 24.0
    },
    "total_miles": 605.0,
    "starting_location": "Chicago, IL",
    "ending_location": "Indianapolis, IN",
    "carrier_name": "ABC Trucking",
    "driver_name": "John Doe",
    "grid_data": {
        "segments": [
            {
                "row": 1,
                "start_x": 0.0,
                "end_x": 6.0,
                "status": "off_duty",
                "status_display": "Off Duty",
                "duration": 6.0
            }
            // ... more segments
        ],
        "transitions": [
            {
                "x": 6.0,
                "from_row": 1,
                "to_row": 4,
                "from_status": "off_duty",
                "to_status": "on_duty_not_driving"
            }
            // ... more transitions
        ],
        "hours": [0, 1, 2, ..., 24],
        "rows": [
            {"id": 1, "label": "Off Duty", "short": "OFF"},
            {"id": 2, "label": "Sleeper Berth", "short": "SB"},
            {"id": 3, "label": "Driving", "short": "D"},
            {"id": 4, "label": "On Duty (Not Driving)", "short": "ON"}
        ]
    }
}
"""
