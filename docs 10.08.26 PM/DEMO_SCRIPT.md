# ATC Simulation — Demo Script

**Course:** COE892 — Distributed Cloud Computing, W2026
**Group 21:** Muhammad Khan, Shaheer Hassan, Abdullah Arif, Abhinav Gupta

---

## Pre-Demo Setup

```bash
# Make sure everything is running before the demo starts
docker compose up --build

# Wait ~30 seconds for all 10 containers to initialize
# Verify all containers are healthy:
docker compose ps
```

Open these tabs in your browser ahead of time:
- **Dashboard:** http://localhost:8005
- **RabbitMQ Management UI:** http://localhost:15672 (guest / guest)

---

## PART 1 — Live Dashboard Demo (Abdullah)

> **Goal:** Show the audience the working system before diving into code. Let them see the "what" before the "how."

### 1.1 — Open the Dashboard

- Open http://localhost:8005
- Point out the overall layout:
  - **Map** (Leaflet.js on dark CartoDB tiles) with aircraft markers, sector overlays, and runway lines
  - **Sidebar** with aircraft cards, stats bar, and event log

### 1.2 — Aircraft in Motion

- Show **WJA512** (departing) — starts at the taxiway near RWY 06L, waiting for clearance
- Show **ACA845** (arriving) — flying an elliptical holding pattern in Sector A (west)
- Show **TSC903** (arriving) — flying a holding pattern in **Sector B** (east) — "this one is waiting for WJA512 to finish taking off before it can land on the same runway"
- Point out the **aircraft markers rotate** based on heading
- Point out the **trail lines** (white dots) showing where the aircraft has been
- Click an aircraft card in the sidebar — map flies to that aircraft's position

### 1.3 — Real-Time Event Flow

- Draw attention to the **event log** at the bottom of the sidebar
- Events are color-coded:
  - **Green** = position updates (every 2 seconds per aircraft)
  - **Yellow** = runway assignments
  - **Purple** = sector handoffs
  - **Red** = conflict alerts
- Toggle the "Hide Position" button to filter out the noise and show only significant events
- Point out the **stats bar**: Events count, Active Aircraft, Conflicts, Runway Ops

### 1.4 — Watch the Lifecycle Play Out

- Narrate as events happen:
  - "WJA512 just got assigned RWY 06L — you can see the yellow event in the log"
  - "Now it's transitioning from TAXI to TAKEOFF_ROLL — watch it start moving down the runway"
  - "ACA845 got cleared for approach on RWY 06R — it's leaving the holding pattern"
  - "Notice TSC903 is still holding in Sector B — both runways are locked right now"
  - "WJA512 has departed — its runway lock on 06L just expired"
  - "Now TSC903 gets assigned RWY 06L — the same runway WJA512 just took off from!"
  - "Watch TSC903 leave the holding pattern and fly west — it crosses the sector boundary..."
  - "There's the handoff! Sector B transferred control to Sector A — you can see the purple event"
  - "TSC903 is now on approach in Sector A, lining up for 06L, and... landed."
- If a **conflict alert** fires, point out the **red dashed line** between the two aircraft on the map

### 1.5 — Sector Boundaries & Runways

- Point out the **two sector overlays**: cyan (Sector A, west) and purple (Sector B, east)
- The boundary between them is at longitude -79.45
- Show the **yellow runway lines** — RWY 06L and 06R are the active ones
- "TSC903 starts in Sector B — when it gets cleared for approach, its flight path crosses into Sector A, and that's when the handoff protocol kicks in. We'll show you that in the code."

### 1.6 — Reset

- Click the **Reset** button in the sidebar header
- Everything clears — aircraft return to starting positions, event log resets, stats reset
- "This sends a POST to /api/reset, which clears all Redis state and signals the Radar to restart. We'll show you exactly how that works in the code."

### 1.7 — RabbitMQ Management UI (Quick Peek)

- Switch to http://localhost:15672
- Show the **Exchanges** tab — point out the single `atc.events` topic exchange
- Show the **Queues** tab — show the queues created by each service (sector, runway, conflict, gateway, logging)
- "Every service communicates through this one exchange using routing keys. No service talks to another directly."

---

## PART 2 — Code Walkthrough

> **Transition:** "Now that you've seen the system running, let's walk through the code. We'll follow the same flow as the simulation — starting from where data originates (the Radar), through the services that react to it, and ending where it gets displayed and stored."

---

### 2.1 — Shared Library (Muhammad + Abhinav)

> **Goal:** Before diving into services, show the common foundation everything is built on.

**Muhammad** covers the event model and RabbitMQ helpers:

- **`shared/shared/events.py:12`** — `ATCEvent` class
  - "This is the standard envelope for every message in the system. Every event has an auto-generated UUID, ISO timestamp, a type (which doubles as the RabbitMQ routing key), the aircraft ID, the source service name, and a data payload."
- **`shared/shared/events.py:26`** — `RoutingKeys` class
  - "These 6 constants are the entire vocabulary of the system. Every service publishes and subscribes using these keys."
- **`shared/shared/rabbitmq.py:22`** — `get_connection()`
  - "Connects to RabbitMQ with 10 retries at 3-second intervals. This is important because in Docker, RabbitMQ might not be ready when our services start."
- **`shared/shared/rabbitmq.py:47`** — `publish()`
  - "Takes an exchange and an ATCEvent, serializes it to JSON, and publishes using the event type as the routing key."
- **`shared/shared/rabbitmq.py:60`** — `subscribe()`
  - "Creates a durable queue, binds it to the exchange with a routing key pattern, and invokes a callback with parsed ATCEvent objects. Every service consumer uses this."

**Abhinav** covers the Redis, Postgres, and logging helpers:

- **`shared/shared/redis_utils.py:39`** — `json_set()` / **line 45** — `json_get()`
  - "These handle JSON serialization for storing complex state in Redis — positions, clearances, etc."
- **`shared/shared/redis_utils.py:53`** — `acquire_lock()` / **line 59** — `release_lock()`
  - "Distributed locking via Redis SETNX with TTL. If a lock holder crashes, the TTL auto-expires the lock so the system self-heals."
- **`shared/shared/redis_utils.py:66`** — `enqueue()` / **line 70** — `dequeue()`
  - "FIFO queue operations using Redis lists. The Runway service uses these for the runway request queue."
- **`shared/shared/redis_utils.py:81`** — `is_duplicate()`
  - "Deduplication using SETNX — returns True if the event was already seen. Prevents double-processing."
- **`shared/shared/postgres.py:18`** — `get_pool()`
  - "Async connection pool with 2-10 connections and retry logic on startup."
- **`shared/shared/postgres.py:35`** — `insert_event_log()`
  - "Inserts into the event_log table with ON CONFLICT DO NOTHING — so even if a message gets redelivered by RabbitMQ, we don't get duplicate rows."

---

### 2.2 — Radar Service (Muhammad)

> **Goal:** "The Radar is the heartbeat of the simulation. It generates aircraft positions every 2 seconds and publishes them for everyone else to react to."

- **`services/radar/app/domain/aircraft.py:25`** — `SimAircraft` class
  - "Each aircraft has a phase, an intent (departing or arriving), position data, and a tick counter for tracking progress along waypoint paths."

- **`services/radar/app/domain/aircraft.py:49`** — `TAKEOFF_PATHS`
  - "Predefined waypoint paths for takeoff. Each waypoint is a tuple of (lat, lon, altitude, speed, ticks_to_next). The Radar interpolates between these points for smooth movement."
- **`services/radar/app/domain/aircraft.py:65`** — `APPROACH_PATHS`
  - "Same idea but for landings — the aircraft descends along these waypoints to the runway."

- **`services/radar/app/domain/aircraft.py:97`** — Holding pattern constants
  - "The arrival aircraft flies an elliptical racetrack pattern. These constants define the center, semi-major/minor axes, and angular speed. The `holding_position()` function on **line 105** uses parametric equations to compute the position on the ellipse."

- **`services/radar/app/domain/aircraft.py:78`** — `APPROACH_PATHS["RWY_06L"]`
  - "This is the approach path for the third aircraft, TSC903. Notice it starts at longitude -79.36 (inside Sector B), then the waypoints move west through -79.48 (crossing into Sector A). That boundary crossing is what triggers the handoff mid-approach."

- **`services/radar/app/domain/aircraft.py:126`** — `HOLDING_CENTER_B`
  - "A second holding pattern centered at (43.70, -79.35) — well inside Sector B. TSC903 orbits here while waiting for RWY 06L to become available."

- **`services/radar/app/domain/aircraft.py:132`** — Initial aircraft definitions
  - "WJA512 starts on the taxiway near RWY 06L. ACA845 starts in the Sector A holding pattern. TSC903 starts in the Sector B holding pattern — it has a custom `holding_center` field so the simulation knows where to orbit it."

- **`services/radar/app/services/position_updater.py:18`** — `_interpolate_path()`
  - "This is the core interpolation logic. Given a waypoint path and the current tick count, it finds which segment the aircraft is on and linearly interpolates lat, lon, altitude, speed, and heading between waypoints."

- **`services/radar/app/services/position_updater.py:69`** — `tick()`
  - "This is the state machine. Every 2 seconds, the broadcaster calls tick() for each aircraft."
  - Walk through the key transitions:
    - **Line 77**: "TAXI phase — the aircraft just sits and waits. When the clearance flag shows up in Redis, **line 79** transitions it to TAKEOFF_ROLL."
    - **Line 83**: "TAKEOFF_ROLL — it follows the takeoff waypoint path. When altitude passes 100ft and enough ticks have elapsed, **line 89** transitions to CLIMBING."
    - **Line 107**: "HOLDING — the aircraft circles. When clearance arrives, **line 113** transitions to APPROACH using the assigned runway's path."
    - **Line 116**: "APPROACH to FINAL when altitude drops below 600ft. Then FINAL to LANDED at path end."

- **`services/radar/app/workers/position_broadcaster.py:47`** — Main loop
  - "This is the main simulation loop — `while True`, sleep for 2 seconds, then process each aircraft."
  - **Line 49**: "First thing every tick — check if `sim:reset` is set in Redis. If someone hit the reset button, we restore the aircraft to their initial positions."
  - **Line 61**: "Read the clearance and runway flags from Redis. These get written by the Sector service after a runway is assigned — that's the feedback loop."
  - **Line 88**: "Publish the position event. Every other service in the system reacts to this."

---

### 2.3 — Sector Services (Shaheer)

> **Transition:** "Now the Radar has published a position event. The Sector services are the first to react — they decide who owns each aircraft and coordinate handoffs."

- **`services/sector/app/domain/sector.py:17`** — `SECTORS` dict
  - "Two sectors split the airspace at longitude -79.45. Sector A is the western half, Sector B is the eastern half. Same code, different SECTOR_ID env var."
- **`services/sector/app/domain/sector.py:35`** — `is_inside()`
  - "Simple boundary check — is this lat/lon inside this sector's rectangle?"
- **`services/sector/app/domain/sector.py:42`** — `find_target_sector()`
  - "Given the current sector, returns the other one. Used during handoffs."

- **`services/sector/app/services/handle_position.py:22`** — `handle()`
  - "This is the main position handler. Every time an `aircraft.position` event arrives, this runs."
  - **Line 43**: "If the aircraft is inside our sector and unclaimed, we claim ownership by writing `owner:{aircraft_id}` to Redis with a 15-second TTL."
  - **Line 61**: "If the aircraft has LEFT our sector, we trigger a handoff — publish `aircraft.handoff.request` to the other sector."
  - **Line 79**: "If a departing aircraft is in TAXI phase, we publish `runway.request` with operation=takeoff."
  - **Line 90**: "If an arriving aircraft is in HOLDING phase, we publish `runway.request` with operation=landing."
  - "Both runway requests use a dedup key `rwy_requested:{aircraft_id}` so we don't flood the Runway service with duplicate requests."

- **`services/sector/app/services/handle_handoff.py:16`** — `handle_request()`
  - "This is the receiving side of the handoff. When Sector B gets a handoff request from Sector A, it claims ownership in Redis and publishes `aircraft.handoff.accepted`."
- **`services/sector/app/services/handle_handoff.py:49`** — `handle_accepted()`
  - "The original sector receives the acceptance and releases control. Ownership has already been transferred in Redis by the other sector."
  - "This two-phase protocol prevents a race condition where both sectors try to control the same aircraft at the boundary."

- **`services/sector/app/services/handle_clearance.py:14`** — `handle()`
  - **Line 31**: "When `runway.assigned` comes in, we write two Redis keys: `clearance:{aircraft_id}` and `runway:{aircraft_id}`. These are the flags that the Radar reads on the next tick to advance the aircraft's phase. This is the closed-loop feedback that drives the simulation forward."

- **`services/sector/app/workers/sector_consumer.py:36`** — Subscriptions
  - "The sector consumer subscribes to 4 routing keys — position, handoff request, handoff accepted, and runway assigned. Each one routes to a different handler."

---

### 2.4 — Conflict Detection (Shaheer)

> **Transition:** "While the sectors are managing ownership, the Conflict service is independently watching every position update looking for separation violations."

- **`services/conflict/app/domain/rules.py:8`** — Separation constants
  - "Minimum horizontal separation: 0.05 degrees (~5.5 km). Minimum vertical: 1000 feet. BOTH must be violated for a conflict — it's not enough to be close horizontally if there's plenty of vertical separation."
- **`services/conflict/app/domain/rules.py:12`** — `haversine_approx()`
  - "Simplified distance calculation using Euclidean approximation in degrees. Good enough for the Toronto area scale."

- **`services/conflict/app/services/detect_conflicts.py:23`** — `check()`
  - "Every time a position event arrives, this function runs."
  - **Line 32**: "It loops through every OTHER tracked aircraft, fetches their last known position from Redis, and compares distances."
  - **Line 51**: "If separation is violated, it publishes a `conflict.alert` with both aircraft's coordinates. That's what creates the red dashed line on the dashboard."

---

### 2.5 — Runway Service (Abdullah)

> **Transition:** "The Sector published a `runway.request`. Now the Runway service picks it up, queues the aircraft, and figures out which runway to assign."

- **`services/runway/app/domain/runway.py:15`** — `RUNWAYS`
  - "Full YYZ runway configuration. Only RWY_06L and RWY_06R are marked active for this simulation."
- **`services/runway/app/domain/runway.py:23`** — `CONFLICT_GROUPS`
  - "This is a key safety mechanism. Group A runways (the parallel east-west ones: 06L, 06R, 05, etc.) can operate simultaneously. Group B runways (the crossing north-south ones: 15L, 15R) CANNOT operate at the same time as Group A — their paths physically cross."
- **`services/runway/app/domain/runway.py:32`** — `conflicts_with_active()`
  - "Given a runway and the set of currently locked runways, returns True if assigning this runway would create a conflict-group violation."

- **`services/runway/app/workers/runway_consumer.py:22`** — `on_runway_request()`
  - **Line 29**: "Enqueues the aircraft into a Redis FIFO list (`runwayq:YYZ`) and stores its operation type (takeoff or landing)."

- **`services/runway/app/workers/runway_processor.py:19`** — `start_processor()`
  - **Line 24**: "Background loop that runs every 5 seconds. Calls the allocation algorithm for each airport."

- **`services/runway/app/services/assign_runway.py:30`** — `try_assign()`
  - "This is the allocation algorithm. Walk through it step by step:"
  - **Line 44**: "First, check conflict groups — skip any runway whose group conflicts with currently active runways."
  - **Line 51**: "Try to acquire a distributed lock on the runway via Redis SETNX with a 30-second TTL. If someone else already locked it, skip to the next runway."
  - **Line 65**: "On success — dequeue the next aircraft, publish `runway.assigned` with the runway ID and operation type."
  - "The 30-second TTL on the lock is important — it acts as the runway turnover time. After 30 seconds the lock auto-expires and the runway is available again, even if a service crashed."

---

### 2.6 — Gateway Service (Abhinav)

> **Transition:** "All these events are flowing through RabbitMQ. The Gateway service is the bridge that gets them to the browser."

- **`services/gateway/app/api/ws.py:15`** — `_clients` set
  - "We maintain a set of all active WebSocket connections. Every browser tab that opens the dashboard gets added here."
- **`services/gateway/app/api/ws.py:22`** — `broadcast()`
  - "Sends an event to every connected client. If a client has disconnected, we catch the exception and remove it from the set."
- **`services/gateway/app/api/ws.py:35`** — WebSocket endpoint
  - "Accepts the connection, adds it to the set, and keeps the connection alive. When the client disconnects, it gets removed."

- **`services/gateway/app/workers/gateway_consumer.py:21`** — Subscribe calls
  - "We subscribe to exactly 3 routing keys — `aircraft.position`, `conflict.alert`, and `runway.assigned`. Each event gets forwarded to all connected browsers."
  - **Line 18**: "The callback just calls broadcast() — every event goes straight to the dashboard."

- **`services/gateway/app/api/reset.py:13`** — Key patterns
  - "These are all the Redis key patterns we need to delete on reset: positions, ownership, clearances, runway state, dedup guards — everything."
- **`services/gateway/app/api/reset.py:26`** — Reset endpoint
  - "POST /api/reset — scans Redis for all these patterns, deletes them all."
  - **Line 39**: "Sets `sim:reset` with a 10-second TTL. The Radar checks for this flag every tick and restores the aircraft to their initial positions."

---

### 2.7 — Logging Service (Abhinav)

> **Transition:** "Every event we've talked about — positions, handoffs, runway assignments, conflict alerts — all of it gets permanently recorded."

- **`services/logging/app/workers/log_consumer.py:36`** — Wildcard subscription
  - "We subscribe to `#` — that's the RabbitMQ wildcard that matches EVERY routing key. This service captures every single event in the system."
- **`services/logging/app/workers/log_consumer.py:25`** — `insert_event_log()` call
  - "Each event gets inserted into PostgreSQL with its full payload as JSONB. The `ON CONFLICT DO NOTHING` on event_id means even if RabbitMQ redelivers a message, we don't get duplicates."
  - "This gives us a complete, queryable audit trail — you could run SQL queries to replay exactly what happened during the simulation."

---

### 2.8 — Docker Compose & Infrastructure (Muhammad)

> **Transition:** "Let's zoom out and look at how all 10 containers are wired together."

- **`docker-compose.yml`** — open the file
  - Point out the **3 infrastructure services** (RabbitMQ, Redis, PostgreSQL) with health checks
  - Point out the **x-common-env** YAML anchor that shares environment variables across all services
  - Show how **Sector A and Sector B** use the same image but different `SECTOR_ID` values
  - Show the **depends_on** with health check conditions — app services wait for infrastructure to be ready
  - Show the **PostgreSQL init volume** mounting `infra/postgres/init.sql` for automatic schema creation

- **`infra/postgres/init.sql`** — show the schema
  - `event_log` table with JSONB payload and unique event_id constraint
  - Indexes on event_type, aircraft_id, timestamp for efficient querying

---

## PART 3 — Wrap-Up

### 3.1 — Distributed Systems Patterns Summary

Quickly recap the key patterns demonstrated:

1. **Event-Driven Architecture** — all communication through RabbitMQ, zero direct service calls
2. **Distributed Locking** — Redis SETNX + TTL for runway allocation
3. **Two-Phase Handoff Protocol** — prevents race conditions during sector transitions
4. **State Machine** — aircraft phases gated by clearance flags
5. **Closed-Loop Feedback** — Sector -> Runway -> Sector -> Radar
6. **Deduplication** — at Redis level and PostgreSQL level
7. **TTL-Based Fault Tolerance** — all Redis keys expire, system self-heals

### 3.2 — Live Q&A

If asked "what happens if a service crashes?":
- Redis TTLs expire, ownership/locks release automatically
- RabbitMQ queues are durable — messages wait for the service to come back
- Reset button clears everything and restarts cleanly

If asked "how would you scale this?":
- Add more sector instances for more airspace coverage
- Kubernetes for horizontal scaling
- Kafka if event volume grows significantly

---

## Quick Reference — Who Presents What

| Section | Presenter | Duration (approx) |
|---|---|---|
| Part 1: Dashboard Demo | Abdullah | 3-4 min |
| 2.1: Shared Library | Muhammad (events, RabbitMQ) + Abhinav (Redis, Postgres) | 2-3 min |
| 2.2: Radar Service | Muhammad | 3-4 min |
| 2.3: Sector Services | Shaheer | 3-4 min |
| 2.4: Conflict Detection | Shaheer | 1-2 min |
| 2.5: Runway Service | Abdullah | 2-3 min |
| 2.6: Gateway Service | Abhinav | 2-3 min |
| 2.7: Logging Service | Abhinav | 1 min |
| 2.8: Docker/Infra | Muhammad | 1-2 min |
| Part 3: Wrap-Up | All | 2 min |
| **Total** | | **~20-25 min** |
