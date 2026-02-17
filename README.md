# litestar-sendparcel

[![PyPI](https://img.shields.io/pypi/v/litestar-sendparcel.svg)](https://pypi.org/project/litestar-sendparcel/)
[![Python Version](https://img.shields.io/pypi/pyversions/litestar-sendparcel.svg)](https://pypi.org/project/litestar-sendparcel/)
[![License](https://img.shields.io/pypi/l/litestar-sendparcel.svg)](https://github.com/python-sendparcel/litestar-sendparcel/blob/main/LICENSE)

Litestar framework adapter for [python-sendparcel](https://github.com/python-sendparcel/python-sendparcel)
— a pluggable shipping and parcel delivery library for Python.

> **Alpha (0.1.0)** — The API is functional but may change before 1.0.
> Use in production at your own discretion.

## Features

- **Router factory** — single `create_shipping_router()` call wires up all shipping endpoints
- **Shipment lifecycle** — create shipments, generate labels, fetch status updates
- **Provider webhooks** — callback endpoint with automatic retry and exponential backoff
- **Plugin registry** — auto-discovers `sendparcel` provider plugins at startup
- **SQLAlchemy contrib** — optional async SQLAlchemy 2.0 models and repository (install the `[sqlalchemy]` extra)
- **Protocol-driven** — `OrderResolver` and `CallbackRetryStore` protocols let you plug in your own logic
- **Structured error handling** — maps core `sendparcel` exceptions to proper HTTP status codes (400, 404, 409, 502)
- **Pydantic configuration** — `SendparcelConfig` reads from environment variables with `SENDPARCEL_` prefix

## Installation

```bash
pip install litestar-sendparcel
```

With the optional SQLAlchemy async persistence layer:

```bash
pip install litestar-sendparcel[sqlalchemy]
```

## Quick Start

A minimal Litestar application with `litestar-sendparcel`:

```python
from litestar import Litestar
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from litestar_sendparcel import SendparcelConfig, create_shipping_router
from litestar_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)

# 1. Configure
config = SendparcelConfig(default_provider="inpost")

# 2. Set up persistence
engine = create_async_engine("sqlite+aiosqlite:///shipments.db")
session_factory = async_sessionmaker(engine, expire_on_commit=False)
repository = SQLAlchemyShipmentRepository(session_factory)

# 3. Create the shipping router
shipping_router = create_shipping_router(
    config=config,
    repository=repository,
)

# 4. Mount in your Litestar app
app = Litestar(route_handlers=[shipping_router])
```

This gives you a fully working set of shipment and callback endpoints.

### With custom components

You can plug in your own `OrderResolver` and `CallbackRetryStore`:

```python
from litestar_sendparcel import (
    CallbackRetryStore,
    OrderResolver,
    create_shipping_router,
)

# Implement the protocols
class MyOrderResolver:
    async def resolve(self, order_id: str) -> Order:
        ...

class MyRetryStore:
    async def store_failed_callback(
        self, shipment_id: str, provider_slug: str,
        payload: dict, headers: dict,
    ) -> str:
        ...

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        ...

    async def mark_succeeded(self, retry_id: str) -> None:
        ...

    async def mark_failed(self, retry_id: str, error: str) -> None:
        ...

    async def mark_exhausted(self, retry_id: str) -> None:
        ...


shipping_router = create_shipping_router(
    config=config,
    repository=repository,
    order_resolver=MyOrderResolver(),
    retry_store=MyRetryStore(),
)
```

## Configuration

`SendparcelConfig` is a [Pydantic Settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
model. Values can be set via constructor arguments or environment variables
with the `SENDPARCEL_` prefix.

| Setting | Type | Default | Env Variable | Description |
|---|---|---|---|---|
| `default_provider` | `str` | *(required)* | `SENDPARCEL_DEFAULT_PROVIDER` | Default shipping provider slug |
| `providers` | `dict[str, dict]` | `{}` | `SENDPARCEL_PROVIDERS` | Per-provider configuration dicts |
| `retry_enabled` | `bool` | `True` | `SENDPARCEL_RETRY_ENABLED` | Enable webhook callback retries |
| `retry_max_attempts` | `int` | `5` | `SENDPARCEL_RETRY_MAX_ATTEMPTS` | Max retry attempts before dead-lettering |
| `retry_backoff_seconds` | `int` | `60` | `SENDPARCEL_RETRY_BACKOFF_SECONDS` | Base backoff delay (exponential: `base * 2^(attempt-1)`) |

## API Endpoints

All endpoints are mounted under the router's path (default `/`).

| Method | Path | Description | Response |
|---|---|---|---|
| `GET` | `/shipments/health` | Healthcheck | `{"status": "ok"}` |
| `POST` | `/shipments/` | Create a shipment | `ShipmentResponse` |
| `POST` | `/shipments/{shipment_id}/label` | Generate shipping label | `ShipmentResponse` |
| `GET` | `/shipments/{shipment_id}/status` | Fetch and update shipment status | `ShipmentResponse` |
| `POST` | `/callbacks/{provider_slug}/{shipment_id}` | Handle provider webhook callback | `CallbackResponse` |

### Request/Response Schemas

**`CreateShipmentRequest`** (POST `/shipments/`):

```json
{
  "order_id": "ORD-0042",
  "provider": "inpost"
}
```

The `provider` field is optional — when omitted, `default_provider` from config is used.

**`ShipmentResponse`**:

```json
{
  "id": "uuid-string",
  "status": "created",
  "provider": "inpost",
  "external_id": "PROVIDER-123",
  "tracking_number": "TRACK-456",
  "label_url": "https://..."
}
```

**`CallbackResponse`**:

```json
{
  "provider": "inpost",
  "status": "accepted",
  "shipment_status": "in_transit"
}
```

### Error Responses

The router registers exception handlers that map `sendparcel` exceptions to HTTP status codes:

| Exception | Status Code | Code |
|---|---|---|
| `ShipmentNotFoundError` | 404 | `not_found` |
| `InvalidCallbackError` | 400 | `invalid_callback` |
| `InvalidTransitionError` | 409 | `invalid_transition` |
| `CommunicationError` | 502 | `communication_error` |
| `ConfigurationError` | 500 | `configuration_error` |
| `SendParcelException` | 400 | `sendparcel_error` |

All error responses have the shape `{"detail": "...", "code": "..."}`.

## SQLAlchemy Contrib

The optional `litestar_sendparcel.contrib.sqlalchemy` module provides async
SQLAlchemy 2.0 models and a repository implementation:

- **`ShipmentModel`** — maps to `sendparcel_shipments` table
- **`CallbackRetryModel`** — maps to `sendparcel_callback_retries` table
- **`SQLAlchemyShipmentRepository`** — implements the `ShipmentRepository` protocol

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from litestar_sendparcel.contrib.sqlalchemy.models import Base, ShipmentModel
from litestar_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)

engine = create_async_engine("sqlite+aiosqlite:///shipments.db")

# Create tables
async with engine.begin() as conn:
    await conn.run_sync(Base.metadata.create_all)

session_factory = async_sessionmaker(engine, expire_on_commit=False)
repository = SQLAlchemyShipmentRepository(session_factory)
```

The repository provides these async methods:

| Method | Description |
|---|---|
| `get_by_id(shipment_id)` | Fetch a shipment by ID (raises `KeyError` if not found) |
| `create(**kwargs)` | Create a new shipment record |
| `save(shipment)` | Merge and commit an existing shipment |
| `update_status(shipment_id, status, **fields)` | Update status and optional extra fields |
| `list_by_order(order_id)` | List all shipments for a given order |

## Webhook Retry Mechanism

When a `CallbackRetryStore` is provided, failed webhook callbacks are
automatically queued for retry with exponential backoff.

Use `process_due_retries()` from a background task or scheduled job:

```python
from litestar_sendparcel.retry import process_due_retries

processed = await process_due_retries(
    retry_store=my_retry_store,
    repository=repository,
    config=config,
    limit=10,
)
```

Retries use exponential backoff: `backoff_seconds * 2^(attempt - 1)`.
After `retry_max_attempts` failures, the retry is marked as exhausted (dead-lettered).

## Example Project

A full working example is included in the `example/` directory. It demonstrates:

- Order management with shipment creation
- Delivery simulation provider with configurable status progression
- Label generation (PDF)
- HTMX-powered status updates
- Tabler UI framework

### Running the example

```bash
cd litestar-sendparcel/example
uv sync
uv run litestar --app app:app run --reload
```

Open http://localhost:8000 in your browser.

## Supported Versions

| Dependency | Version |
|---|---|
| Python | >= 3.12 |
| Litestar | >= 2.0.0 |
| python-sendparcel | >= 0.1.0 |
| pydantic-settings | >= 2.0.0 |
| SQLAlchemy (optional) | >= 2.0.0 |

## Running Tests

```bash
# Install dev dependencies
pip install litestar-sendparcel[dev]

# Run tests
pytest
```

Or with `uv`:

```bash
uv sync --extra dev
uv run pytest
```

## Credits

Created and maintained by [Dominik Kozaczko](mailto:dominik@kozaczko.info).

Built on top of:

- [python-sendparcel](https://github.com/python-sendparcel/python-sendparcel) — core shipping abstraction
- [Litestar](https://litestar.dev/) — high-performance async Python web framework
- [SQLAlchemy](https://www.sqlalchemy.org/) — Python SQL toolkit (optional)

## License

[MIT](https://github.com/python-sendparcel/litestar-sendparcel/blob/main/LICENSE)
