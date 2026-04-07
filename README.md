# Air Traffic Control Simulation

A distributed air traffic control simulation for Toronto Pearson International Airport (YYZ). Built with Python microservices, RabbitMQ, Redis, PostgreSQL, and a real-time Leaflet.js dashboard.

## Prerequisites

You only need two things installed:

- [Git](https://git-scm.com/downloads)
- [Docker Desktop](https://www.docker.com/products/docker-desktop/)

Docker Desktop is available for Mac, Windows, and Linux. It includes Docker Compose which is required to run this project.

**Windows users:** Make sure to enable WSL 2 during the Docker Desktop installation when prompted.

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Muhmdk/Air-Traffic-Control.git
cd Air-Traffic-Control
```

### 2. Create the environment file

**Mac / Linux:**
```bash
cp .env.example .env
```

**Windows (Command Prompt):**
```cmd
copy .env.example .env
```

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

if there is no .env.example file make it and add the following inside the file:
# ── RabbitMQ ─────────────────────────────────────────
RABBITMQ_DEFAULT_USER=guest
RABBITMQ_DEFAULT_PASS=guest
AMQP_URL=amqp://guest:guest@rabbitmq:5672/

# ── Redis ────────────────────────────────────────────
REDIS_URL=redis://redis:6379/0

# ── PostgreSQL ───────────────────────────────────────
POSTGRES_USER=atc
POSTGRES_PASSWORD=atc_secret
POSTGRES_DB=atc_db
POSTGRES_DSN=postgresql://atc:atc_secret@postgres:5432/atc_db

# ── Service Config ───────────────────────────────────
# RADAR_MODE: "simulated" (4 fake aircraft) or "live" (real ADS-B from OpenSky)
RADAR_MODE=simulated
RADAR_INTERVAL=2
LOG_LEVEL=INFO


### 3. Build and start all services

```bash
docker compose up --build
```

This starts 10 containers (RabbitMQ, Redis, PostgreSQL, and 7 application services). Wait about 30 seconds for everything to initialize.

### 4. Open the dashboard

Go to [http://localhost:8005](http://localhost:8005) in your browser.

You should see a live map with aircraft markers moving in real time, sector boundaries, runway overlays, and an event log.

## Other Useful Links

| Resource | URL |
|---|---|
| RabbitMQ Management UI | [http://localhost:15672](http://localhost:15672) (username: `guest`, password: `guest`) |

## Reset the Simulation

To restart the aircraft from their initial positions, either click the Reset button on the dashboard or run:

```bash
curl -X POST http://localhost:8005/api/reset
```

**Windows (PowerShell):**
```powershell
Invoke-WebRequest -Method POST http://localhost:8005/api/reset
```

## Stop the Application

```bash
docker compose down
```

To also remove the database volume (full clean reset):

```bash
docker compose down -v
```

## Troubleshooting

| Problem | Fix |
|---|---|
| Port already in use | Stop any services running on ports 5672, 6379, 5432, 8001-8006, or 8012 |
| Services keep restarting | Wait a bit longer — services retry connections to infrastructure on startup |
| Dashboard not loading | Make sure all containers are running: `docker compose ps` |
| Docker command not found | Make sure Docker Desktop is running |
