# P-01 Core OS Architecture — Implemented Conditional Backend

This document describes the implemented P-01 backend in this repository. It is not the full AUTONOMUS product and not a Windows-certified desktop OS.

## Implemented modules

- `app/core`: settings, lifecycle, logging, exceptions, health, authentication, application factory.
- `app/database`: SQLAlchemy async engine, SQLite pragmas, Alembic migration, repositories.
- `app/tasks`: bounded priority queue, persistent task manager, safe internal handlers, retry scheduler.
- `app/events`: bounded asynchronous event bus, persisted system events, isolated subscribers.
- `app/permissions`: deterministic permission engine, permission definitions, approval service.
- `app/monitoring`: psutil resource snapshot, admission pressure checks, metrics, diagnostics.
- `app/api`: versioned FastAPI routes, bearer-session authentication, permission dependencies.

## Lifecycle

Startup: load settings → logging → migrations/database health → seed permissions/system principal → event bus → monitoring → task recovery/workers → ready. Shutdown: stop admission → signal running handlers → wait cleanup window → persist interrupted state → drain/stop event bus → dispose database.

Observed lifecycle events in the smoke run: `ApplicationStarted`, `ApplicationReady`, `ApplicationStopping`, `ApplicationStopped`.

## Explicitly not implemented

Frontend dashboard, Tauri shell, AI models, agent creation, browser/desktop automation, business execution, wallets/payments, Windows service installation, remote access, distributed workers.
