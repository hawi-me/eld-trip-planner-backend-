"""
FMCSA Hours of Service (HOS) Calculation Service.

Implements Federal Motor Carrier Safety Administration regulations for 
property-carrying drivers (truckers).

FMCSA HOS Rules Implemented:
============================
1. 70-Hour/8-Day Rule: Max 70 hours on-duty in any 8 consecutive days
2. 11-Hour Driving Limit: Max 11 hours driving after 10 consecutive hours off-duty
3. 14-Hour On-Duty Window: Cannot drive beyond 14th hour after coming on-duty
4. 30-Minute Break: Required after 8 hours of cumulative driving
5. 10-Hour Off-Duty: Required before new driving period (can split 7/3 or 8/2)
6. Fuel Stop: Every ~1,000 miles (practical consideration)
7. Pickup/Dropoff: 1 hour each for loading/unloading activities

References:
- https://www.fmcsa.dot.gov/regulations/hours-of-service
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class DutyStatus(Enum):
    """Driver duty status as defined by FMCSA."""
    OFF_DUTY = "off_duty"
    SLEEPER_BERTH = "sleeper_berth"
    DRIVING = "driving"
    ON_DUTY_NOT_DRIVING = "on_duty_not_driving"


@dataclass
class HOSConfig:
    """
    Configuration for HOS rules.
    All values can be adjusted for different regulations or testing.
    """
    # Cycle limits
    cycle_days: int = 8
    cycle_hours: float = 70.0
    
    # Daily limits
    max_driving_hours: float = 11.0
    max_on_duty_hours: float = 14.0
    
    # Break requirements
    break_required_after_hours: float = 8.0
    break_duration_hours: float = 0.5  # 30 minutes
    
    # Reset requirements
    off_duty_reset_hours: float = 10.0
    restart_hours: float = 34.0  # 34-hour restart (optional use)
    
    # Practical stops
    fuel_interval_miles: float = 1000.0
    fuel_stop_duration_hours: float = 0.5  # 30 minutes
    
    # Loading/unloading
    pickup_duration_hours: float = 1.0
    dropoff_duration_hours: float = 1.0
    
    # Average speed for calculations
    average_speed_mph: float = 55.0


@dataclass
class DutyPeriod:
    """Represents a period of a specific duty status."""
    status: DutyStatus
    start_time: datetime
    end_time: datetime
    location: str = ""
    remarks: str = ""
    
    @property
    def duration_hours(self) -> float:
        return (self.end_time - self.start_time).total_seconds() / 3600


@dataclass
class PlannedStop:
    """A planned stop during the trip."""
    stop_type: str  # 'rest', 'break', 'fuel', 'pickup', 'dropoff'
    location: str
    latitude: float
    longitude: float
    arrival_time: datetime
    departure_time: datetime
    duration_hours: float
    miles_from_start: float
    day_number: int
    remarks: str = ""


@dataclass
class DailyHOSSummary:
    """Summary of HOS for a single day."""
    date: datetime
    day_number: int
    driving_hours: float = 0.0
    on_duty_hours: float = 0.0
    off_duty_hours: float = 0.0
    sleeper_berth_hours: float = 0.0
    miles_driven: float = 0.0
    duty_periods: List[DutyPeriod] = field(default_factory=list)
    
    @property
    def total_hours(self) -> float:
        return self.driving_hours + self.on_duty_hours + self.off_duty_hours + self.sleeper_berth_hours


@dataclass
class HOSPlan:
    """Complete HOS plan for a trip."""
    planned_stops: List[PlannedStop]
    daily_summaries: List[DailyHOSSummary]
    total_driving_hours: float
    total_on_duty_hours: float
    total_trip_days: int
    departure_time: datetime
    arrival_time: datetime
    cycle_hours_remaining: float


class HOSService:
    """
    Service for calculating FMCSA-compliant Hours of Service schedules.
    
    This service takes trip parameters and calculates:
    - When and where the driver needs to stop
    - Daily breakdown of duty statuses
    - Total trip duration accounting for all required stops
    """
    
    def __init__(self, config: Optional[HOSConfig] = None):
        self.config = config or HOSConfig()
    
    def calculate_trip_plan(
        self,
        total_distance_miles: float,
        pickup_miles_from_start: float,
        current_cycle_used_hours: float,
        departure_time: Optional[datetime] = None,
        locations: Optional[Dict] = None,
        route_coordinates: Optional[List[Dict]] = None,
        adverse_conditions: bool = False,
        short_haul_cdl: bool = False,
        split_sleeper: bool = False
    ) -> HOSPlan:
        """
        Calculate complete HOS-compliant trip plan.
        
        Args:
            total_distance_miles: Total trip distance
            pickup_miles_from_start: Distance to pickup location
            current_cycle_used_hours: Hours already used in 8-day cycle
            departure_time: When the trip starts (defaults to now)
            locations: Dict with current, pickup, dropoff location info
            route_coordinates: List of route coordinates for stop placement
            
        Returns:
            HOSPlan with all stops and daily summaries
        """
        if departure_time is None:
            departure_time = datetime.now().replace(second=0, microsecond=0)
        
        locations = locations or {}
        route_coordinates = route_coordinates or []
        
        # Initialize tracking variables
        current_time = departure_time
        current_miles = 0.0
        
        # Daily counters (reset after 10-hour off-duty)
        driving_since_break = 0.0  # Hours since last 30-min break
        driving_today = 0.0        # Hours driving in current on-duty period
        on_duty_window_start = current_time  # Start of 14-hour window
        
        # Cycle counter
        cycle_hours_used = current_cycle_used_hours
        
        # Results
        planned_stops: List[PlannedStop] = []
        daily_summaries: List[DailyHOSSummary] = []
        all_duty_periods: List[DutyPeriod] = []
        
        # Current day tracking
        current_day_number = 1
        current_day_start = current_time.replace(hour=0, minute=0, second=0, microsecond=0)
        
        logger.info(
            f"Planning trip: {total_distance_miles:.1f} miles, "
            f"pickup at {pickup_miles_from_start:.1f} miles, "
            f"cycle used: {current_cycle_used_hours:.1f}h"
        )
        
        # Track when we need stops
        miles_since_fuel = 0.0
        passed_pickup = False
        passed_dropoff = False

        # Apply exception toggles
        max_drive_hours_today = self.config.max_driving_hours + (2.0 if adverse_conditions else 0.0)
        max_on_duty_window_today = self.config.max_on_duty_hours + (2.0 if adverse_conditions else 0.0)
        break_required_after = self.config.break_required_after_hours if not short_haul_cdl else float('inf')
        
        while current_miles < total_distance_miles:
            # Check if we need mandatory breaks/stops
            
            # 1. Check 30-minute break requirement (after 8 hours cumulative driving)
            if driving_since_break >= break_required_after:
                stop = self._create_break_stop(
                    current_time, current_miles, current_day_number,
                    route_coordinates, total_distance_miles
                )
                planned_stops.append(stop)
                all_duty_periods.append(DutyPeriod(
                    status=DutyStatus.OFF_DUTY,
                    start_time=stop.arrival_time,
                    end_time=stop.departure_time,
                    location=stop.location,
                    remarks="30-minute break (8-hour driving rule)"
                ))
                current_time = stop.departure_time
                driving_since_break = 0.0
                logger.debug(f"Added 30-min break at {current_miles:.1f} miles")
            
            # 2. Check 11-hour driving limit
            if driving_today >= max_drive_hours_today:
                if split_sleeper:
                    # Add split sleeper pair (7h sleeper + 3h off-duty), does not reset 11-hour driving
                    pair = self._create_split_sleeper_pair(
                        current_time, current_miles, current_day_number,
                        route_coordinates, total_distance_miles
                    )
                    for stop in pair:
                        planned_stops.append(stop)
                    # Record duty periods
                    all_duty_periods.append(DutyPeriod(
                        status=DutyStatus.SLEEPER_BERTH,
                        start_time=pair[0].arrival_time,
                        end_time=pair[0].departure_time,
                        location=pair[0].location,
                        remarks="Sleeper berth (split pair)"
                    ))
                    all_duty_periods.append(DutyPeriod(
                        status=DutyStatus.OFF_DUTY,
                        start_time=pair[1].arrival_time,
                        end_time=pair[1].departure_time,
                        location=pair[1].location,
                        remarks="Off duty (split pair)"
                    ))
                    current_time = pair[1].departure_time
                    driving_since_break = 0.0
                    # 14-hour window does not include split pair; advance window start accordingly
                    on_duty_window_start = on_duty_window_start + timedelta(hours=pair[0].duration_hours + pair[1].duration_hours)
                    logger.debug(f"Applied split sleeper pair at {current_miles:.1f} miles (11h limit)")
                else:
                    stop = self._create_rest_stop(
                        current_time, current_miles, current_day_number,
                        route_coordinates, total_distance_miles
                    )
                    planned_stops.append(stop)
                    all_duty_periods.append(DutyPeriod(
                        status=DutyStatus.SLEEPER_BERTH,
                        start_time=stop.arrival_time,
                        end_time=stop.departure_time,
                        location=stop.location,
                        remarks="10-hour rest (11-hour driving limit)"
                    ))
                    current_time = stop.departure_time
                    current_day_number += 1
                    driving_today = 0.0
                    driving_since_break = 0.0
                    on_duty_window_start = current_time
                    logger.debug(f"Added rest stop at {current_miles:.1f} miles (11h limit)")
            
            # 3. Check 14-hour on-duty window
            hours_on_duty = (current_time - on_duty_window_start).total_seconds() / 3600
            if hours_on_duty >= max_on_duty_window_today:
                if split_sleeper:
                    pair = self._create_split_sleeper_pair(
                        current_time, current_miles, current_day_number,
                        route_coordinates, total_distance_miles
                    )
                    for stop in pair:
                        planned_stops.append(stop)
                    all_duty_periods.append(DutyPeriod(
                        status=DutyStatus.SLEEPER_BERTH,
                        start_time=pair[0].arrival_time,
                        end_time=pair[0].departure_time,
                        location=pair[0].location,
                        remarks="Sleeper berth (split pair)"
                    ))
                    all_duty_periods.append(DutyPeriod(
                        status=DutyStatus.OFF_DUTY,
                        start_time=pair[1].arrival_time,
                        end_time=pair[1].departure_time,
                        location=pair[1].location,
                        remarks="Off duty (split pair)"
                    ))
                    current_time = pair[1].departure_time
                    driving_since_break = 0.0
                    # Exclude split pair from 14h window
                    on_duty_window_start = on_duty_window_start + timedelta(hours=pair[0].duration_hours + pair[1].duration_hours)
                    logger.debug(f"Applied split sleeper pair at {current_miles:.1f} miles (14h window)")
                else:
                    stop = self._create_rest_stop(
                        current_time, current_miles, current_day_number,
                        route_coordinates, total_distance_miles
                    )
                    planned_stops.append(stop)
                    all_duty_periods.append(DutyPeriod(
                        status=DutyStatus.SLEEPER_BERTH,
                        start_time=stop.arrival_time,
                        end_time=stop.departure_time,
                        location=stop.location,
                        remarks="10-hour rest (14-hour window limit)"
                    ))
                    current_time = stop.departure_time
                    current_day_number += 1
                    driving_today = 0.0
                    driving_since_break = 0.0
                    on_duty_window_start = current_time
                    logger.debug(f"Added rest stop at {current_miles:.1f} miles (14h limit)")
            
            # 4. Check 60/70-hour cycle limit; apply 34-hour restart
            if cycle_hours_used >= self.config.cycle_hours:
                # Apply 34-hour restart: off-duty block that resets cycle hours
                restart_start = current_time
                restart_end = restart_start + timedelta(hours=self.config.restart_hours)
                planned_stops.append(PlannedStop(
                    stop_type='rest',
                    location=f"34-hour restart at mile {current_miles:.0f}",
                    latitude=self._get_location_at_miles(route_coordinates, current_miles, total_distance_miles)[0],
                    longitude=self._get_location_at_miles(route_coordinates, current_miles, total_distance_miles)[1],
                    arrival_time=restart_start,
                    departure_time=restart_end,
                    duration_hours=self.config.restart_hours,
                    miles_from_start=current_miles,
                    day_number=current_day_number,
                    remarks="34-hour restart per §395.3(c)"
                ))
                all_duty_periods.append(DutyPeriod(
                    status=DutyStatus.OFF_DUTY,
                    start_time=restart_start,
                    end_time=restart_end,
                    location=f"Restart at mile {current_miles:.0f}",
                    remarks="34-hour restart"
                ))
                current_time = restart_end
                current_day_number += int(self.config.restart_hours // 24)
                driving_today = 0.0
                driving_since_break = 0.0
                on_duty_window_start = current_time
                cycle_hours_used = 0.0
                logger.debug(f"Applied 34-hour restart at {current_miles:.1f} miles")
            
            # 5. Check fuel stop requirement
            if miles_since_fuel >= self.config.fuel_interval_miles:
                stop = self._create_fuel_stop(
                    current_time, current_miles, current_day_number,
                    route_coordinates, total_distance_miles
                )
                planned_stops.append(stop)
                all_duty_periods.append(DutyPeriod(
                    status=DutyStatus.ON_DUTY_NOT_DRIVING,
                    start_time=stop.arrival_time,
                    end_time=stop.departure_time,
                    location=stop.location,
                    remarks="Fuel stop"
                ))
                current_time = stop.departure_time
                miles_since_fuel = 0.0
                hours_on_duty = (current_time - on_duty_window_start).total_seconds() / 3600
                logger.debug(f"Added fuel stop at {current_miles:.1f} miles")
            
            # 6. Check if we've reached pickup (if not passed)
            if not passed_pickup and current_miles >= pickup_miles_from_start:
                pickup_loc = locations.get('pickup', {})
                stop = PlannedStop(
                    stop_type='pickup',
                    location=pickup_loc.get('address', 'Pickup Location'),
                    latitude=pickup_loc.get('latitude', 0.0),
                    longitude=pickup_loc.get('longitude', 0.0),
                    arrival_time=current_time,
                    departure_time=current_time + timedelta(hours=self.config.pickup_duration_hours),
                    duration_hours=self.config.pickup_duration_hours,
                    miles_from_start=pickup_miles_from_start,
                    day_number=current_day_number,
                    remarks="Loading cargo at pickup location"
                )
                planned_stops.append(stop)
                all_duty_periods.append(DutyPeriod(
                    status=DutyStatus.ON_DUTY_NOT_DRIVING,
                    start_time=stop.arrival_time,
                    end_time=stop.departure_time,
                    location=stop.location,
                    remarks="Pickup - loading cargo"
                ))
                current_time = stop.departure_time
                hours_on_duty = (current_time - on_duty_window_start).total_seconds() / 3600
                passed_pickup = True
                logger.debug(f"Added pickup stop at {current_miles:.1f} miles")
            
            # Calculate how far we can drive in this segment
            remaining_drive_time_11h = max_drive_hours_today - driving_today
            remaining_drive_time_break = break_required_after - driving_since_break
            hours_until_14h = max_on_duty_window_today - hours_on_duty
            
            # Time until we hit any limit
            drive_time_limit = min(
                remaining_drive_time_11h,
                remaining_drive_time_break,
                hours_until_14h
            )
            
            # Calculate miles we can drive
            max_miles_this_segment = drive_time_limit * self.config.average_speed_mph
            
            # Check if pickup or dropoff is within this segment
            if not passed_pickup and (current_miles + max_miles_this_segment) >= pickup_miles_from_start:
                max_miles_this_segment = pickup_miles_from_start - current_miles
            
            if (current_miles + max_miles_this_segment) >= total_distance_miles:
                max_miles_this_segment = total_distance_miles - current_miles
            
            # Check fuel limit
            if (miles_since_fuel + max_miles_this_segment) >= self.config.fuel_interval_miles:
                max_miles_this_segment = self.config.fuel_interval_miles - miles_since_fuel
            
            # Drive this segment
            if max_miles_this_segment > 0:
                drive_hours = max_miles_this_segment / self.config.average_speed_mph
                drive_end_time = current_time + timedelta(hours=drive_hours)
                
                all_duty_periods.append(DutyPeriod(
                    status=DutyStatus.DRIVING,
                    start_time=current_time,
                    end_time=drive_end_time,
                    remarks=f"Driving {max_miles_this_segment:.1f} miles"
                ))
                
                current_time = drive_end_time
                current_miles += max_miles_this_segment
                miles_since_fuel += max_miles_this_segment
                driving_today += drive_hours
                driving_since_break += drive_hours
                cycle_hours_used += drive_hours
                
                logger.debug(
                    f"Drove {max_miles_this_segment:.1f} miles, "
                    f"now at {current_miles:.1f} miles, "
                    f"driving today: {driving_today:.1f}h"
                )
        
        # Add dropoff stop at the end
        if not passed_dropoff:
            dropoff_loc = locations.get('dropoff', {})
            stop = PlannedStop(
                stop_type='dropoff',
                location=dropoff_loc.get('address', 'Dropoff Location'),
                latitude=dropoff_loc.get('latitude', 0.0),
                longitude=dropoff_loc.get('longitude', 0.0),
                arrival_time=current_time,
                departure_time=current_time + timedelta(hours=self.config.dropoff_duration_hours),
                duration_hours=self.config.dropoff_duration_hours,
                miles_from_start=total_distance_miles,
                day_number=current_day_number,
                remarks="Unloading cargo at destination"
            )
            planned_stops.append(stop)
            all_duty_periods.append(DutyPeriod(
                status=DutyStatus.ON_DUTY_NOT_DRIVING,
                start_time=stop.arrival_time,
                end_time=stop.departure_time,
                location=stop.location,
                remarks="Dropoff - unloading cargo"
            ))
            current_time = stop.departure_time
        
        # Build daily summaries
        daily_summaries = self._build_daily_summaries(
            all_duty_periods, departure_time, current_day_number
        )
        
        # Calculate totals
        total_driving = sum(
            p.duration_hours for p in all_duty_periods 
            if p.status == DutyStatus.DRIVING
        )
        total_on_duty = sum(
            p.duration_hours for p in all_duty_periods 
            if p.status in [DutyStatus.DRIVING, DutyStatus.ON_DUTY_NOT_DRIVING]
        )
        
        return HOSPlan(
            planned_stops=planned_stops,
            daily_summaries=daily_summaries,
            total_driving_hours=total_driving,
            total_on_duty_hours=total_on_duty,
            total_trip_days=current_day_number,
            departure_time=departure_time,
            arrival_time=current_time,
            cycle_hours_remaining=self.config.cycle_hours - cycle_hours_used
        )

    def _create_split_sleeper_pair(
        self,
        current_time: datetime,
        current_miles: float,
        day_number: int,
        route_coordinates: List[Dict],
        total_miles: float
    ) -> List[PlannedStop]:
        """Create a split sleeper berth pair (7h sleeper + 3h off-duty)."""
        coords = self._get_location_at_miles(route_coordinates, current_miles, total_miles)
        sleeper = PlannedStop(
            stop_type='rest',
            location=f"Sleeper berth (split) at mile {current_miles:.0f}",
            latitude=coords[0],
            longitude=coords[1],
            arrival_time=current_time,
            departure_time=current_time + timedelta(hours=7.0),
            duration_hours=7.0,
            miles_from_start=current_miles,
            day_number=day_number,
            remarks="Sleeper berth split period (7h)"
        )
        offduty = PlannedStop(
            stop_type='break',
            location=f"Off duty (split) at mile {current_miles:.0f}",
            latitude=coords[0],
            longitude=coords[1],
            arrival_time=sleeper.departure_time,
            departure_time=sleeper.departure_time + timedelta(hours=3.0),
            duration_hours=3.0,
            miles_from_start=current_miles,
            day_number=day_number,
            remarks="Off-duty split period (3h)"
        )
        return [sleeper, offduty]
    
    def _create_break_stop(
        self,
        current_time: datetime,
        current_miles: float,
        day_number: int,
        route_coordinates: List[Dict],
        total_miles: float
    ) -> PlannedStop:
        """Create a 30-minute break stop."""
        coords = self._get_location_at_miles(
            route_coordinates, current_miles, total_miles
        )
        return PlannedStop(
            stop_type='break',
            location=f"Rest Area at mile {current_miles:.0f}",
            latitude=coords[0],
            longitude=coords[1],
            arrival_time=current_time,
            departure_time=current_time + timedelta(hours=self.config.break_duration_hours),
            duration_hours=self.config.break_duration_hours,
            miles_from_start=current_miles,
            day_number=day_number,
            remarks="30-minute break required after 8 hours driving"
        )
    
    def _create_rest_stop(
        self,
        current_time: datetime,
        current_miles: float,
        day_number: int,
        route_coordinates: List[Dict],
        total_miles: float
    ) -> PlannedStop:
        """Create a 10-hour rest stop."""
        coords = self._get_location_at_miles(
            route_coordinates, current_miles, total_miles
        )
        return PlannedStop(
            stop_type='rest',
            location=f"Truck Stop at mile {current_miles:.0f}",
            latitude=coords[0],
            longitude=coords[1],
            arrival_time=current_time,
            departure_time=current_time + timedelta(hours=self.config.off_duty_reset_hours),
            duration_hours=self.config.off_duty_reset_hours,
            miles_from_start=current_miles,
            day_number=day_number,
            remarks="10-hour off-duty rest period"
        )
    
    def _create_fuel_stop(
        self,
        current_time: datetime,
        current_miles: float,
        day_number: int,
        route_coordinates: List[Dict],
        total_miles: float
    ) -> PlannedStop:
        """Create a fuel stop."""
        coords = self._get_location_at_miles(
            route_coordinates, current_miles, total_miles
        )
        return PlannedStop(
            stop_type='fuel',
            location=f"Fuel Station at mile {current_miles:.0f}",
            latitude=coords[0],
            longitude=coords[1],
            arrival_time=current_time,
            departure_time=current_time + timedelta(hours=self.config.fuel_stop_duration_hours),
            duration_hours=self.config.fuel_stop_duration_hours,
            miles_from_start=current_miles,
            day_number=day_number,
            remarks="Fuel stop"
        )
    
    def _get_location_at_miles(
        self,
        route_coordinates: List[Dict],
        target_miles: float,
        total_miles: float
    ) -> Tuple[float, float]:
        """Get approximate coordinates at a given mile marker."""
        if not route_coordinates:
            return (0.0, 0.0)
        
        if target_miles <= 0:
            coord = route_coordinates[0]
            return (coord.get('latitude', 0), coord.get('longitude', 0))
        
        if target_miles >= total_miles:
            coord = route_coordinates[-1]
            return (coord.get('latitude', 0), coord.get('longitude', 0))
        
        percentage = target_miles / total_miles
        index = int(percentage * (len(route_coordinates) - 1))
        index = max(0, min(index, len(route_coordinates) - 1))
        
        coord = route_coordinates[index]
        return (coord.get('latitude', 0), coord.get('longitude', 0))
    
    def _build_daily_summaries(
        self,
        duty_periods: List[DutyPeriod],
        start_date: datetime,
        total_days: int
    ) -> List[DailyHOSSummary]:
        """Build daily summaries from duty periods."""
        summaries = []
        
        for day_num in range(1, total_days + 1):
            day_start = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_start += timedelta(days=day_num - 1)
            day_end = day_start + timedelta(days=1)
            
            summary = DailyHOSSummary(
                date=day_start,
                day_number=day_num,
                duty_periods=[]
            )
            
            for period in duty_periods:
                # Check if this period overlaps with this day
                if period.end_time <= day_start or period.start_time >= day_end:
                    continue
                
                # Calculate overlap
                overlap_start = max(period.start_time, day_start)
                overlap_end = min(period.end_time, day_end)
                hours = (overlap_end - overlap_start).total_seconds() / 3600
                
                if hours > 0:
                    # Create a day-specific period
                    day_period = DutyPeriod(
                        status=period.status,
                        start_time=overlap_start,
                        end_time=overlap_end,
                        location=period.location,
                        remarks=period.remarks
                    )
                    summary.duty_periods.append(day_period)
                    
                    # Update totals
                    if period.status == DutyStatus.DRIVING:
                        summary.driving_hours += hours
                        summary.miles_driven += hours * self.config.average_speed_mph
                    elif period.status == DutyStatus.ON_DUTY_NOT_DRIVING:
                        summary.on_duty_hours += hours
                    elif period.status == DutyStatus.OFF_DUTY:
                        summary.off_duty_hours += hours
                    elif period.status == DutyStatus.SLEEPER_BERTH:
                        summary.sleeper_berth_hours += hours
            
            # Fill remaining hours with off-duty if day not complete
            total = summary.total_hours
            if total < 24:
                summary.off_duty_hours += (24 - total)
            
            summaries.append(summary)
        
        return summaries
    
    def validate_hos_compliance(self, hos_plan: HOSPlan) -> Dict:
        """
        Validate that a HOS plan is compliant with regulations.
        
        Returns dict with compliance status and any violations.
        """
        violations = []
        
        for summary in hos_plan.daily_summaries:
            if summary.driving_hours > self.config.max_driving_hours:
                violations.append(
                    f"Day {summary.day_number}: Driving hours ({summary.driving_hours:.1f}) "
                    f"exceed {self.config.max_driving_hours}h limit"
                )
            
            if (summary.driving_hours + summary.on_duty_hours) > self.config.max_on_duty_hours:
                violations.append(
                    f"Day {summary.day_number}: On-duty hours exceed {self.config.max_on_duty_hours}h limit"
                )
        
        return {
            'compliant': len(violations) == 0,
            'violations': violations
        }
