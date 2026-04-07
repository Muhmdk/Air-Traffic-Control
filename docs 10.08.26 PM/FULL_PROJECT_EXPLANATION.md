# Air Traffic Control Simulation — Full Project Explanation

## 1. Abstract-Level Summary

This project is a distributed, event-driven air traffic control (ATC) simulation modeled around Toronto Pearson International Airport (YYZ). It demonstrates how modern distributed systems handle real-time, safety-critical coordination problems by simulating aircraft departures, arrivals, sector handoffs, runway allocation, and conflict detection using a microservices architecture. The system comprises 7 application services and 3 infrastructure services, all containerized and orchestrated via Docker Compose. Two aircraft — a WestJet departure (WJA512) and an Air Canada arrival (ACA845) — are simulated through their complete flight lifecycles. Services communicate exclusively through asynchronous messaging (RabbitMQ), share real-time state via Redis, persist a complete audit trail to PostgreSQL, and stream live updates to a browser-based Leaflet.js dashboard over WebSockets. The project applies core distributed systems concepts including event-driven architecture, distributed locking, state machines, two-phase commit protocols, deduplication, and closed-loop feedback control.

---

## 2. Introduction and Goals

### 2.1 Project Goals

The primary goal is to design and implement a distributed system that solves a real-world coordination problem — air traffic control — where:

- Multiple independent systems must communicate reliably and in real time
- Shared resources (runways, airspace sectors) require strict coordination to prevent conflicts
- Events must be processed asynchronously without tight coupling between services
- Every action must be auditable with a full event log

The secondary goals include:

- Demonstrating practical application of distributed systems patterns (pub/sub messaging, distributed locking, state machines, consensus protocols)
- Building a visually observable system where distributed interactions can be watched in real time
- Implementing a production-grade microservices architecture with proper containerization, health checks, retry logic, and structured logging

### 2.2 Relationship to Course (COE892 — Distributed Cloud Computing)

This project directly applies concepts from the COE892 course at Toronto Metropolitan University:

| Course Concept | Implementation in Project |
|---|---|
| Asynchronous Messaging | RabbitMQ topic exchange for all inter-service communication |
| Distributed State Management | Redis as shared real-time state store across all services |
| Distributed Locking | Redis SETNX with TTL for runway allocation and ownership |
| Event-Driven Architecture | Every service publishes/consumes events; no direct HTTP calls between services |
| Microservices | 7 independently deployable services, each with a single responsibility |
| Containerization & Orchestration | Docker Compose managing 10 containers with health checks and dependency ordering |
| Fault Tolerance | Retry logic, TTL-based lock expiry, deduplication, durable message queues |
| Data Persistence | PostgreSQL event log with deduplication for complete audit trail |
| Real-Time Streaming | WebSocket bridge from backend to browser dashboard |
| Consensus / Coordination | Two-phase handoff protocol preventing race conditions during sector transitions |

---

## 3. System Design

### 3.1 High-Level Architecture

The system follows an event-driven microservices architecture. All application services are fully decoupled — they never call each other directly. Instead, they communicate exclusively through a RabbitMQ topic exchange named `atc.events`. Redis serves as the shared state layer, and PostgreSQL provides persistent storage.

**Architecture Diagram Description:**

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Docker Compose Network                       │
│                                                                     │
│  ┌──────────┐   ┌──────────┐   ┌──────────┐                       │
│  │ RabbitMQ │   │  Redis   │   │ Postgres │                       │
│  │  :5672   │   │  :6379   │   │  :5432   │                       │
│  └────┬─────┘   └────┬─────┘   └────┬─────┘                       │
│       │              │              │                               │
│  ─────┼──────────────┼──────────────┼────────── Event Bus ───────  │
│       │              │              │                               │
│  ┌────┴────┐  ┌──────┴──────┐  ┌───┴─────┐  ┌──────────┐         │
│  │  Radar  │  │ Sector A/B  │  │ Runway  │  │ Conflict │         │
│  │  :8001  │  │ :8002/:8012 │  │  :8003  │  │  :8004   │         │
│  └─────────┘  └─────────────┘  └─────────┘  └──────────┘         │
│                                                                     │
│  ┌──────────┐  ┌──────────┐                                        │
│  │ Gateway  │  │ Logging  │                                        │
│  │  :8005   │  │  :8006   │                                        │
│  └────┬─────┘  └──────────┘                                        │
│       │ WebSocket                                                   │
│  ┌────┴─────────────┐                                              │
│  │ Browser Dashboard│                                              │
│  │  (Leaflet.js)    │                                              │
│  └──────────────────┘                                              │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Infrastructure Services

**RabbitMQ (Message Broker)** — Port 5672 (AMQP), 15672 (Management UI)
- Uses a single durable topic exchange: `atc.events`
- Messages are routed using dot-separated routing keys (e.g., `aircraft.position`, `runway.assigned`)
- Each consuming service creates its own durable queue bound to specific routing key patterns
- Provides guaranteed delivery, backpressure handling, and message durability across broker restarts
- Chosen over Redis Pub/Sub (lacks durability), Kafka (overkill for this throughput), and direct HTTP (creates tight coupling)

**Redis (State Store)** — Port 6379 (mapped to 6380 on host)
- Serves as the real-time shared state layer that multiple services read and write
- Stores aircraft positions, sector ownership, clearances, runway locks, queues, and deduplication guards
- Provides distributed locking via SETNX (Set if Not Exists) with TTL-based auto-expiry
- All keys use TTLs to prevent stale state if a service crashes

**PostgreSQL (Persistent Storage)** — Port 5432
- Stores the complete event audit trail in the `event_log` table
- Uses JSONB for flexible event payload storage
- Deduplication via UNIQUE constraint on `event_id` with ON CONFLICT DO NOTHING
- Indexed by event_type, aircraft_id, and timestamp for efficient querying

### 3.3 Why Both RabbitMQ and Redis?

They serve fundamentally different roles:

- **RabbitMQ** handles **event flow** — asynchronous communication between services. It answers "what happened?" and ensures every interested service gets notified.
- **Redis** handles **current state** — shared, real-time data that multiple services need to read/write. It answers "what is true right now?" (who owns this aircraft, is this runway locked, has this aircraft been cleared).

Redis Pub/Sub could deliver messages but cannot guarantee delivery if a consumer is down. RabbitMQ could store state in messages but cannot provide fast key-value lookups or distributed locks. Both are necessary.

### 3.4 Event Schema

All inter-service communication uses a standard event envelope (the `ATCEvent` Pydantic model):

```json
{
  "event_id": "uuid-v4",
  "timestamp": "ISO-8601",
  "type": "aircraft.position",
  "aircraft_id": "WJA512",
  "source_service": "radar",
  "data": { ... }
}
```

Six event types define the entire communication vocabulary:

| Routing Key | Publisher | Consumers | Purpose |
|---|---|---|---|
| `aircraft.position` | Radar | Sector A/B, Conflict, Gateway, Logging | Aircraft position broadcast |
| `aircraft.handoff.request` | Sector (source) | Sector (target), Logging | Initiate sector transfer |
| `aircraft.handoff.accepted` | Sector (target) | Sector (source), Logging | Confirm sector transfer |
| `runway.request` | Sector | Runway, Logging | Request runway allocation |
| `runway.assigned` | Runway | Sector A/B, Gateway, Logging | Runway allocated to aircraft |
| `conflict.alert` | Conflict | Gateway, Logging | Separation violation detected |

### 3.5 Redis Key Schema

| Key Pattern | Type | TTL | Purpose |
|---|---|---|---|
| `pos:{aircraft_id}` | JSON | 30s | Current position (lat, lon, altitude, heading, speed, phase) |
| `owner:{aircraft_id}` | String | 15s | Sector ID that currently owns this aircraft |
| `clearance:{aircraft_id}` | String | 120s | Clearance type: "takeoff" or "landing" |
| `runway:{aircraft_id}` | String | 120s | Assigned runway ID (e.g., "RWY_06L") |
| `rwy_requested:{aircraft_id}` | String | 300s | Deduplication guard: prevents duplicate runway requests |
| `rwyop:{aircraft_id}` | String | 300s | Operation type stored during enqueue |
| `runwayq:{airport_id}` | List | none | FIFO queue of aircraft waiting for runway |
| `runwaylock:{runway_id}` | String | 30s | Distributed lock: runway is in use |
| `dedup:{event_id}` | String | 300s | Event deduplication guard |
| `sim:reset` | String | 10s | Signal flag for simulation reset |

### 3.6 Database Schema

```sql
-- Complete event audit trail
CREATE TABLE event_log (
    id          TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    event_id    UUID UNIQUE NOT NULL,
    event_type  TEXT NOT NULL,
    aircraft_id TEXT NOT NULL,
    source_service TEXT NOT NULL,
    timestamp   TIMESTAMPTZ NOT NULL,
    payload     JSONB NOT NULL
);

-- Indexes for efficient querying
CREATE INDEX idx_event_type ON event_log(event_type);
CREATE INDEX idx_aircraft   ON event_log(aircraft_id);
CREATE INDEX idx_timestamp  ON event_log(timestamp);

-- Stub for future use
CREATE TABLE flight_plans (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aircraft_id       TEXT NOT NULL,
    origin            TEXT,
    destination       TEXT,
    planned_departure TIMESTAMPTZ,
    planned_arrival   TIMESTAMPTZ,
    created_at        TIMESTAMPTZ DEFAULT now()
);
```

---

## 4. Implementation — Detailed Module Descriptions

### 4.1 Shared Library (`shared/`)

A common Python package installed by all services, providing reusable infrastructure code.

#### 4.1.1 Events Module (`shared/shared/events.py`)

Defines the `ATCEvent` Pydantic model — the standard envelope for all events. Fields include `event_id` (auto-generated UUID), `timestamp` (auto-generated ISO-8601), `type` (routing key), `aircraft_id`, `source_service`, and `data` (dictionary payload). Also defines six routing key constants (`AIRCRAFT_POSITION`, `HANDOFF_REQUEST`, `HANDOFF_ACCEPTED`, `RUNWAY_REQUEST`, `RUNWAY_ASSIGNED`, `CONFLICT_ALERT`) and the exchange name `atc.events`.

#### 4.1.2 RabbitMQ Module (`shared/shared/rabbitmq.py`)

Provides connection, publishing, and subscription helpers:

- `get_connection(amqp_url)` — Connects to RabbitMQ with 10 retries at 3-second intervals using aio-pika's robust connection
- `get_exchange(channel)` — Declares or reuses the durable topic exchange `atc.events`
- `publish(exchange, event)` — Serializes an ATCEvent to JSON and publishes with the event type as the routing key
- `subscribe(channel, exchange, queue_name, routing_key, callback)` — Creates a durable queue, binds it to the exchange with the given routing key pattern, and invokes the callback with parsed ATCEvent objects. Uses auto-acknowledgment via the `msg.process()` context manager.

#### 4.1.3 Redis Utilities Module (`shared/shared/redis_utils.py`)

Provides all Redis operations used across the system:

- `get_redis(redis_url)` — Connection with 10-retry logic
- `json_set(r, key, value, ttl)` / `json_get(r, key)` — JSON serialization/deserialization for storing complex state
- `acquire_lock(r, key, ttl)` / `release_lock(r, key)` — Distributed locking via Redis SETNX with TTL. Returns True if the lock was acquired, False if already held. TTL prevents deadlocks if a service crashes.
- `enqueue(r, key, value)` / `dequeue(r, key)` / `queue_length(r, key)` — FIFO queue operations using Redis lists (RPUSH/LPOP)
- `is_duplicate(r, event_id, ttl)` — Deduplication via SETNX on `dedup:{event_id}` key

#### 4.1.4 PostgreSQL Module (`shared/shared/postgres.py`)

- `get_pool(dsn)` — Creates an asyncpg connection pool (2-10 connections) with 10-retry startup logic
- `insert_event_log(pool, ...)` — Inserts into the event_log table. Converts ISO-8601 timestamp strings to TIMESTAMPTZ. Uses `ON CONFLICT (event_id) DO NOTHING` for deduplication.

#### 4.1.5 Logging Configuration (`shared/shared/logging_config.py`)

- `setup_logging(service_name)` — Configures structlog with JSON rendering, timestamp formatting, log level from environment, and stack trace processing
- `new_correlation_id()` — Generates UUID for request tracing across services

---

### 4.2 Radar Service (`services/radar/`, Port 8001)

**Purpose:** The simulation engine. Simulates aircraft movement through predefined waypoint paths and broadcasts position updates every 2 seconds.

#### 4.2.1 Aircraft Models (`app/domain/aircraft.py`)

Defines the `SimAircraft` model with fields: `aircraft_id`, `callsign`, `phase`, `intent` (departing/arriving), `lat`, `lon`, `altitude`, `heading`, `speed`, and `phase_tick` (elapsed ticks in current phase).

**Flight Phases (8 total):**
- Departing: `TAXI` → `TAKEOFF_ROLL` → `CLIMBING` → `DEPARTED`
- Arriving: `HOLDING` → `APPROACH` → `FINAL` → `LANDED`

**Waypoint Paths:** Predefined for each runway. Each waypoint contains (latitude, longitude, altitude_ft, speed_kts, ticks_to_next). The system linearly interpolates positions within segments.
- RWY_06L path: Used for takeoff (WJA512)
- RWY_06R path: Used for approach (ACA845)
- Fallback default paths if runway-specific paths are unavailable

**Holding Pattern:** Elliptical racetrack centered at (43.72, -79.48). Semi-major axis: 0.015 degrees latitude, 0.025 degrees longitude (elongated east-west). Angular speed: 0.15 radians/tick (~42 ticks per full loop). Constant altitude 5000 ft, speed 220 kts. Uses parametric equations: `lat = center_lat + a * sin(angle)`, `lon = center_lon + b * cos(angle)`.

**Two Simulated Aircraft:**
- WJA512 (WestJet 512): Starts at taxi position near RWY_06L threshold, intent=departing
- ACA845 (Air Canada 845): Starts in holding pattern, intent=arriving

#### 4.2.2 State Machine — Position Updater (`app/services/position_updater.py`)

The `tick(aircraft, has_clearance, runway_id)` function is the core simulation logic. For each tick (every 2 seconds):

1. Reads clearance status from Redis: `clearance:{aircraft_id}` and `runway:{aircraft_id}`
2. Based on current phase and clearance status, either advances phase or continues current movement:
   - **TAXI**: Aircraft waits. When clearance received → transition to TAKEOFF_ROLL
   - **TAKEOFF_ROLL**: Follows takeoff waypoint path. At path end → transition to CLIMBING
   - **CLIMBING**: Follows climbing waypoints. At altitude threshold → transition to DEPARTED
   - **DEPARTED**: Terminal state. Aircraft removed from simulation.
   - **HOLDING**: Aircraft flies elliptical racetrack pattern. When clearance received → transition to APPROACH
   - **APPROACH**: Follows approach waypoint path using assigned runway. At path end → transition to FINAL
   - **FINAL**: Short final approach. At touchdown → transition to LANDED
   - **LANDED**: Terminal state. Aircraft removed from simulation.
3. Interpolates position along the current waypoint segment
4. Updates aircraft lat, lon, altitude, heading, and speed

#### 4.2.3 Position Broadcaster (`app/workers/position_broadcaster.py`)

The main simulation loop that runs as a background task:

1. Connects to RabbitMQ and Redis
2. Initializes both aircraft at their starting positions
3. Every `RADAR_INTERVAL` seconds (default 2):
   - Checks for `sim:reset` flag in Redis → if set, restores aircraft to initial state
   - For each active aircraft:
     - Reads clearance flags from Redis
     - Calls `tick()` to advance the state machine
     - Publishes `aircraft.position` event with all current data
   - Removes aircraft that have reached terminal states (DEPARTED, LANDED)

---

### 4.3 Sector Service (`services/sector/`, Ports 8002 and 8012)

**Purpose:** Manages airspace sectors, claims aircraft ownership, handles sector-to-sector handoffs, requests runways, and writes clearance flags.

A single codebase deployed as two instances using the `SECTOR_ID` environment variable (SECTOR_A or SECTOR_B).

#### 4.3.1 Sector Boundaries (`app/domain/sector.py`)

```
SECTOR_A: latitude [43.5, 43.8], longitude [-79.7, -79.45]   (western half)
SECTOR_B: latitude [43.5, 43.8], longitude [-79.45, -79.2]   (eastern half)
Boundary: longitude -79.45
```

Provides `is_inside(sector_id, lat, lon)` to check if a position falls within a sector's boundary, and `target_sector(sector_id)` to determine the handoff destination.

#### 4.3.2 Position Handling (`app/services/handle_position.py`)

When an `aircraft.position` event is consumed:

1. Store position in Redis: `pos:{aircraft_id}` as JSON (TTL 30s)
2. Check if aircraft is inside this sector's boundary
3. If inside and unclaimed: claim ownership via `owner:{aircraft_id}` = SECTOR_ID (TTL 15s)
4. If owned by this sector: renew ownership TTL, check if aircraft needs a runway
5. If aircraft has left the boundary: initiate handoff to the other sector

**Runway Request Detection:**
- Departing aircraft in TAXI phase → publish `runway.request` with operation="takeoff"
- Arriving aircraft in HOLDING phase → publish `runway.request` with operation="landing"
- Deduplication guard: `rwy_requested:{aircraft_id}` (TTL 300s) ensures only one request per aircraft

#### 4.3.3 Two-Phase Handoff Protocol (`app/services/handle_handoff.py`)

This is a critical distributed coordination mechanism that prevents race conditions:

**Phase 1 — Request:** When the owning sector detects an aircraft leaving its boundary:
- Publishes `aircraft.handoff.request` with `from_sector`, `to_sector`, and current coordinates

**Phase 2 — Acceptance:** When the target sector receives the handoff request:
- Claims ownership: writes `owner:{aircraft_id}` = new sector ID
- Publishes `aircraft.handoff.accepted`

**Phase 3 — Acknowledgment:** The source sector receives the acceptance and releases control (ownership already transferred via Redis).

Without this protocol, both sectors could simultaneously attempt to control an aircraft crossing the boundary, leading to conflicting commands.

#### 4.3.4 Clearance Handling (`app/services/handle_clearance.py`)

When a `runway.assigned` event is consumed:
- Writes `clearance:{aircraft_id}` = "takeoff" or "landing" (TTL 120s)
- Writes `runway:{aircraft_id}` = runway ID (TTL 120s)

These flags are read by the Radar service on the next tick to advance the aircraft's phase.

#### 4.3.5 Consumer Worker (`app/workers/sector_consumer.py`)

Subscribes to four routing keys:
- `aircraft.position` → position handling
- `aircraft.handoff.request` → handoff protocol (target side)
- `aircraft.handoff.accepted` → handoff protocol (source side)
- `runway.assigned` → clearance writing

---

### 4.4 Runway Service (`services/runway/`, Port 8003)

**Purpose:** Queues aircraft requesting runways and allocates available runways using conflict-group validation and distributed locking.

#### 4.4.1 Runway Configuration (`app/domain/runway.py`)

Full YYZ runway configuration:
- **Active runways:** RWY_06L, RWY_06R
- **All runways:** RWY_05, RWY_23, RWY_06L, RWY_24R, RWY_06R, RWY_24L, RWY_15L, RWY_33R, RWY_15R, RWY_33L

**Conflict Groups** (a key safety mechanism):
- **Group A** (parallel east-west, heading ~047°): 05/23, 06L/24R, 06R/24L
- **Group B** (crossing north-south, heading ~137°): 15L/33R, 15R/33L
- **Rule:** Runways in the same conflict group CAN operate simultaneously. Runways from different conflict groups CANNOT (because their paths cross).

This models the real-world constraint at YYZ where crossing runway operations create collision risks.

#### 4.4.2 Queue Management (`app/workers/runway_consumer.py`)

When a `runway.request` event is consumed:
1. Enqueue aircraft ID to Redis FIFO list: `runwayq:YYZ` (RPUSH)
2. Store operation type: `rwyop:{aircraft_id}` = "takeoff" or "landing" (TTL 300s)

#### 4.4.3 Allocation Algorithm (`app/services/assign_runway.py`)

The `try_assign()` function runs every 5 seconds via the background processor:

1. **Snapshot locked runways:** Scan all `runwaylock:{runway_id}` keys to determine which runways are currently in use
2. **Determine active conflict groups:** For each locked runway, record which conflict group it belongs to
3. **Iterate available runways** in priority order:
   a. Skip if runway is locked
   b. Skip if runway's conflict group differs from currently active group (prevents crossing operations)
   c. Attempt to acquire distributed lock: `runwaylock:{runway_id}` via Redis SETNX (TTL 30s)
   d. On success: dequeue next aircraft from `runwayq:YYZ` (LPOP), retrieve operation type from `rwyop:{aircraft_id}`, publish `runway.assigned` event
4. Repeat for each queued aircraft until queue is empty or no more runways available

The TTL on runway locks (30s) is critical: if an aircraft completes its takeoff/landing (or a service crashes), the lock auto-expires and the runway becomes available again.

#### 4.4.4 Background Processor (`app/workers/runway_processor.py`)

An asyncio background task that calls `try_assign()` every 5 seconds. Runs continuously from service startup.

---

### 4.5 Conflict Detection Service (`services/conflict/`, Port 8004)

**Purpose:** Monitors all aircraft positions and detects when separation minimums are violated between any pair of aircraft.

#### 4.5.1 Separation Rules (`app/domain/rules.py`)

- **Minimum horizontal separation:** 0.05 degrees (~5.5 km)
- **Minimum vertical separation:** 1000 feet
- **Conflict condition:** BOTH horizontal AND vertical minimums must be violated simultaneously

Distance calculation uses `haversine_approx()` — a simplified Euclidean distance in degrees:
```python
sqrt((lat1 - lat2)² + (lon1 - lon2)²)
```
This approximation is sufficient for the simulation's geographic scale (Toronto area).

#### 4.5.2 Detection Logic (`app/services/detect_conflicts.py`)

Maintains an in-memory set of tracked aircraft IDs. On each `aircraft.position` event:

1. Add the aircraft_id to the tracked set
2. For every OTHER tracked aircraft:
   - Fetch its last known position from Redis (`pos:{other_id}`)
   - Calculate horizontal distance (degrees)
   - Calculate vertical distance (feet)
   - If horizontal < 0.05° AND vertical < 1000 ft: publish `conflict.alert`

The conflict alert event contains both aircraft IDs, their coordinates, and is forwarded to the dashboard for visualization.

---

### 4.6 Gateway Service (`services/gateway/`, Port 8005)

**Purpose:** Bridges the backend event system to the browser via WebSocket, serves the dashboard, and provides the simulation reset API.

#### 4.6.1 WebSocket Endpoint (`app/api/ws.py`)

- Accepts WebSocket connections on `/ws`
- Maintains a set of all active client connections
- `broadcast(event)` sends JSON-serialized events to all connected clients
- Handles graceful disconnection cleanup

#### 4.6.2 Event Consumer (`app/workers/gateway_consumer.py`)

Subscribes to three event types:
- `aircraft.position` — Aircraft position updates
- `conflict.alert` — Separation violations
- `runway.assigned` — Runway allocations

Each received event is immediately broadcast to all WebSocket clients.

#### 4.6.3 Reset API (`app/api/reset.py`)

`POST /api/reset` endpoint:
1. Scans Redis for all simulation state keys using patterns: `pos:*`, `owner:*`, `clearance:*`, `runway:*`, `rwy_requested:*`, `rwyop:*`, `runwayq:*`, `runwaylock:*`, `dedup:*`
2. Deletes all found keys
3. Sets `sim:reset` flag (TTL 10s) — Radar checks this flag and restores aircraft to initial positions
4. Returns JSON with count of deleted keys

#### 4.6.4 Real-Time Dashboard (`app/static/index.html`)

A single-page application built with Leaflet.js 1.9.4 on a dark CartoDB basemap. This is the visual interface for observing the entire simulation.

**Map Layer:**
- Sector boundary overlays: Cyan polygon for Sector A, Purple polygon for Sector B
- 5 runway polylines with yellow styling and labels
- YYZ airport marker at center
- Aircraft markers: Custom SVG airplane icons, color-coded per aircraft, rotatable by heading
- Position trails: Polylines showing the last 60 positions per aircraft
- Animated conflict lines: Red dashed lines between conflicting aircraft with 6-second timeout

**Sidebar (380px, resizable):**
- Header: "YYZ TERMINAL CONTROL"
- WebSocket status indicator (green dot = connected, red = disconnected)
- Reset button with spinning animation during reset
- Statistics bar: 4-column grid showing Events count, Active Aircraft, Conflicts, and Runway Operations
- Aircraft cards: Sorted by conflict status (conflicting first) then by altitude. Each card shows:
  - Callsign and flight phase badge (color-coded by phase)
  - Altitude (ft), speed (kts), heading (degrees)
  - Latitude/longitude coordinates
  - Vertical rate with up/down arrow indicators
  - Click-to-fly-to functionality (map centers on aircraft)
- Color palette: 24 cycling colors assigned to aircraft

**Event Log (scrollable, resizable):**
- Newest-first ordering, capped at 200 entries
- Color-coded entries: Green = position, Red = conflict, Yellow = runway, Purple = handoff
- Toggle button to hide position events (reduces noise)
- Each entry shows: timestamp (HH:MM:SS), event type, relevant data

**JavaScript Event Handling:**
- Position events: Update marker position, rotate icon, extend trail polyline, update aircraft card
- Conflict events: Mark conflicting aircraft, draw red dashed line between them (auto-removes after 6s)
- Runway events: Increment runway operations counter
- Stale aircraft detection: Removes aircraft not updated for 60 seconds
- Terminal states: Removes aircraft from map when LANDED or DEPARTED
- WebSocket auto-reconnection with 2-second retry interval

---

### 4.7 Logging Service (`services/logging/`, Port 8006)

**Purpose:** Captures every event in the system and persists it to PostgreSQL, providing a complete audit trail.

#### 4.7.1 Event Consumer (`app/workers/log_consumer.py`)

- Subscribes to `#` (wildcard) on the `atc.events` exchange
- Uses durable queue `logging.all_events`
- This means it captures EVERY event type — position updates, handoffs, runway assignments, and conflict alerts

For each event received:
1. Calls `insert_event_log()` from the shared PostgreSQL module
2. Inserts event_id, event_type, aircraft_id, source_service, timestamp, and full payload as JSONB
3. Deduplication: `ON CONFLICT (event_id) DO NOTHING` prevents double-insertion if a message is redelivered

---

## 5. End-to-End Simulation Flow

The complete lifecycle of how events flow through the system:

### Step 1: Radar Broadcasts Positions (Every 2 seconds)
The Radar service advances each aircraft's state machine by calling `tick()`, interpolating positions along waypoint paths, and publishing `aircraft.position` events containing latitude, longitude, altitude, speed, heading, phase, and intent.

### Step 2: Sectors Claim Ownership
Both Sector A and Sector B consume position events. Each checks if the aircraft falls within its geographic boundary. The first sector to detect the aircraft claims ownership by writing `owner:{aircraft_id}` to Redis.

### Step 3: Sector Handoff (Two-Phase Protocol)
When an aircraft crosses longitude -79.45 (the sector boundary):
1. Source sector publishes `aircraft.handoff.request`
2. Target sector claims ownership and publishes `aircraft.handoff.accepted`
3. Source sector releases control

### Step 4: Runway Request
When the owning sector detects an aircraft needing a runway (departing in TAXI or arriving in HOLDING), it publishes `runway.request`. A deduplication guard prevents duplicate requests.

### Step 5: Runway Allocation
The Runway service enqueues the aircraft. Every 5 seconds, the background processor checks available runways, validates conflict-group constraints, acquires a distributed lock, and publishes `runway.assigned`.

### Step 6: Clearance Feedback Loop
The owning sector receives the runway assignment and writes clearance flags to Redis. On the next tick, Radar reads these flags and transitions the aircraft to the next phase (TAXI → TAKEOFF_ROLL or HOLDING → APPROACH). This closed-loop feedback drives the simulation forward.

### Step 7: Conflict Detection
The Conflict service compares every position update against all other tracked aircraft. If both horizontal and vertical separation minimums are violated, it publishes `conflict.alert`.

### Step 8: Real-Time Dashboard
The Gateway service forwards position, conflict, and runway events to all connected browser clients over WebSocket. The Leaflet dashboard updates aircraft markers, trails, conflict lines, statistics, and event logs in real time.

### Step 9: Event Persistence
The Logging service captures every event via wildcard subscription and inserts it into PostgreSQL, creating a complete, queryable audit trail.

---

## 6. Distributed Systems Patterns Applied

### 6.1 Event-Driven Architecture
All inter-service communication flows through the RabbitMQ topic exchange. Services are fully decoupled — adding a new consumer requires zero changes to existing services. The Radar publishes positions without knowing which services consume them.

### 6.2 Distributed Locking (Redis SETNX + TTL)
Used for runway allocation: `SETNX` (Set if Not Exists) atomically acquires a lock only if no other service holds it. The TTL ensures locks auto-expire even if the holding service crashes, preventing permanent deadlocks. Also used implicitly for sector ownership claims.

### 6.3 Two-Phase Commit / Handoff Protocol
The sector handoff follows a request-accept pattern analogous to two-phase commit. This prevents split-brain scenarios where both sectors simultaneously attempt to control an aircraft crossing the boundary.

### 6.4 State Machine
Aircraft progress through well-defined phases with gated transitions. Phase advancement requires specific conditions (clearance flags, path completion, altitude thresholds). This ensures orderly, predictable behavior even in a distributed environment.

### 6.5 Deduplication
Multiple layers of deduplication prevent duplicate processing:
- Redis `SETNX` keys for runway requests (`rwy_requested:{aircraft_id}`)
- Redis `SETNX` keys for event processing (`dedup:{event_id}`)
- PostgreSQL `ON CONFLICT DO NOTHING` for event log insertion

### 6.6 Closed-Loop Feedback Control
The simulation forms a feedback loop: Sector → Runway → Sector → Radar. The Sector requests a runway, the Runway service allocates it, the Sector writes clearance flags, and the Radar reads those flags to advance the aircraft. No single service controls the entire flow.

### 6.7 FIFO Queue Processing
The runway queue uses Redis lists (RPUSH/LPOP) to ensure first-come-first-served ordering for runway allocation. This models real-world ATC queuing.

### 6.8 TTL-Based Fault Tolerance
Every Redis key has a TTL. If a service crashes:
- Ownership expires (15s) → another sector can claim the aircraft
- Runway locks expire (30s) → runway becomes available again
- Clearance expires (120s) → prevents stale clearances from persisting
- Position data expires (30s) → stale position data is automatically cleaned

---

## 7. Containerization and Orchestration

### 7.1 Docker Compose Configuration

10 containers orchestrated via `docker-compose.yml`:

**Infrastructure (with health checks):**
- `rabbitmq:3-management` — Health: `rabbitmq-diagnostics -q ping`
- `redis:7-alpine` — Health: `redis-cli ping`
- `postgres:16-alpine` — Health: `pg_isready -U atc`

**Application (depend on infrastructure health):**
- All 7 app services use the same Dockerfile pattern: Python 3.11-slim base, install shared package, install service-specific requirements, run with uvicorn
- Environment variables propagated via YAML anchors for consistency
- Sector A and B use the same image with different `SECTOR_ID` values

### 7.2 Service Internal Structure

Every service follows a consistent layout:
```
app/
├── main.py        # FastAPI with lifespan context (connection setup/cleanup)
├── api/           # HTTP endpoints
├── domain/        # Models, rules, business entities
├── services/      # Business logic handlers
└── workers/       # Message consumers and background tasks
```

### 7.3 Startup Sequence

1. Docker Compose starts infrastructure services
2. Health checks verify RabbitMQ, Redis, and PostgreSQL are ready
3. Application services start and connect with retry logic (10 retries, 3s intervals)
4. Each service declares/binds its queues on the topic exchange
5. Radar begins broadcasting aircraft positions
6. Dashboard becomes available at http://localhost:8005

---

## 8. Results and Analysis

### 8.1 Simulation Behavior

The system successfully simulates:
- **WJA512 departure:** TAXI → (waits for clearance) → TAKEOFF_ROLL → CLIMBING → DEPARTED. Aircraft follows RWY_06L waypoint path, accelerates through takeoff, climbs to altitude, and exits the simulation.
- **ACA845 arrival:** HOLDING (elliptical pattern) → (waits for clearance) → APPROACH → FINAL → LANDED. Aircraft descends along RWY_06R approach path to touchdown.

### 8.2 Distributed Coordination Results

- **Sector handoffs** occur cleanly when aircraft cross longitude -79.45, with no race conditions observed due to the two-phase protocol
- **Runway allocation** correctly prevents conflict-group violations — crossing runways are never assigned simultaneously
- **Conflict detection** triggers alerts when aircraft separation minimums are violated, visible as red lines on the dashboard
- **Event persistence** provides a queryable audit trail of every event in the simulation

### 8.3 Performance Characteristics

| Metric | Value |
|---|---|
| Simulation tick interval | 2 seconds |
| Runway allocation interval | 5 seconds |
| WebSocket update latency | < 100ms |
| Dashboard event log capacity | 200 entries |
| Aircraft trail history | 60 points |
| RabbitMQ retry strategy | 10 attempts, 3s intervals |
| Redis/PostgreSQL retry strategy | 10 attempts, 3s intervals |

---

## 9. Conclusions and Contributions

### 9.1 What Was Achieved

This project successfully demonstrates that distributed systems can solve complex, real-time coordination problems. Specifically:

1. **Decoupled microservices** communicate reliably through asynchronous messaging without any direct service-to-service calls
2. **Distributed locking** prevents resource conflicts (runway double-allocation) in a concurrent environment
3. **The two-phase handoff protocol** eliminates race conditions during ownership transfers between sectors
4. **State machine design** ensures orderly progression through flight phases even across multiple distributed services
5. **Real-time visualization** makes distributed system behavior observable and debuggable
6. **Complete audit trail** satisfies the non-negotiable requirement for event logging in safety-critical systems
7. **TTL-based fault tolerance** ensures the system self-heals from service crashes without manual intervention

### 9.2 Team Contributions

| Member | Contribution |
|---|---|
| **Muhammad Khan** | Radar simulation engine (aircraft models, waypoint interpolation, state machine), Docker/Compose orchestration, RabbitMQ and shared event/messaging infrastructure |
| **Shaheer Hassan** | Sector control services (ownership, position handling), two-phase handoff protocol, conflict detection service, Redis schema design and shared state utilities |
| **Abdullah Arif** | Runway service (queue management, allocation algorithm, conflict groups), Leaflet.js real-time dashboard, project documentation |
| **Abhinav Gupta** | Gateway service (WebSocket server, event consumer, reset API), logging service, PostgreSQL persistence, shared library (postgres, logging config) |

---

## 10. Future Work

Possible extensions to improve and expand the system:

1. **Dynamic Aircraft Spawning** — Allow users to add new aircraft through the dashboard instead of the fixed two-aircraft scenario
2. **Weather Simulation** — Add a weather service that publishes weather events affecting runway availability, separation minimums, and approach procedures
3. **Multiple Airport Support** — Extend the system to simulate traffic between multiple airports with en-route sectors
4. **3D Visualization** — Replace Leaflet (2D) with CesiumJS or Three.js for a 3D airspace view
5. **Machine Learning Conflict Prediction** — Use historical event log data to predict potential conflicts before they occur
6. **Flight Plan Service** — Implement the stubbed `flight_plans` table to allow pre-planned routes and schedule management
7. **Horizontal Scaling** — Deploy multiple instances of each service using Kubernetes with load balancing for higher throughput
8. **ADSB Data Integration** — Incorporate real-world ADS-B data feeds to simulate alongside live aircraft
9. **Voice Communication Simulation** — Add text-to-speech for ATC instructions and pilot readbacks
10. **Failure Injection Testing** — Build a chaos engineering framework to test resilience by randomly killing services during simulation

---

## 11. Technology Justifications and References

### Why RabbitMQ over alternatives?

- **vs Redis Pub/Sub:** Redis Pub/Sub is fire-and-forget — if a consumer is down, messages are lost. RabbitMQ queues are durable, and messages persist until acknowledged.
- **vs Apache Kafka:** Kafka is designed for high-throughput stream processing with log-based storage. It would be overkill for this system's event volume and adds operational complexity.
- **vs Direct HTTP calls:** HTTP creates tight coupling and requires service discovery. Adding a new consumer would require modifying the producer.

### Why Redis for state?

- Sub-millisecond read/write latency for real-time position lookups
- Built-in distributed locking primitive (SETNX)
- TTL support for automatic state cleanup
- Atomic operations prevent race conditions

### Why PostgreSQL for persistence?

- JSONB support for flexible event payloads
- Strong indexing for efficient querying by event type, aircraft, and time
- ACID compliance for audit trail reliability
- Unique constraints for deduplication

### Libraries and Frameworks

| Library | Version | Purpose |
|---|---|---|
| FastAPI | Latest | Async HTTP framework with WebSocket support |
| aio-pika | Latest | Async RabbitMQ client (AMQP 0-9-1) |
| redis (aioredis) | Latest | Async Redis client |
| asyncpg | Latest | Async PostgreSQL driver with connection pooling |
| Pydantic | v2 | Data validation and serialization for event models |
| structlog | Latest | Structured JSON logging |
| uvicorn | Latest | ASGI server for FastAPI applications |
| Leaflet.js | 1.9.4 | Interactive map rendering |
| Docker | Latest | Container runtime |
| Docker Compose | Latest | Multi-container orchestration |
