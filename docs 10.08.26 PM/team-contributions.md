# Distributed Air Traffic Control System — Project Overview & Team Contributions

**Course:** COE892 — Distributed Cloud Computing, Toronto Metropolitan University, W2026
**Instructor:** Dr. Muhammad Jaseemuddin
**Group:** 21

---

## The Complete Project

### What We Built

A fully distributed, event-driven air traffic control simulation modeled around **Toronto Pearson International Airport (YYZ)**. The system simulates real-world ATC operations — aircraft departures, arrivals, sector handoffs, runway allocation, and conflict detection — using a microservices architecture where every service communicates asynchronously through a message broker.

The simulation runs two aircraft simultaneously:

- **WJA512 (WestJet 512)** — Departure: TAXI → TAKEOFF_ROLL → CLIMBING → DEPARTED
- **ACA845 (Air Canada 845)** — Arrival: HOLDING → APPROACH → FINAL → LANDED

### Technology Stack

| Technology | Role |
|---|---|
| **Python 3.11 / FastAPI** | Backend microservices and REST APIs |
| **RabbitMQ** | Message broker (topic exchange `atc.events`) for asynchronous inter-service communication |
| **Redis** | In-memory shared state (aircraft positions, ownership, clearances, runway locks, queues) |
| **PostgreSQL** | Persistent event log and audit trail |
| **Docker & Docker Compose** | Containerization and orchestration of all 10 services |
| **Leaflet.js** | Interactive map-based real-time dashboard |
| **WebSockets** | Real-time bidirectional streaming from backend to browser |

### System Architecture

The system is composed of **6 application services** and **3 infrastructure services**:

| Service | Port | Description |
|---|---|---|
| **RabbitMQ** | 5672 / 15672 | Message broker with topic exchange |
| **Redis** | 6379 | Real-time state store and distributed locking |
| **PostgreSQL** | 5432 | Persistent storage for event logs |
| **Radar** | 8001 | Simulates aircraft movement, publishes position updates every 2s |
| **Sector A** | 8002 | Manages western airspace sector, handles ownership and handoffs |
| **Sector B** | 8012 | Manages eastern airspace sector, handles ownership and handoffs |
| **Runway** | 8003 | Queues and allocates runways using distributed locking |
| **Conflict** | 8004 | Detects separation violations between aircraft pairs |
| **Gateway** | 8005 | WebSocket bridge + serves the Leaflet.js dashboard |
| **Logging** | 8006 | Persists every event to PostgreSQL via wildcard subscription |

### Event Flow (End-to-End)

All services communicate through a single RabbitMQ topic exchange (`atc.events`) using a standard event envelope (`ATCEvent`). The event types and their flow:

| Routing Key | Publisher | Consumers |
|---|---|---|
| `aircraft.position` | Radar | Sector A/B, Conflict, Gateway, Logging |
| `aircraft.handoff.request` | Sector (source) | Sector (target), Logging |
| `aircraft.handoff.accepted` | Sector (target) | Sector (source), Logging |
| `runway.request` | Sector | Runway, Logging |
| `runway.assigned` | Runway | Sector A/B, Gateway, Logging |
| `conflict.alert` | Conflict | Gateway, Logging |

**The simulation loop works as follows:**

1. **Radar** broadcasts aircraft positions every 2 seconds.
2. **Sector A/B** consume positions, claim ownership in Redis, and detect when aircraft cross the sector boundary at longitude -79.45.
3. A **two-phase handoff protocol** transfers ownership between sectors (request → accepted) to prevent race conditions.
4. When a sector detects an aircraft needing a runway (departing in TAXI or arriving in HOLDING), it publishes a `runway.request`.
5. The **Runway** service enqueues the aircraft, then a background processor (every 5s) allocates a runway using conflict-group checks and distributed locks.
6. The sector receives `runway.assigned`, writes clearance flags to Redis (`clearance:{id}`, `runway:{id}`).
7. **Radar** reads the clearance flags and advances the aircraft to the next phase (e.g., TAXI → TAKEOFF_ROLL, HOLDING → APPROACH).
8. **Conflict** checks every position update against all tracked aircraft and publishes `conflict.alert` when separation minimums are violated (horizontal < 0.05 degrees AND vertical < 1000 ft).
9. **Gateway** pushes all relevant events to the browser dashboard over WebSocket.
10. **Logging** captures every event via wildcard `#` subscription and persists it to PostgreSQL.

### Shared Library

A common Python package (`shared/`) is installed by all services, providing:

- **`events.py`** — `ATCEvent` Pydantic model and routing key constants
- **`rabbitmq.py`** — Connection with retry logic, topic exchange declaration, publish/subscribe helpers
- **`redis_utils.py`** — JSON get/set, distributed locks (SETNX + TTL), FIFO queues, deduplication
- **`postgres.py`** — Async connection pooling (asyncpg), event log insertion with dedup
- **`logging_config.py`** — Structured logging via structlog

### Key Distributed Systems Patterns

- **Event-Driven Architecture**: All communication via RabbitMQ topic exchange; services are fully decoupled
- **Distributed Locking**: Redis SETNX with TTLs for runway allocation and ownership consistency
- **State Machine**: Aircraft progress through well-defined flight phases, gated by clearance flags
- **Two-Phase Handoff Protocol**: Prevents race conditions during sector transitions
- **Deduplication**: Redis keys prevent duplicate runway requests and duplicate event processing
- **Closed-Loop Feedback**: Sector → Runway → Sector → Radar creates the feedback loop that drives the simulation forward
- **Audit Trail**: Every event persisted to PostgreSQL for compliance and debugging

---

## Team Member Contributions

### Muhammad Khan

**Assigned:** Radar Simulation Service, aircraft/waypoint models, Docker/Docker Compose, RabbitMQ and shared event/messaging setup.

**What was built:**

- **Radar Simulation Service** (`services/radar/`)
  - FastAPI application with background task that loops every 2 seconds (configurable via `RADAR_INTERVAL`)
  - Aircraft state machine with 8 flight phases: TAXI, TAKEOFF_ROLL, CLIMBING, DEPARTED (departures) and HOLDING, APPROACH, FINAL, LANDED (arrivals)
  - Waypoint-based position interpolation system — predefined paths per runway (RWY_06L for takeoff, RWY_06R for approach) with lat, lon, altitude, speed, and tick-count per segment
  - Clearance-gated phase transitions: Radar reads `clearance:{aircraft_id}` and `runway:{aircraft_id}` from Redis before advancing aircraft state
  - Simulation reset mechanism: detects `sim:reset` flag in Redis and restores both aircraft to initial state
  - Two simulated aircraft: WJA512 (WestJet departure) and ACA845 (Air Canada arrival)

- **Aircraft & Waypoint Models** (`services/radar/app/domain/aircraft.py`)
  - `SimAircraft` model with phase tracking, tick counters, and waypoint path selection
  - Position updater service (`services/radar/app/services/position_updater.py`) implementing the full state machine tick logic
  - Position broadcaster worker (`services/radar/app/workers/position_broadcaster.py`) driving the main simulation loop

- **Docker & Docker Compose Setup** (`docker-compose.yml`, Dockerfiles)
  - Full multi-container orchestration: 10 services (3 infrastructure + 7 application containers including Sector A and B)
  - Consistent Dockerfile pattern for all services: Python 3.11-slim base, shared package installation, per-service requirements, uvicorn entrypoint
  - Health checks for RabbitMQ (`rabbitmq-diagnostics`), Redis (`redis-cli ping`), and PostgreSQL (`pg_isready`)
  - Dependency ordering with `depends_on` and health check conditions so app services start only after infrastructure is ready
  - Environment variable configuration via `.env.example` (AMQP_URL, REDIS_URL, POSTGRES_DSN, LOG_LEVEL, SECTOR_ID, RADAR_INTERVAL)
  - Persistent volume for PostgreSQL data (`pgdata`)

- **RabbitMQ & Shared Messaging Setup** (`shared/shared/rabbitmq.py`, `shared/shared/events.py`)
  - `ATCEvent` Pydantic model — the standard event envelope used by every service (event_id, timestamp, type, aircraft_id, source_service, data)
  - 6 routing key constants defining the entire event vocabulary of the system
  - RabbitMQ connection helper with 10-retry backoff strategy (3s intervals)
  - Topic exchange declaration (`atc.events`)
  - `publish()` and `subscribe()` helpers abstracting away AMQP details — subscribe creates a durable queue, binds it to a routing key, and invokes a callback with parsed ATCEvent objects

---

### Shaheer Hassan

**Assigned:** Sector Control Services and handoff protocol, Conflict Detection Service, Redis schema and shared state usage.

**What was built:**

- **Sector Control Services** (`services/sector/`)
  - Single codebase deployed as two instances via `SECTOR_ID` environment variable (SECTOR_A on port 8002, SECTOR_B on port 8012)
  - Sector boundary definitions (`services/sector/app/domain/sector.py`): Sector A covers longitude -79.7 to -79.45, Sector B covers -79.45 to -79.2 (both latitude 43.5 to 43.8)
  - **Position handling** (`services/sector/app/services/handle_position.py`): Consumes `aircraft.position` events, updates `pos:{aircraft_id}` in Redis (TTL 30s), claims ownership via `owner:{aircraft_id}` (TTL 15s) when aircraft is inside sector boundary, and detects when aircraft has left the sector to trigger handoff
  - **Two-phase handoff protocol** (`services/sector/app/services/handle_handoff.py`): Source sector publishes `aircraft.handoff.request` with from_sector, to_sector, and coordinates; target sector receives, claims ownership, and publishes `aircraft.handoff.accepted`; prevents race conditions on sector transitions
  - **Runway request detection**: Identifies when departing aircraft (TAXI phase) or arriving aircraft (HOLDING phase) need a runway and publishes `runway.request` with deduplication guard (`rwy_requested:{aircraft_id}`, TTL 300s)
  - **Clearance handling** (`services/sector/app/services/handle_clearance.py`): Consumes `runway.assigned` events and writes clearance flags to Redis (`clearance:{aircraft_id}` = "takeoff"/"landing", `runway:{aircraft_id}` = runway ID, both TTL 120s) so the Radar can advance the aircraft
  - Consumer worker (`services/sector/app/workers/sector_consumer.py`) subscribing to `aircraft.position`, `aircraft.handoff.request`, `aircraft.handoff.accepted`, and `runway.assigned`

- **Conflict Detection Service** (`services/conflict/`)
  - Consumes every `aircraft.position` event and maintains an in-memory set of tracked aircraft IDs
  - Separation rules (`services/conflict/app/domain/rules.py`): Horizontal minimum of 0.05 degrees (~5.5 km), vertical minimum of 1000 ft; both must be violated simultaneously to trigger an alert
  - Distance calculation via `haversine_approx()` — simplified Euclidean distance in degrees
  - Detection logic (`services/conflict/app/services/detect_conflicts.py`): On each position event, compares the aircraft against all other tracked aircraft by fetching their last known positions from Redis; publishes `conflict.alert` with both aircraft coordinates when separation is violated
  - Consumer worker (`services/conflict/app/workers/conflict_consumer.py`) handling the position subscription

- **Redis Schema & Shared State** (`shared/shared/redis_utils.py`)
  - Designed the Redis key schema used across all services:
    - `pos:{aircraft_id}` — JSON position data (TTL 30s)
    - `owner:{aircraft_id}` — Sector ownership (TTL 15s)
    - `clearance:{aircraft_id}` — Clearance type (TTL 120s)
    - `runway:{aircraft_id}` — Assigned runway (TTL 120s)
    - `rwy_requested:{aircraft_id}` — Dedup guard (TTL 300s)
    - `rwyop:{aircraft_id}` — Operation type for runway queue
    - `runwayq:{airport_id}` — FIFO queue of waiting aircraft
    - `runwaylock:{runway_id}` — Distributed lock (TTL 30s)
    - `sim:reset` — Reset signal flag
    - `dedup:{event_id}` — Event deduplication
  - Redis utility functions: `get_redis()` with retries, `json_set()`/`json_get()` with automatic serialization, `acquire_lock()`/`release_lock()` for distributed locking, `enqueue()`/`dequeue()`/`queue_length()` for FIFO queues, `is_duplicate()` for deduplication

---

### Abdullah Arif

**Assigned:** Runway & Ground Control Service, real-time dashboard (Leaflet, WebSocket client), documentation.

**What was built:**

- **Runway & Ground Control Service** (`services/runway/`)
  - **Runway definitions** (`services/runway/app/domain/runway.py`): Full YYZ runway configuration including RWY_06L, RWY_06R, RWY_05, RWY_23, RWY_15L, RWY_15R, RWY_33R, RWY_33L with headings and active status
  - **Conflict groups**: Group A (parallel east-west: 05/23, 06L/24R, 06R/24L) and Group B (crossing north-south: 15L/33R, 15R/33L); runways in the same group can operate simultaneously, runways from different groups cannot
  - **Queue management**: Consumes `runway.request`, enqueues aircraft into Redis FIFO list (`runwayq:YYZ`), stores operation type (`rwyop:{aircraft_id}`)
  - **Allocation algorithm** (`services/runway/app/services/assign_runway.py`): Snapshots currently locked runways, iterates available runways checking for conflict-group violations, acquires distributed lock via Redis SETNX (TTL 30s), dequeues aircraft, and publishes `runway.assigned`
  - **Background processor** (`services/runway/app/workers/runway_processor.py`): Runs every 5 seconds, calls the allocation algorithm for each airport
  - **Consumer** (`services/runway/app/workers/runway_consumer.py`): Subscribes to `runway.request` and handles enqueueing

- **Real-Time Dashboard** (`services/gateway/app/static/index.html`)
  - Full single-page application built with Leaflet.js on a dark CartoDB basemap
  - **Map features**: Sector boundary overlays (cyan for Sector A, purple for Sector B), runway polylines (yellow) for all YYZ runways, YYZ airport marker, aircraft markers as SVG airplane icons that rotate based on heading, position trails (last 60 points per aircraft), animated red dashed conflict lines between conflicting aircraft (6s timeout)
  - **Sidebar** (380px, resizable): Aircraft cards sorted by conflict status then altitude, showing callsign, phase badge, altitude, speed, heading, coordinates, and vertical rate with arrow indicators; click-to-fly-to-aircraft on map
  - **Statistics bar**: Live counters for events, active aircraft, conflicts, and runway operations
  - **Event log**: Scrollable, newest-first (capped at 200), color-coded (green=position, red=conflict, yellow=runway, purple=handoff), filterable toggle to hide position events
  - **Dynamic features**: Auto-removal of stale aircraft (60s timeout), cyclic color assignment from a 24-color palette, resizable sidebar and log section, WebSocket auto-reconnect with status indicator (green=live, red=disconnected)
  - WebSocket connection to Gateway at `/ws` with 2-second retry on disconnect

- **Documentation**
  - Project flow documentation (`docs/project-flow.md`): Comprehensive write-up covering system purpose, architecture overview, step-by-step event flow, RabbitMQ concepts and justification, Redis vs RabbitMQ comparison, and running instructions
  - README with quick-start guide

---

### Abhinav Gupta

**Assigned:** Gateway Service (WebSocket server, consumer, reset API), Logging Service and PostgreSQL persistence, shared library (events, Redis/Postgres helpers, logging config).

**What was built:**

- **Gateway Service** (`services/gateway/`)
  - FastAPI application serving both HTTP and WebSocket endpoints
  - **WebSocket endpoint** (`services/gateway/app/api/ws.py`): Accepts connections on `/ws`, maintains a set of active client connections, broadcasts events to all connected clients as JSON, handles graceful disconnection
  - **Event consumer** (`services/gateway/app/workers/gateway_consumer.py`): Subscribes to three event types — `aircraft.position`, `conflict.alert`, and `runway.assigned` — and forwards each to all connected WebSocket clients
  - **Reset API** (`services/gateway/app/api/reset.py`): `POST /api/reset` endpoint that scans Redis for all simulation state keys (`pos:*`, `owner:*`, `clearance:*`, `runway:*`, `rwy_requested:*`, `rwyop:*`, `runwayq:*`, `runwaylock:*`, `dedup:*`), deletes them, sets the `sim:reset` flag for Radar, and returns the count of deleted keys
  - Serves the static dashboard page (`index.html`) for browser access at port 8005

- **Logging Service** (`services/logging/`)
  - Subscribes to `#` (wildcard) on the `atc.events` exchange via durable queue `logging.all_events`, capturing every event regardless of type
  - Consumer worker (`services/logging/app/workers/log_consumer.py`) that calls `insert_event_log()` for each event received
  - Provides the complete audit trail of the simulation — every position update, handoff, runway assignment, and conflict alert is persisted

- **PostgreSQL Persistence** (`shared/shared/postgres.py`, `infra/postgres/init.sql`)
  - Database schema design: `event_log` table with UUID primary key, unique `event_id` constraint (deduplication via ON CONFLICT DO NOTHING), columns for event_type, aircraft_id, source_service, timestamp, and JSONB payload
  - Indexes on event_type, aircraft_id, and timestamp for efficient querying
  - `flight_plans` table stub for future use
  - Async connection pooling via asyncpg (2-10 connections) with startup retry logic
  - `insert_event_log()` function used by the Logging service

- **Shared Library Contributions** (`shared/`)
  - `postgres.py` — `get_pool()` for async connection pooling with retries, `insert_event_log()` for dedup-safe event insertion
  - `logging_config.py` — Structured logging configuration using structlog, applied consistently across all services
  - Package definition (`pyproject.toml`) specifying dependencies: pydantic, aio-pika, redis, asyncpg, structlog
