# Distributed Air Traffic Control (ATC) Simulation

A distributed, event-driven air traffic control simulation built with Python microservices communicating via RabbitMQ, using Redis for real-time state and PostgreSQL for persistence. Features a real-time Leaflet-based dashboard with live aircraft tracking, sector boundaries, conflict visualization, and runway operations at Toronto Pearson (YYZ).

## Architecture

```
┌──────────────┐    aircraft.position     ┌───────────────┐
│    Radar     │ ──────────────────────►  │  Sector A/B   │
│   Service    │                          │   Services    │
│  (waypoint   │                          │ (ownership +  │
│   sim)       │                          │   handoff)    │
└──────┬───────┘                          └──┬────┬───────┘
       │                                     │    │
       │ aircraft.position                   │    │ runway.request
       │◄─── reads clearance from Redis ─────┘    │
       ▼                                          ▼
┌──────────────┐    conflict.alert        ┌──────────────┐
│   Conflict   │ ──────────────────────►  │    Runway     │
│   Detection  │                          │   Service     │
│   Service    │                          │ (queue+lock)  │
└──────┬───────┘                          └──────┬────────┘
       │                                         │ runway.assigned
       ▼                                         ▼
┌──────────────────────────────────────────────────────────┐
│                    Gateway Service                        │
│     (WebSocket bridge → Leaflet dashboard + reset API)   │
└──────────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────────────────────────────────────────────────┐
│                    Logging Service                        │
│            (persists ALL events to PostgreSQL)            │
└──────────────────────────────────────────────────────────┘
```

### Clearance Feedback Loop

The system implements a closed-loop clearance flow for runway operations:

1. **Sector** detects aircraft needing a runway → publishes `runway.request`
2. **Runway** allocates a runway → publishes `runway.assigned`
3. **Sector** receives assignment → writes clearance flag to Redis (`clearance:{ac_id}`)
4. **Radar** reads clearance from Redis → advances aircraft state machine (e.g., HOLDING → APPROACH, TAXI → TAKEOFF_ROLL)

### Infrastructure

| Component      | Role                                                               | External Port |
|---------------|--------------------------------------------------------------------|----|
| **RabbitMQ**  | Async event bus (topic exchange `atc.events`)                     | 5672 (AMQP), 15672 (Management UI) |
| **Redis**     | Real-time shared state (positions, ownership, runway queues/locks) | 6380 |
| **PostgreSQL** | Persistent storage (event log, flight plans)                      | 5432 |

### Services

| Service          | Port | Description                                                    |
|-----------------|------|----------------------------------------------------------------|
| **Radar**        | 8001 | Waypoint-based aircraft simulation, publishes positions every 2s |
| **Sector A**     | 8002 | Manages aircraft in sector A (lon -79.7 to -79.45)            |
| **Sector B**     | 8012 | Manages aircraft in sector B (lon -79.45 to -79.2)            |
| **Runway**       | 8003 | Manages YYZ runway allocation via distributed queue + lock     |
| **Conflict**     | 8004 | Detects separation violations between aircraft                  |
| **Gateway**      | 8005 | WebSocket bridge + Leaflet dashboard + reset API               |
| **Logging**      | 8006 | Persists all events to PostgreSQL                               |

## Aircraft Simulation

### Scenario

The simulation runs two aircraft at Toronto Pearson International Airport (YYZ):

| Aircraft   | Callsign | Operation  | Start State                     | End State  |
|-----------|----------|------------|---------------------------------|------------|
| **WJA512** | WestJet 512 | Departure | Taxiway near RWY 06L          | Departed (climbing out) |
| **ACA845** | Air Canada 845 | Arrival | Elliptical holding pattern     | Landed on assigned runway |

### State Machine Phases

**WJA512 (Departure):** `TAXI` → `TAKEOFF_ROLL` → `CLIMBING` → `DEPARTED`

**ACA845 (Arrival):** `HOLDING` → `APPROACH` → `FINAL` → `LANDED`

Each phase uses waypoint interpolation with tuples of `(lat, lon, altitude_ft, speed_kts, ticks_to_next)` to calculate smooth position, altitude, speed, and heading transitions.

### Holding Pattern

ACA845 flies an elliptical racetrack pattern centered at (43.72, -79.48) with semi-axes 0.015° (lat) x 0.025° (lon) at 5000 ft / 220 kts until receiving landing clearance.

## Communication Workflow

### RabbitMQ Exchange & Routing Keys

All services communicate through a single **topic exchange**: `atc.events`

| Routing Key                  | Publisher       | Subscribers                            |
|-----------------------------|-----------------|----------------------------------------|
| `aircraft.position`          | Radar           | Sector A/B, Conflict, Gateway, Logging |
| `aircraft.handoff.request`   | Sector (source) | Sector (target), Logging               |
| `aircraft.handoff.accepted`  | Sector (target) | Sector (source), Logging               |
| `runway.request`             | Sector          | Runway, Logging                        |
| `runway.assigned`            | Runway          | Sector A/B, Gateway, Logging           |
| `conflict.alert`             | Conflict        | Gateway, Logging                       |

### Event Envelope (Standard)

Every event JSON follows this schema:

```json
{
  "event_id": "uuid",
  "timestamp": "2026-01-15T10:30:00.000Z",
  "type": "aircraft.position",
  "aircraft_id": "WJA512",
  "source_service": "radar",
  "data": { ... }
}
```

### Event Flow

1. **Radar** generates 2 aircraft (WJA512, ACA845) using waypoint-based state machine, publishes `aircraft.position` every 2s
2. **Sector A/B** receive positions → store in Redis (`pos:{id}`, `owner:{id}`) → detect boundary crossings → publish `aircraft.handoff.request`
3. Receiving **Sector** accepts handoff → publishes `aircraft.handoff.accepted` → claims ownership
4. **Sector** detects aircraft needing runway (holding/landing or taxi/takeoff) → publishes `runway.request`
5. **Runway** enqueues aircraft in Redis list → processor (every 5s) acquires runway lock checking conflict groups → publishes `runway.assigned`
6. **Sector** receives `runway.assigned` → writes clearance flag to Redis (`clearance:{id}`, `runway:{id}`)
7. **Radar** reads clearance from Redis → advances aircraft phase (e.g., HOLDING → APPROACH)
8. **Conflict** compares each position against all tracked aircraft → publishes `conflict.alert` on separation violation
9. **Gateway** forwards `aircraft.position`, `conflict.alert`, `runway.assigned` to WebSocket clients
10. **Logging** captures ALL events (`#` wildcard) → persists to `event_log` table

## Redis Key Schema

| Key Pattern              | Type          | TTL  | Description                              |
|-------------------------|---------------|------|------------------------------------------|
| `pos:{aircraft_id}`      | String (JSON) | 30s  | Latest aircraft position                 |
| `owner:{aircraft_id}`    | String        | 15s  | Sector ID that controls the aircraft     |
| `clearance:{aircraft_id}`| String        | 120s | Runway clearance type (takeoff/landing)  |
| `runway:{aircraft_id}`   | String        | 120s | Assigned runway ID                       |
| `rwyop:{aircraft_id}`    | String        | 300s | Operation type (takeoff/landing)         |
| `runwayq:{airport_id}`   | List          | --   | FIFO queue of aircraft awaiting runway   |
| `runwaylock:{runway_id}` | String        | 30s  | Distributed lock for runway usage        |
| `dedup:{event_id}`       | String        | 300s | Deduplication guard                      |
| `sim:reset`              | String        | 10s  | Reset signal from gateway to radar       |

## PostgreSQL Schema

### `event_log`

| Column          | Type          | Notes                    |
|----------------|---------------|--------------------------|
| id             | TEXT (UUID)   | Primary key              |
| event_id       | UUID          | Unique, from event envelope |
| event_type     | TEXT          | Routing key              |
| aircraft_id    | TEXT          | Aircraft identifier      |
| source_service | TEXT          | Originating service      |
| timestamp      | TIMESTAMPTZ   | Event time               |
| payload        | JSONB         | Event data object        |

Indexes on `event_type`, `aircraft_id`, and `timestamp`.

### `flight_plans` (stub)

| Column            | Type        | Notes              |
|------------------|-------------|--------------------|
| id               | UUID        | Primary key        |
| aircraft_id      | TEXT        | Aircraft identifier |
| origin           | TEXT        | Origin airport     |
| destination      | TEXT        | Destination airport |
| planned_departure | TIMESTAMPTZ | Scheduled departure |
| planned_arrival   | TIMESTAMPTZ | Scheduled arrival   |
| created_at       | TIMESTAMPTZ | Record creation time |

## Runway System

### YYZ Runways

| Runway     | Conflict Group | Notes                    |
|-----------|---------------|--------------------------|
| **RWY 06L** | Group A       | Parallel operations safe |
| **RWY 06R** | Group A       | Parallel operations safe |

Runways in the same conflict group can operate simultaneously. Cross-group runways conflict and cannot be allocated at the same time.

### Allocation Logic

1. Aircraft enqueued in `runwayq:{airport_id}` FIFO list
2. Processor runs every 5s, dequeues one aircraft
3. Checks for non-conflicting runway availability
4. Acquires distributed lock (`runwaylock:{runway_id}`, 30s TTL)
5. Publishes `runway.assigned` event

## Sector Boundaries

| Sector     | Longitude Range       | Latitude Range       |
|-----------|----------------------|---------------------|
| **Sector A** | -79.70 to -79.45   | 43.55 to 43.80     |
| **Sector B** | -79.45 to -79.20   | 43.55 to 43.80     |

Split at longitude **-79.45**. Aircraft crossing this boundary trigger the handoff protocol (two-phase: request → accept → ownership transfer).

## Dashboard

The gateway serves a real-time Leaflet-based ATC dashboard at `http://localhost:8005` featuring:

- **Live map** with sector boundary overlays (cyan for A, purple for B)
- **YYZ runway overlays** with labeled runway positions
- **Aircraft markers** with heading-based rotation and color-coded trails
- **Aircraft info cards** showing ALT, SPD, HDG, LAT, LON, V/S
- **Conflict visualization** with dashed red lines between violating aircraft
- **Event log** (scrollable, filterable by event type)
- **Stats panel** showing event count, aircraft count, conflicts, and runway operations
- **Reset button** (POST `/api/reset`) to clear all Redis state and restart simulation

## How to Run

### Prerequisites

- Docker and Docker Compose installed

### Start the System

```bash
# Copy environment file
cp .env.example .env

# Build and start all services
docker compose up --build
```

### Access Points

| What                     | URL                              |
|-------------------------|----------------------------------|
| ATC Dashboard           | http://localhost:8005             |
| RabbitMQ Management UI  | http://localhost:15672 (guest/guest) |
| Radar health            | http://localhost:8001/health      |
| Sector A health         | http://localhost:8002/health      |
| Sector B health         | http://localhost:8012/health      |
| Runway health           | http://localhost:8003/health      |
| Conflict health         | http://localhost:8004/health      |
| Gateway health          | http://localhost:8005/health      |
| Logging health          | http://localhost:8006/health      |

### Stop the System

```bash
docker compose down

# To also remove volumes (database data):
docker compose down -v
```

## How to Verify the System is Working

1. **Start the system** and wait ~30 seconds for all services to connect.

2. **Check all health endpoints:**
   ```bash
   for port in 8001 8002 8012 8003 8004 8005 8006; do
     echo "Port $port: $(curl -s http://localhost:$port/health)"
   done
   ```

3. **Open the dashboard** at http://localhost:8005 -- you should see the Leaflet map with sector boundaries, runway overlays, and live aircraft markers moving along their routes.

4. **Check RabbitMQ** at http://localhost:15672 -- verify the `atc.events` exchange exists with bindings.

5. **Check Redis state:**
   ```bash
   docker compose exec redis redis-cli KEYS "*"
   ```
   You should see `pos:WJA512`, `pos:ACA845`, `owner:WJA512`, `clearance:*`, etc.

6. **Check PostgreSQL event log:**
   ```bash
   docker compose exec postgres psql -U atc -d atc_db -c \
     "SELECT event_type, aircraft_id, timestamp FROM event_log ORDER BY timestamp DESC LIMIT 10;"
   ```

7. **Watch the full scenario** -- WJA512 should taxi and depart, ACA845 should hold then approach and land. Conflict alerts may appear when aircraft are close together.

8. **Reset the simulation** -- click the Reset button on the dashboard or:
   ```bash
   curl -X POST http://localhost:8005/api/reset
   ```

## Environment Variables

| Variable              | Default                                      | Description                    |
|----------------------|----------------------------------------------|--------------------------------|
| `AMQP_URL`          | `amqp://guest:guest@rabbitmq:5672/`          | RabbitMQ connection string     |
| `REDIS_URL`         | `redis://redis:6379/0`                       | Redis connection string        |
| `POSTGRES_DSN`      | `postgresql://atc:atc_secret@postgres:5432/atc_db` | PostgreSQL connection string |
| `RADAR_INTERVAL`    | `2`                                          | Seconds between position updates |
| `LOG_LEVEL`         | `INFO`                                       | Logging level                  |

## Project Structure

```
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
├── infra/
│   └── postgres/
│       └── init.sql              # DB schema (auto-run on first start)
├── shared/                        # Shared Python package
│   ├── pyproject.toml
│   └── shared/
│       ├── __init__.py
│       ├── events.py              # ATCEvent model + routing keys
│       ├── rabbitmq.py            # Publish/subscribe helpers
│       ├── redis_utils.py         # JSON, lock, queue, dedupe helpers
│       ├── postgres.py            # Connection pool + insert helpers
│       └── logging_config.py      # Structured logging setup
└── services/
    ├── radar/                     # Radar Simulation Service
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py
    │       ├── api/health.py
    │       ├── domain/aircraft.py           # Aircraft models, waypoints, holding pattern
    │       ├── services/position_updater.py # Phase state machine, waypoint interpolation
    │       └── workers/position_broadcaster.py
    ├── sector/                    # Sector Control Service
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py
    │       ├── api/health.py
    │       ├── domain/sector.py             # Sector boundaries, ownership logic
    │       ├── services/
    │       │   ├── handle_position.py       # Position tracking, handoff triggers
    │       │   ├── handle_handoff.py        # Handoff request/acceptance protocol
    │       │   └── handle_clearance.py      # Write clearance flags to Redis
    │       └── workers/sector_consumer.py
    ├── runway/                    # Runway & Ground Control Service
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py
    │       ├── api/health.py
    │       ├── domain/runway.py             # YYZ runways, conflict groups
    │       ├── services/assign_runway.py    # Dequeue + lock + conflict check
    │       ├── workers/runway_consumer.py
    │       └── workers/runway_processor.py  # Background task (every 5s)
    ├── conflict/                  # Conflict Detection Service
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py
    │       ├── api/health.py
    │       ├── domain/rules.py              # Separation minimums, haversine distance
    │       ├── services/detect_conflicts.py
    │       └── workers/conflict_consumer.py
    ├── gateway/                   # WebSocket Gateway Service
    │   ├── Dockerfile
    │   ├── requirements.txt
    │   └── app/
    │       ├── main.py
    │       ├── api/
    │       │   ├── health.py
    │       │   ├── ws.py                    # WebSocket /ws endpoint
    │       │   └── reset.py                 # POST /api/reset endpoint
    │       ├── workers/gateway_consumer.py
    │       └── static/index.html            # Leaflet-based ATC dashboard
    └── logging/                   # Persistence / Logging Service
        ├── Dockerfile
        ├── requirements.txt
        └── app/
            ├── main.py
            ├── api/health.py
            └── workers/log_consumer.py      # Wildcard (#) subscription
```

## Per-Service Architecture (Layered)

Each service follows the same layered pattern:

```
app/
├── main.py          # FastAPI app, lifespan (startup/shutdown)
├── api/             # HTTP routes (health, REST endpoints)
├── domain/          # Models, rules, business entities
├── services/        # Business use cases (handle_position, detect_conflicts, etc.)
└── workers/         # Message consumers and background tasks
```

## Conflict Detection Rules

| Parameter              | Value    | Description                              |
|-----------------------|----------|------------------------------------------|
| Horizontal separation | 0.05°   | ~5.5 km minimum horizontal distance      |
| Vertical separation   | 1000 ft | Minimum altitude difference               |

A conflict alert is triggered when two aircraft violate **both** minimums simultaneously.
