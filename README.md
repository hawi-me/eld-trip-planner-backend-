# ELD Trip Planner - Backend

A Django REST API for Electronic Logging Device (ELD) trip planning with FMCSA Hours of Service (HOS) compliance.

## Features

- **Trip Planning API**: Calculate routes with pickup/dropoff locations
- **FMCSA HOS Compliance**: Automatic enforcement of driving limits, breaks, and rest periods
- **ELD Log Generation**: Generate daily log sheets in JSON format for frontend rendering
- **Route Calculation**: Free routing using OSRM (no API key required)
- **Geocoding**: Address-to-coordinates conversion using Nominatim

## FMCSA HOS Rules Implemented

| Rule | Description |
|------|-------------|
| 70-Hour/8-Day | Max 70 hours on-duty in any 8 consecutive days |
| 11-Hour Driving | Max 11 hours driving after 10 consecutive hours off-duty |
| 14-Hour Window | Cannot drive beyond 14th hour after coming on-duty |
| 30-Minute Break | Required after 8 hours of cumulative driving |
| 10-Hour Off-Duty | Required before new driving period |
| Fuel Stops | Every ~1,000 miles |
| Loading Time | 1 hour for pickup, 1 hour for dropoff |

## Project Structure

```
eld-trip-planner-backend/
├── core/                    # Django project settings
│   ├── settings.py          # Main settings with CORS, REST config
│   ├── urls.py              # Root URL configuration
│   └── wsgi.py              # WSGI entry point
├── trips/                   # Main application
│   ├── models.py            # Trip, TripStop, ELDLogEntry models
│   ├── views.py             # API views
│   ├── serializers.py       # DRF serializers
│   ├── urls.py              # App URL routes
│   ├── admin.py             # Django admin config
│   └── services/            # Business logic layer
│       ├── route_service.py # Route calculation (OSRM/ORS)
│       ├── hos_service.py   # FMCSA HOS logic
│       └── eld_service.py   # ELD log generation
├── manage.py
├── requirements.txt
└── README.md
```

## API Endpoints

### Health Check
```
GET /api/health/

Response:
{
    "status": "healthy",
    "message": "ELD Trip Planner API is running",
    "version": "1.0.0",
    "timestamp": "2024-01-15T10:30:00Z"
}
```

### Plan Trip
```
POST /api/trips/plan/

Request Body:
{
    "current_location": "Chicago, IL",
    "pickup_location": "Indianapolis, IN",
    "dropoff_location": "Nashville, TN",
    "current_cycle_used_hours": 0
}

Response:
{
    "trip_id": "uuid",
    "total_distance_miles": 456.2,
    "total_trip_duration_hours": 12.5,
    "estimated_days": 2,
    "route_coordinates": [
        {"latitude": 41.8781, "longitude": -87.6298},
        ...
    ],
    "route_polyline": "encoded_polyline_string",
    "planned_stops": [
        {
            "stop_type": "pickup",
            "location": "Indianapolis, IN",
            "latitude": 39.7684,
            "longitude": -86.1581,
            "arrival_time": "2024-01-15T09:15:00",
            "departure_time": "2024-01-15T10:15:00",
            "duration_hours": 1.0,
            "miles_from_start": 181.5,
            "day_number": 1,
            "remarks": "Loading cargo"
        },
        ...
    ],
    "daily_logs": [
        {
            "date": "2024-01-15",
            "day_number": 1,
            "entries": [...],
            "summary": {
                "off_duty": 10.0,
                "sleeper_berth": 0.0,
                "driving": 11.0,
                "on_duty_not_driving": 3.0
            },
            "grid_data": {...}
        }
    ],
    "total_driving_hours": 8.3,
    "total_on_duty_hours": 10.3,
    "departure_time": "2024-01-15T06:00:00",
    "estimated_arrival_time": "2024-01-15T18:30:00"
}
```

### Get Route Only (No HOS)
```
GET /api/trips/route/?current_location=Chicago,IL&pickup_location=Indianapolis,IN&dropoff_location=Nashville,TN

Response:
{
    "locations": {...},
    "total_distance_miles": 456.2,
    "total_duration_hours": 7.5,
    "route_coordinates": [...],
    "encoded_polyline": "..."
}
```

## Installation

### 1. Clone and Setup Virtual Environment

```bash
cd eld-trip-planner-backend
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/Mac
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run Migrations

```bash
python manage.py migrate
```

### 4. Run Development Server

```bash
python manage.py runserver
```

The API will be available at `http://localhost:8000/api/`

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DJANGO_SECRET_KEY` | Django secret key | Dev key (change in prod) |
| `DJANGO_DEBUG` | Debug mode | `True` |
| `DJANGO_ALLOWED_HOSTS` | Allowed hosts | `localhost,127.0.0.1` |
| `CORS_ALLOWED_ORIGINS` | CORS origins | `http://localhost:3000,http://localhost:5173` |
| `ROUTING_PROVIDER` | `osrm` or `openrouteservice` | `osrm` |
| `OPENROUTESERVICE_API_KEY` | ORS API key (if using ORS) | - |

### Routing Providers

**OSRM (Default)** - Free, no API key required
- Uses public demo server: `https://router.project-osrm.org`
- Good for development and moderate traffic

**OpenRouteService** - Requires free API key
- Sign up at: https://openrouteservice.org/dev/#/signup
- Better rate limits and truck-specific routing

## Running Tests

```bash
pytest
```

Or with Django test runner:

```bash
python manage.py test trips
```

## Frontend Integration

The API returns ELD log data structured for easy frontend rendering:

```javascript
// Example: Drawing the ELD log grid
const gridData = dailyLog.grid_data;

gridData.segments.forEach(segment => {
    // Draw horizontal line from start_x to end_x on row
    drawLine(segment.start_x, segment.row, segment.end_x, segment.row);
});

gridData.transitions.forEach(transition => {
    // Draw vertical line for status changes
    drawVerticalLine(transition.x, transition.from_row, transition.to_row);
});
```

## Production Deployment

1. Set `DJANGO_DEBUG=False`
2. Set a secure `DJANGO_SECRET_KEY`
3. Configure `DJANGO_ALLOWED_HOSTS`
4. Use gunicorn: `gunicorn core.wsgi:application`
5. Set up HTTPS with nginx/Apache
6. Consider using PostgreSQL for database

## License

MIT License
