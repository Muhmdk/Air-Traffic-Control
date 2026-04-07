# Air Traffic Control (ATC) Simulation — Project Documentation

## Purpose

This project is a distributed, event-driven air traffic control simulation system modeled around Toronto Pearson International Airport (YYZ). It simulates real-world ATC operations — aircraft departures, arrivals, sector handoffs, runway allocation, and conflict detection — using a microservices architecture.

### Why Are We Building This?

The goal is to demonstrate how modern distributed systems handle real-time, safety-critical coordination problems. Air traffic control is a domain where:

- Multiple independent systems must communicate reliably and in real time.
- Shared resources (runways, airspace sectors) require strict coordination to prevent conflicts.
- Events must be processed asynchronously without tight coupling between services.
- Every action must be auditable — a full event log is non-negotiable.

By building this simulation, we explore and apply core distributed systems concepts: **asynchronous messaging**, **event-driven architecture**, **distributed locking**, **state machines**, and **real-time data streaming** — all within a tangible, visual domain that makes the interactions easy to observe and reason about.

---

## System Architecture Overview

The system is composed of **6 application services** and **3 infrastructure services**, all orchestrated via Docker Compose.

### Infrastructure

| Service      | Role                                      |
| ------------ | ----------------------------------------- |
| **RabbitMQ** | Message broker for inter-service events   |
| **Redis**    | Real-time shared state store and locking  |
| **PostgreSQL** | Persistent event log and audit trail    |

### Application Services

| Service        | Port | Responsibility                                              |
| -------------- | ---- | ----------------------------------------------------------- |
| **Radar**      | 8001 | Simulates aircraft movement, publishes position updates     |
| **Sector A**   | 8002 | Manages airspace sector A, handles ownership and handoffs   |
| **Sector B**   | 8012 | Manages airspace sector B, handles ownership and handoffs   |
| **Runway**     | 8003 | Queues runway requests and allocates runways                |
| **Conflict**   | 8004 | Detects separation violations between aircraft              |
| **Gateway**    | 8005 | WebSocket bridge to the browser dashboard                   |
| **Logging**    | 8006 | Persists every event to PostgreSQL                          |

---

## Project Workflow

The simulation runs two aircraft simultaneously:

- **WJA512 (WestJet 512)** — Departure: TAXI → TAKEOFF_ROLL → CLIMBING → DEPARTED
- **ACA845 (Air Canada 845)** — Arrival: HOLDING → APPROACH → FINAL → LANDED

Here is the end-to-end flow of how these aircraft move through the system:

### Step 1 — Radar Broadcasts Positions

Every 2 seconds, the **Radar** service advances each aircraft's state machine (interpolating along predefined waypoints) and publishes an `aircraft.position` event containing latitude, longitude, altitude, speed, heading, flight phase, and intent. Every other service reacts to these position updates.

### Step 2 — Sectors Claim Ownership

**Sector A** and **Sector B** each consume position events and check if the aircraft falls within their geographic boundary. The first sector to detect the aircraft claims ownership by writing an `owner:{aircraft_id}` key to Redis. From that point on, only the owning sector manages that aircraft.

### Step 3 — Sector Handoff

When an aircraft crosses the boundary between sectors (longitude -79.45), the owning sector initiates a **two-phase handoff protocol**:

1. The source sector publishes `aircraft.handoff.request` identifying the target sector.
2. The target sector receives the request, claims ownership, and publishes `aircraft.handoff.accepted`.
3. The source sector acknowledges and releases control.

This prevents race conditions where both sectors might try to control the same aircraft.

### Step 4 — Runway Request

When a sector detects that an aircraft needs a runway (a departing aircraft in TAXI phase or an arriving aircraft in HOLDING phase), it publishes a `runway.request` event. A deduplication guard in Redis (`rwy_requested:{aircraft_id}`) prevents duplicate requests.

### Step 5 — Runway Allocation

The **Runway** service enqueues the aircraft into a FIFO queue (`runwayq:YYZ`) in Redis. A background processor runs every 5 seconds and:

1. Checks which runways are available (not locked).
2. Verifies no conflict-group violations (e.g., crossing runways can't operate simultaneously).
3. Acquires a distributed lock (`runwaylock:{runway_id}`) via Redis `SETNX`.
4. Dequeues the next aircraft and publishes `runway.assigned`.

### Step 6 — Clearance Feedback Loop

When the owning sector receives `runway.assigned`, it writes clearance flags to Redis:

- `clearance:{aircraft_id}` = "takeoff" or "landing"
- `runway:{aircraft_id}` = the assigned runway ID

On the next tick, the **Radar** service reads these flags and transitions the aircraft to its next phase (e.g., TAXI → TAKEOFF_ROLL for departures, HOLDING → APPROACH for arrivals). This is the **closed-loop feedback** that drives the simulation forward.

### Step 7 — Conflict Detection

The **Conflict** service consumes every position update and compares it against all other tracked aircraft. If two aircraft violate separation minimums (horizontal distance < 0.05 degrees AND vertical separation < 1000 ft), it publishes a `conflict.alert` event.

### Step 8 — Real-Time Dashboard

The **Gateway** service consumes position, conflict, and runway events and pushes them over WebSocket to a browser-based dashboard built with Leaflet.js. The dashboard renders:

- Live aircraft markers with heading rotation
- Sector boundary overlays
- Runway positions
- Conflict lines (red dashed)
- A scrollable event log
- Statistics (event counts, active aircraft, conflicts, runway operations)

### Step 9 — Event Persistence

The **Logging** service subscribes to all events (using a wildcard `#` routing key) and inserts every event into the `event_log` table in PostgreSQL. This provides a complete audit trail of everything that happened during the simulation.

---

## What is RabbitMQ?

RabbitMQ is an open-source **message broker** — a middleman that receives messages from producers (services that send messages) and delivers them to consumers (services that receive messages). It implements the AMQP (Advanced Message Queuing Protocol) standard.

Think of it like a post office: services don't send messages directly to each other. Instead, they drop messages at the broker with an address (routing key), and the broker delivers them to any service that has expressed interest in that type of message.

### Key RabbitMQ Concepts Used in This Project

**Exchange**: A message router. We use a single **topic exchange** named `atc.events`. A topic exchange routes messages based on pattern matching against routing keys.

**Routing Key**: A dot-separated string attached to each message that describes what the message is about (e.g., `aircraft.position`, `runway.assigned`). Consumers bind to patterns — for example, `aircraft.*` would match both `aircraft.position` and `aircraft.handoff.request`.

**Queue**: A buffer where messages wait to be consumed. Each service creates its own durable queue and binds it to the exchange with the routing keys it cares about.

**Consumer**: A service (or function within a service) that reads messages from a queue and processes them.

**Producer**: A service that publishes messages to the exchange.

### How We Use RabbitMQ

All inter-service communication flows through the `atc.events` topic exchange. Here is a map of every event type, who publishes it, and who consumes it:

| Routing Key                   | Publisher       | Consumers                               |
| ----------------------------- | --------------- | --------------------------------------- |
| `aircraft.position`           | Radar           | Sector A/B, Conflict, Gateway, Logging  |
| `aircraft.handoff.request`    | Sector (source) | Sector (target), Logging                |
| `aircraft.handoff.accepted`   | Sector (target) | Sector (source), Logging                |
| `runway.request`              | Sector          | Runway, Logging                         |
| `runway.assigned`             | Runway          | Sector A/B, Gateway, Logging            |
| `conflict.alert`              | Conflict        | Gateway, Logging                        |

Every message follows a standard envelope format:

```json
{
  "event_id": "uuid",
  "timestamp": "ISO-8601",
  "type": "aircraft.position",
  "aircraft_id": "WJA512",
  "source_service": "radar",
  "data": { ... }
}
```

### Why RabbitMQ?

We chose RabbitMQ over alternatives (like Redis Pub/Sub, Kafka, or direct HTTP calls) for several reasons:

1. **Decoupling** — Services don't need to know about each other. The Radar service publishes positions without knowing or caring which services consume them. Adding a new consumer (e.g., a weather service) requires zero changes to existing services.

2. **Durability** — RabbitMQ queues are durable, meaning messages survive broker restarts. If the Logging service goes down temporarily, its messages queue up and get processed when it comes back. With Redis Pub/Sub, those messages would be lost.

3. **Topic Routing** — The topic exchange gives us flexible, pattern-based routing. The Logging service subscribes to `#` (everything), while the Conflict service only subscribes to `aircraft.position`. Each service gets exactly the events it needs without any filtering logic.

4. **Backpressure** — If a consumer falls behind, messages accumulate in its queue rather than being dropped or overwhelming the consumer. This is critical in a system where every event matters.

5. **Guaranteed Delivery** — With message acknowledgments, RabbitMQ ensures a message is only removed from the queue after the consumer confirms it has been processed. If a consumer crashes mid-processing, the message gets redelivered.

6. **Built for This Pattern** — RabbitMQ is purpose-built for the pub/sub and work-queue patterns we use. Kafka would be overkill for our throughput. Redis Pub/Sub lacks durability. HTTP calls would create tight coupling and require service discovery.

---

## Redis vs RabbitMQ — Why Both?

Redis and RabbitMQ serve fundamentally different roles in this system:

- **RabbitMQ** handles **event flow** — the asynchronous communication between services. It answers "what happened?" and ensures every interested service gets notified.
- **Redis** handles **current state** — the shared, real-time data that multiple services need to read and write. It answers "what is true right now?" (e.g., who owns this aircraft, is this runway locked, has this aircraft been cleared).

You cannot replace one with the other. Redis Pub/Sub could deliver messages but can't guarantee delivery if a consumer is down. RabbitMQ could store state in messages but can't provide fast key-value lookups or distributed locks.

---

## Running the System

```bash
# Start everything
docker compose up --build

# Access the dashboard
open http://localhost:8005

# Access RabbitMQ management UI
open http://localhost:15672    # guest:guest

# Reset the simulation
curl -X POST http://localhost:8005/api/reset

# Query the event log
docker compose exec postgres psql -U atc -d atc_db \
  -c "SELECT event_type, aircraft_id, timestamp FROM event_log ORDER BY timestamp DESC LIMIT 20;"
```
