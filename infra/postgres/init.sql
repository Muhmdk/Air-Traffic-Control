-- ATC Database Initialization
-- Executed automatically by Postgres container on first run

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- Event log: stores every event that flows through the system
CREATE TABLE IF NOT EXISTS event_log (
    id              TEXT PRIMARY KEY DEFAULT gen_random_uuid()::text,
    event_id        UUID UNIQUE NOT NULL,
    event_type      TEXT NOT NULL,
    aircraft_id     TEXT NOT NULL,
    source_service  TEXT NOT NULL,
    timestamp       TIMESTAMPTZ NOT NULL,
    payload         JSONB NOT NULL DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_event_log_type ON event_log (event_type);
CREATE INDEX IF NOT EXISTS idx_event_log_aircraft ON event_log (aircraft_id);
CREATE INDEX IF NOT EXISTS idx_event_log_timestamp ON event_log (timestamp);

-- Flight plans: stub table for future use
CREATE TABLE IF NOT EXISTS flight_plans (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aircraft_id         TEXT NOT NULL,
    origin              TEXT NOT NULL,
    destination         TEXT NOT NULL,
    planned_departure   TIMESTAMPTZ,
    planned_arrival     TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_flight_plans_aircraft ON flight_plans (aircraft_id);
