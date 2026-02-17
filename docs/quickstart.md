# Quickstart

## Installation

Install `litestar-sendparcel` using pip or uv:

**Using uv:**

```bash
uv add litestar-sendparcel
```

**Using pip:**

```bash
pip install litestar-sendparcel
```

## Basic setup

### 1. Create a shipment repository

`litestar-sendparcel` requires a repository implementing the `ShipmentRepository` protocol from `python-sendparcel`.
The repository handles persistence of shipment records.

```python
from sendparcel.protocols import ShipmentRepository, Shipment


class MyShipmentRepository:
    """Example in-memory repository."""

    def __init__(self):
        self._store: dict[str, Shipment] = {}
        self._counter = 0

    async def get_by_id(self, shipment_id: str) -> Shipment:
        return self._store[shipment_id]

    async def create(self, **kwargs) -> Shipment:
        self._counter += 1
        # Create your shipment object here
        ...

    async def save(self, shipment: Shipment) -> Shipment:
        self._store[str(shipment.id)] = shipment
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> Shipment:
        shipment = self._store[shipment_id]
        shipment.status = status
        return shipment
```

For a production example using SQLAlchemy, see the [example app](https://github.com/python-sendparcel/litestar-sendparcel/tree/main/example).

### 2. Configure the plugin

```python
from litestar_sendparcel import SendparcelConfig, create_shipping_router

config = SendparcelConfig(
    default_provider="dummy",
    providers={
        "dummy": {
            "latency_seconds": 0.1,
        },
    },
)

shipping_router = create_shipping_router(
    config=config,
    repository=MyShipmentRepository(),
)
```

### 3. Mount in your Litestar app

```python
from litestar import Litestar

app = Litestar(
    route_handlers=[shipping_router],
)
```

This gives you the following API endpoints:

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/shipments/health` | Health check |
| `POST` | `/shipments` | Create a shipment |
| `POST` | `/shipments/{id}/label` | Generate shipping label |
| `GET` | `/shipments/{id}/status` | Fetch latest status |
| `POST` | `/callbacks/{provider}/{id}` | Provider webhook callback |

### 4. Create a shipment via API

```bash
curl -X POST http://localhost:8000/shipments \
  -H "Content-Type: application/json" \
  -d '{
    "reference_id": "SHP-001",
    "provider": "dummy",
    "sender_address": {"name": "Sender", "city": "Warsaw", "country_code": "PL"},
    "receiver_address": {"name": "Receiver", "city": "Krakow", "country_code": "PL"},
    "parcels": [{"weight_kg": 1.5}]
  }'
```

## Next steps

- {doc}`configuration` — Full configuration reference
- {doc}`api` — API reference
- [Example app](https://github.com/python-sendparcel/litestar-sendparcel/tree/main/example) — Complete working example with SQLAlchemy, Jinja2 templates, and HTMX
