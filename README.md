# Air Traffic Control (ATC) Simulation

A distributed, event-driven air traffic control simulation for Toronto Pearson International Airport (YYZ). Built with Python microservices, RabbitMQ, Redis, and PostgreSQL, featuring a real-time Leaflet-based dashboard.

## Tech Stack

| Technology   | Usage                          |
| ------------ | ------------------------------ |
| Python 3     | All microservices              |
| FastAPI      | HTTP & WebSocket endpoints     |
| RabbitMQ     | Async event bus (AMQP)         |
| Redis        | Real-time state & dist. locks  |
| PostgreSQL   | Persistent event logging       |
| Leaflet.js   | Live map dashboard             |
| Docker       | Containerization & orchestration |

## Getting Started

### Prerequisites

- [Git](https://git-scm.com/)
- [Docker](https://www.docker.com/) and Docker Compose

### Setup

```bash
# Clone the repository
git clone https://github.com/Muhmdk/Air-Traffic-Control.git
cd Air-Traffic-Control

# Copy the environment file
cp .env.example .env

# Build and start all services
docker compose up --build
```

Wait ~30 seconds for all services to initialize and connect.

### Access

| Resource               | URL                                          |
| ---------------------- | -------------------------------------------- |
| ATC Dashboard          | http://localhost:8005                         |
| RabbitMQ Management UI | http://localhost:15672 (guest / guest)        |



### Stop

```bash
docker compose down

# To also remove database volumes:
docker compose down -v
```

## Repository Structure

```
├── docker-compose.yml          # Service orchestration
├── .env.example                # Environment variable template
├── infra/
│   └── postgres/
│       └── init.sql            # Database schema (auto-runs on first start)
├── shared/                     # Shared Python package used by all services
│   ├── pyproject.toml
│   └── shared/
│       ├── events.py           # Event model and routing key constants
│       ├── rabbitmq.py         # Publish/subscribe helpers
│       ├── redis_utils.py      # State, locking, queue, and dedup utilities
│       ├── postgres.py         # Connection pool and insert helpers
│       └── logging_config.py   # Structured logging setup
└── services/
    ├── radar/                  # Simulates aircraft movement, publishes positions
    ├── sector/                 # Manages airspace sectors, ownership, and handoffs
    ├── runway/                 # Queues and allocates runways with distributed locks
    ├── conflict/               # Detects separation violations between aircraft
    ├── gateway/                # WebSocket bridge and Leaflet dashboard
    └── logging/                # Persists all events to PostgreSQL
```

Each service follows the same internal layout:

```
app/
├── main.py        # FastAPI app with lifespan startup/shutdown
├── api/           # HTTP endpoints (health, REST)
├── domain/        # Models, rules, business entities
├── services/      # Business logic and use-case handlers
└── workers/       # Message consumers and background tasks
```

## Services

| Service      | Port | Description                                    |
| ------------ | ---- | ---------------------------------------------- |
| Radar        | 8001 | Aircraft simulation, publishes positions every 2s |
| Sector A     | 8002 | Airspace management for sector A               |
| Sector B     | 8012 | Airspace management for sector B               |
| Runway       | 8003 | Runway queue management and allocation         |
| Conflict     | 8004 | Separation violation detection                 |
| Gateway      | 8005 | WebSocket gateway and live dashboard           |
| Logging      | 8006 | Event persistence to PostgreSQL                |

## Environment Variables

| Variable         | Default                                            |
| ---------------- | -------------------------------------------------- |
| `AMQP_URL`       | `amqp://guest:guest@rabbitmq:5672/`                |
| `REDIS_URL`      | `redis://redis:6379/0`                             |
| `POSTGRES_DSN`   | `postgresql://atc:atc_secret@postgres:5432/atc_db` |
| `RADAR_INTERVAL` | `2`                                                |
| `LOG_LEVEL`      | `INFO`                                             |
