# Example App Rewrite + Documentation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the monolithic 437-line inline-HTML example app with a properly structured Litestar application using Jinja2 templates, Tabler UI, HTMX, and SQLAlchemy models; then add Sphinx documentation with quickstart, configuration, and API reference.

**Architecture:** The example app is split into separate modules — `models.py` (SQLAlchemy models implementing core protocols), `delivery_sim.py` (a `BaseProvider` subclass simulating delivery lifecycle), and `app.py` (Litestar app with Jinja2 template engine, SQLAlchemy plugin, and HTMX-driven views). Templates live in `example/templates/` using Tabler CSS framework. Sphinx docs live in `docs/` with autodoc for the public API.

**Tech Stack:** Litestar 2.x, Jinja2 (via Litestar `TemplateConfig`), SQLAlchemy (async, SQLite), HTMX 1.9, Tabler CSS, Sphinx + MyST

---

## Prerequisites

This plan assumes the critical-fixes and testing plans have already been executed. The core library (`python-sendparcel`) and litestar adapter (`litestar-sendparcel`) are functional with passing tests.

## Key Constraints

- **All user-facing strings in POLISH** (per project rules for web apps)
- **Tabler UI** for CSS framework: https://tabler.io/
- **HTMX** for dynamic interactions — no JavaScript unless strictly necessary
- **Jinja2 templates** via Litestar template engine — no inline HTML in Python
- **TypedDict returns** from Order model methods (not plain dicts)

## Reference: Core Protocols

The example must satisfy these protocols from `python-sendparcel/src/sendparcel/protocols.py`:

```python
class Order(Protocol):
    def get_total_weight(self) -> Decimal: ...
    def get_parcels(self) -> list[ParcelInfo]: ...       # ParcelInfo is TypedDict
    def get_sender_address(self) -> AddressInfo: ...     # AddressInfo is TypedDict
    def get_receiver_address(self) -> AddressInfo: ...   # AddressInfo is TypedDict

class Shipment(Protocol):
    id: str
    order: Order
    status: str
    provider: str
    external_id: str
    tracking_number: str
    label_url: str

class ShipmentRepository(Protocol):
    async def get_by_id(self, shipment_id: str) -> Shipment: ...
    async def create(self, **kwargs) -> Shipment: ...
    async def save(self, shipment: Shipment) -> Shipment: ...
    async def update_status(self, shipment_id: str, status: str, **fields) -> Shipment: ...
```

TypedDicts from `sendparcel.types`:
```python
class AddressInfo(TypedDict, total=False):
    name: str; company: str; line1: str; line2: str; city: str
    state: str; postal_code: str; country_code: str; phone: str; email: str

class ParcelInfo(TypedDict, total=False):
    weight_kg: Decimal; length_cm: Decimal; width_cm: Decimal; height_cm: Decimal
```

`BaseProvider` from `sendparcel.provider`:
```python
class BaseProvider(ABC):
    slug: ClassVar[str] = ""
    display_name: ClassVar[str] = ""
    def __init__(self, shipment: Shipment, config: dict | None = None): ...
    async def create_shipment(self, **kwargs) -> ShipmentCreateResult: ...
    async def create_label(self, **kwargs) -> LabelInfo: ...
    async def fetch_shipment_status(self, **kwargs) -> ShipmentStatusResponse: ...
    async def cancel_shipment(self, **kwargs) -> bool: ...
```

---

## Task 1: Create example project structure and pyproject.toml

**Files:**
- Create: `example/pyproject.toml`
- Create: `example/README.md`

**Step 1: Create example directory**

```bash
mkdir -p litestar-sendparcel/example/templates
```

**Step 2: Create `example/pyproject.toml`**

```toml
[project]
name = "litestar-sendparcel-example"
version = "0.1.0"
description = "Example Litestar app using litestar-sendparcel"
requires-python = ">=3.12"
dependencies = [
    "litestar[standard]>=2.0.0",
    "litestar-sendparcel>=0.1.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
    "jinja2>=3.1.0",
    "uvicorn>=0.30.0",
]

[tool.uv.sources]
litestar-sendparcel = { path = "..", editable = true }
python-sendparcel = { path = "../../python-sendparcel", editable = true }
```

**Step 3: Create `example/README.md`**

```markdown
# litestar-sendparcel example

Example Litestar application demonstrating `litestar-sendparcel` integration
with SQLAlchemy, Jinja2 templates, Tabler UI, and HTMX.

## Setup

```bash
cd litestar-sendparcel/example
uv sync
```

## Run

```bash
uv run litestar --app app:app run --reload
```

Open http://localhost:8000 in your browser.

## Features

- Order management with shipment creation
- Delivery simulation provider with configurable status progression
- Label generation (PDF)
- HTMX-powered status updates
- Tabler UI framework
```

**Step 4: Verify structure**

Run: `ls litestar-sendparcel/example/`
Expected: `pyproject.toml  README.md  templates/`

**Step 5: Commit**

```bash
git add example/pyproject.toml example/README.md example/templates/
git commit -m "feat(example): scaffold example project structure"
```

---

## Task 2: Create SQLAlchemy models

**Files:**
- Create: `example/models.py`

The models must implement the core `Order`, `Shipment`, and `ShipmentRepository` protocols. Critically, `get_parcels()` must return `list[ParcelInfo]` (TypedDict) and `get_sender_address()` / `get_receiver_address()` must return `AddressInfo` (TypedDict), not plain dicts.

**Step 1: Create `example/models.py`**

```python
"""SQLAlchemy models implementing sendparcel core protocols."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String, Text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

from sendparcel.types import AddressInfo, ParcelInfo


class Base(DeclarativeBase):
    pass


class Order(Base):
    """Order model implementing sendparcel Order protocol."""

    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(100), unique=True)

    sender_email: Mapped[str] = mapped_column(String(255))
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    sender_country_code: Mapped[str] = mapped_column(
        String(2), default="PL"
    )

    recipient_email: Mapped[str] = mapped_column(String(255))
    recipient_phone: Mapped[str] = mapped_column(String(50))
    recipient_name: Mapped[str] = mapped_column(String(255), default="")
    recipient_line1: Mapped[str] = mapped_column(String(500), default="")
    recipient_city: Mapped[str] = mapped_column(String(255), default="")
    recipient_postal_code: Mapped[str] = mapped_column(
        String(20), default=""
    )
    recipient_country_code: Mapped[str] = mapped_column(
        String(2), default="PL"
    )
    recipient_locker_code: Mapped[str] = mapped_column(
        String(50), default=""
    )

    package_size: Mapped[str] = mapped_column(String(5), default="M")
    weight_kg: Mapped[Decimal] = mapped_column(
        Numeric(6, 2), default=Decimal("1.0")
    )
    notes: Mapped[str] = mapped_column(Text, default="")

    shipments: Mapped[list[Shipment]] = relationship(
        back_populates="order", lazy="selectin"
    )

    def get_total_weight(self) -> Decimal:
        return self.weight_kg

    def get_parcels(self) -> list[ParcelInfo]:
        return [ParcelInfo(weight_kg=self.weight_kg)]

    def get_sender_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.sender_name,
            email=self.sender_email,
            country_code=self.sender_country_code,
        )

    def get_receiver_address(self) -> AddressInfo:
        return AddressInfo(
            name=self.recipient_name,
            email=self.recipient_email,
            phone=self.recipient_phone,
            line1=self.recipient_line1,
            city=self.recipient_city,
            postal_code=self.recipient_postal_code,
            country_code=self.recipient_country_code,
        )


class Shipment(Base):
    """Shipment model implementing sendparcel Shipment protocol."""

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    status: Mapped[str] = mapped_column(String(50), default="new")
    provider: Mapped[str] = mapped_column(String(100), default="")
    external_id: Mapped[str] = mapped_column(String(255), default="")
    tracking_number: Mapped[str] = mapped_column(String(255), default="")
    label_url: Mapped[str] = mapped_column(String(500), default="")

    order: Mapped[Order] = relationship(back_populates="shipments")


class ShipmentRepository:
    """Async SQLAlchemy repository implementing ShipmentRepository protocol."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, shipment_id: str) -> Shipment:
        result = await self.session.get(Shipment, int(shipment_id))
        if result is None:
            raise KeyError(f"Shipment {shipment_id} not found")
        return result

    async def create(self, **kwargs) -> Shipment:
        order = kwargs.pop("order")
        shipment = Shipment(
            order_id=order.id,
            status=str(kwargs.get("status", "new")),
            provider=str(kwargs.get("provider", "")),
            external_id=str(kwargs.get("external_id", "")),
            tracking_number=str(kwargs.get("tracking_number", "")),
            label_url=str(kwargs.get("label_url", "")),
        )
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def save(self, shipment: Shipment) -> Shipment:
        self.session.add(shipment)
        await self.session.flush()
        return shipment

    async def update_status(
        self, shipment_id: str, status: str, **fields
    ) -> Shipment:
        shipment = await self.get_by_id(shipment_id)
        shipment.status = status
        for key, value in fields.items():
            if hasattr(shipment, key):
                setattr(shipment, key, value)
        await self.session.flush()
        return shipment


engine = create_async_engine("sqlite+aiosqlite:///example.db")
async_session = async_sessionmaker(engine, expire_on_commit=False)


async def init_db() -> None:
    """Create all tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
```

**Step 2: Verify model satisfies protocol**

Run: `cd litestar-sendparcel/example && uv run python -c "from models import Order, Shipment; from sendparcel.protocols import Order as OP, Shipment as SP; print('Order:', isinstance(Order.__new__(Order), OP)); print('Shipment:', isinstance(Shipment.__new__(Shipment), SP))"`

Expected: Both print `True` (runtime_checkable protocol checks).

Note: This is a structural protocol check. The `__new__` trick creates instances without `__init__` — enough for `isinstance` on `runtime_checkable` protocols which only check method/attribute existence. If the check fails, the model is missing required methods/attributes.

**Step 3: Commit**

```bash
git add example/models.py
git commit -m "feat(example): add SQLAlchemy models implementing core protocols"
```

---

## Task 3: Create delivery simulator provider

**Files:**
- Create: `example/delivery_sim.py`

This provider subclasses `BaseProvider` to simulate the full delivery lifecycle:
- `create_shipment` → returns external_id + tracking_number
- `create_label` → returns a PDF URL
- `fetch_shipment_status` → returns configurable status for testing progression

It also provides Litestar routes for a **simulator control panel** (HTMX) where the user can advance a shipment's status through the FSM.

**Step 1: Create `example/delivery_sim.py`**

```python
"""Simulated delivery provider with control panel routes."""

from __future__ import annotations

from typing import ClassVar
from uuid import uuid4

from litestar import Router, get, post
from litestar.response import Template

from sendparcel.enums import ShipmentStatus
from sendparcel.provider import BaseProvider
from sendparcel.types import (
    LabelInfo,
    ShipmentCreateResult,
    ShipmentStatusResponse,
)

# In-memory store for simulator state keyed by shipment.id
_sim_state: dict[str, str] = {}


class DeliverySimProvider(BaseProvider):
    """Simulated delivery provider for the example app."""

    slug: ClassVar[str] = "delivery-sim"
    display_name: ClassVar[str] = "Symulator Dostawy"
    supported_countries: ClassVar[list[str]] = ["PL"]
    supported_services: ClassVar[list[str]] = ["standard"]

    async def create_shipment(self, **kwargs) -> ShipmentCreateResult:
        shipment_id = str(self.shipment.id)
        tracking = f"SIM-{uuid4().hex[:8].upper()}"
        _sim_state[shipment_id] = ShipmentStatus.CREATED
        return ShipmentCreateResult(
            external_id=f"sim-{shipment_id}",
            tracking_number=tracking,
        )

    async def create_label(self, **kwargs) -> LabelInfo:
        shipment_id = str(self.shipment.id)
        return LabelInfo(
            format="PDF",
            url=f"/sim/label/{shipment_id}.pdf",
        )

    async def fetch_shipment_status(
        self, **kwargs
    ) -> ShipmentStatusResponse:
        shipment_id = str(self.shipment.id)
        current = _sim_state.get(
            shipment_id, str(self.shipment.status)
        )
        return ShipmentStatusResponse(status=current)

    async def cancel_shipment(self, **kwargs) -> bool:
        shipment_id = str(self.shipment.id)
        _sim_state[shipment_id] = ShipmentStatus.CANCELLED
        return True


# --- Status progression helpers ---

# Allowed forward transitions for the control panel
_NEXT_STATUSES: dict[str, list[str]] = {
    ShipmentStatus.CREATED: [
        ShipmentStatus.LABEL_READY,
        ShipmentStatus.CANCELLED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.LABEL_READY: [
        ShipmentStatus.IN_TRANSIT,
        ShipmentStatus.CANCELLED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.IN_TRANSIT: [
        ShipmentStatus.OUT_FOR_DELIVERY,
        ShipmentStatus.DELIVERED,
        ShipmentStatus.RETURNED,
        ShipmentStatus.FAILED,
    ],
    ShipmentStatus.OUT_FOR_DELIVERY: [
        ShipmentStatus.DELIVERED,
        ShipmentStatus.RETURNED,
        ShipmentStatus.FAILED,
    ],
}

# Polish labels for statuses
STATUS_LABELS: dict[str, str] = {
    ShipmentStatus.NEW: "Nowa",
    ShipmentStatus.CREATED: "Utworzona",
    ShipmentStatus.LABEL_READY: "Etykieta gotowa",
    ShipmentStatus.IN_TRANSIT: "W transporcie",
    ShipmentStatus.OUT_FOR_DELIVERY: "W doręczeniu",
    ShipmentStatus.DELIVERED: "Doręczona",
    ShipmentStatus.CANCELLED: "Anulowana",
    ShipmentStatus.FAILED: "Błąd",
    ShipmentStatus.RETURNED: "Zwrócona",
}


def get_sim_status(shipment_id: str) -> str:
    """Get current simulator status for a shipment."""
    return _sim_state.get(shipment_id, ShipmentStatus.NEW)


def get_next_statuses(current: str) -> list[str]:
    """Get list of allowed next statuses from current."""
    return _NEXT_STATUSES.get(current, [])


# --- Litestar routes for the simulator control panel ---


@get("/sim/panel/{shipment_id:int}")
async def sim_panel(shipment_id: int) -> Template:
    """Render simulator control panel partial (HTMX target)."""
    sid = str(shipment_id)
    current = get_sim_status(sid)
    next_options = get_next_statuses(current)
    return Template(
        template_name="partials/sim_panel.html",
        context={
            "shipment_id": shipment_id,
            "current_status": current,
            "current_label": STATUS_LABELS.get(current, current),
            "next_options": [
                {"value": s, "label": STATUS_LABELS.get(s, s)}
                for s in next_options
            ],
        },
    )


@post("/sim/advance/{shipment_id:int}")
async def sim_advance(shipment_id: int, data: dict) -> Template:
    """Advance simulator status for a shipment (HTMX)."""
    sid = str(shipment_id)
    new_status = data.get("status", "")
    current = get_sim_status(sid)
    allowed = get_next_statuses(current)
    if new_status in allowed:
        _sim_state[sid] = new_status

    current = get_sim_status(sid)
    next_options = get_next_statuses(current)
    return Template(
        template_name="partials/sim_panel.html",
        context={
            "shipment_id": shipment_id,
            "current_status": current,
            "current_label": STATUS_LABELS.get(current, current),
            "next_options": [
                {"value": s, "label": STATUS_LABELS.get(s, s)}
                for s in next_options
            ],
        },
    )


sim_router = Router(
    path="/",
    route_handlers=[sim_panel, sim_advance],
)
```

**Step 2: Verify import**

Run: `cd litestar-sendparcel/example && uv run python -c "from delivery_sim import DeliverySimProvider; print(DeliverySimProvider.slug, DeliverySimProvider.display_name)"`

Expected: `delivery-sim Symulator Dostawy`

**Step 3: Commit**

```bash
git add example/delivery_sim.py
git commit -m "feat(example): add delivery simulator provider with control panel"
```

---

## Task 4: Create Jinja2 templates with Tabler UI

**Files:**
- Create: `example/templates/base.html`
- Create: `example/templates/home.html`
- Create: `example/templates/order_detail.html`
- Create: `example/templates/shipment_detail.html`
- Create: `example/templates/delivery_gateway.html`
- Create: `example/templates/result.html`
- Create: `example/templates/partials/sim_panel.html`

All user-facing text is in **Polish**. Uses Tabler CSS from CDN and HTMX from CDN.

**Step 1: Create `example/templates/base.html`**

```html
<!doctype html>
<html lang="pl">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{% block title %}Sendparcel Demo{% endblock %}</title>
    <link
      href="https://cdn.jsdelivr.net/npm/@tabler/core@1.0.0-beta20/dist/css/tabler.min.css"
      rel="stylesheet"
    />
    <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  </head>
  <body class="layout-fluid">
    <div class="page">
      <header class="navbar navbar-expand-md d-print-none">
        <div class="container-xl">
          <h1 class="navbar-brand navbar-brand-autodark d-none-navbar-btn">
            <a href="/">Sendparcel Demo</a>
          </h1>
          <div class="navbar-nav flex-row order-md-last">
            <span class="nav-link text-muted">Litestar + HTMX + Tabler</span>
          </div>
        </div>
      </header>
      <div class="page-wrapper">
        <div class="page-body">
          <div class="container-xl">
            {% block content %}{% endblock %}
          </div>
        </div>
      </div>
    </div>
  </body>
</html>
```

**Step 2: Create `example/templates/home.html`**

```html
{% extends "base.html" %}
{% block title %}Strona główna — Sendparcel Demo{% endblock %}
{% block content %}
<div class="page-header d-print-none mb-3">
  <div class="row align-items-center">
    <div class="col-auto">
      <h2 class="page-title">Zamówienia</h2>
    </div>
    <div class="col-auto ms-auto">
      <a href="/orders/new" class="btn btn-primary">Nowe zamówienie</a>
    </div>
  </div>
</div>

{% if orders %}
<div class="card">
  <div class="table-responsive">
    <table class="table table-vcenter card-table">
      <thead>
        <tr>
          <th>ID</th>
          <th>Referencja</th>
          <th>Odbiorca</th>
          <th>Rozmiar</th>
          <th>Przesyłki</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {% for order in orders %}
        <tr>
          <td>{{ order.id }}</td>
          <td>{{ order.reference }}</td>
          <td>{{ order.recipient_name or order.recipient_email }}</td>
          <td>{{ order.package_size }}</td>
          <td>{{ order.shipments | length }}</td>
          <td>
            <a href="/orders/{{ order.id }}" class="btn btn-sm btn-outline-primary">
              Szczegóły
            </a>
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>
{% else %}
<div class="empty">
  <p class="empty-title">Brak zamówień</p>
  <p class="empty-subtitle text-secondary">
    Utwórz pierwsze zamówienie, aby rozpocząć.
  </p>
  <div class="empty-action">
    <a href="/orders/new" class="btn btn-primary">Nowe zamówienie</a>
  </div>
</div>
{% endif %}
{% endblock %}
```

**Step 3: Create `example/templates/delivery_gateway.html`**

This is the form for creating a new order (analogous to the old checkout form).

```html
{% extends "base.html" %}
{% block title %}Nowe zamówienie — Sendparcel Demo{% endblock %}
{% block content %}
<div class="page-header d-print-none mb-3">
  <div class="row align-items-center">
    <div class="col">
      <h2 class="page-title">Nowe zamówienie</h2>
      <div class="text-secondary">
        Wypełnij dane przesyłki i wybierz dostawcę.
      </div>
    </div>
  </div>
</div>

<div class="card">
  <div class="card-body">
    <form method="post" action="/orders/create">
      <div class="row g-3">
        <div class="col-md-6">
          <label class="form-label">Dostawca</label>
          <select class="form-select" name="provider" required>
            {% for slug, name in providers %}
            <option value="{{ slug }}">{{ name }}</option>
            {% endfor %}
          </select>
        </div>
        <div class="col-md-6">
          <label class="form-label">Rozmiar paczki</label>
          <select class="form-select" name="package_size" required>
            <option value="S">S — mała</option>
            <option value="M" selected>M — średnia</option>
            <option value="L">L — duża</option>
          </select>
        </div>

        <div class="col-12">
          <hr class="my-2" />
          <h3 class="mb-3">Nadawca</h3>
        </div>
        <div class="col-md-6">
          <label class="form-label">Imię i nazwisko</label>
          <input class="form-control" type="text" name="sender_name" />
        </div>
        <div class="col-md-6">
          <label class="form-label">E-mail nadawcy</label>
          <input class="form-control" type="email" name="sender_email" required />
        </div>

        <div class="col-12">
          <hr class="my-2" />
          <h3 class="mb-3">Odbiorca</h3>
        </div>
        <div class="col-md-6">
          <label class="form-label">Imię i nazwisko</label>
          <input class="form-control" type="text" name="recipient_name" />
        </div>
        <div class="col-md-6">
          <label class="form-label">E-mail odbiorcy</label>
          <input class="form-control" type="email" name="recipient_email" required />
        </div>
        <div class="col-md-6">
          <label class="form-label">Telefon</label>
          <input class="form-control" type="text" name="recipient_phone" required />
        </div>
        <div class="col-md-6">
          <label class="form-label">Kod paczkomatu</label>
          <input class="form-control" type="text" name="recipient_locker_code"
                 placeholder="Opcjonalnie" />
        </div>
        <div class="col-md-8">
          <label class="form-label">Adres</label>
          <input class="form-control" type="text" name="recipient_line1"
                 placeholder="Ulica, numer" />
        </div>
        <div class="col-md-4">
          <label class="form-label">Miasto</label>
          <input class="form-control" type="text" name="recipient_city" />
        </div>
        <div class="col-md-4">
          <label class="form-label">Kod pocztowy</label>
          <input class="form-control" type="text" name="recipient_postal_code" />
        </div>

        <div class="col-12">
          <hr class="my-2" />
          <h3 class="mb-3">Notatki</h3>
        </div>
        <div class="col-12">
          <textarea class="form-control" name="notes" rows="2"
                    placeholder="Opcjonalne uwagi"></textarea>
        </div>
      </div>

      <div class="mt-4">
        <button class="btn btn-primary" type="submit">Utwórz zamówienie</button>
        <a href="/" class="btn btn-outline-secondary ms-2">Anuluj</a>
      </div>
    </form>
  </div>
</div>
{% endblock %}
```

**Step 4: Create `example/templates/order_detail.html`**

```html
{% extends "base.html" %}
{% block title %}Zamówienie #{{ order.id }} — Sendparcel Demo{% endblock %}
{% block content %}
<div class="page-header d-print-none mb-3">
  <div class="row align-items-center">
    <div class="col">
      <div class="page-pretitle">Zamówienie</div>
      <h2 class="page-title">{{ order.reference }}</h2>
    </div>
    <div class="col-auto ms-auto">
      <a href="/" class="btn btn-outline-secondary">Powrót do listy</a>
    </div>
  </div>
</div>

<div class="row row-deck row-cards">
  <div class="col-md-6">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Dane zamówienia</h3>
      </div>
      <div class="card-body">
        <dl class="row mb-0">
          <dt class="col-5">Nadawca:</dt>
          <dd class="col-7">{{ order.sender_name }} ({{ order.sender_email }})</dd>
          <dt class="col-5">Odbiorca:</dt>
          <dd class="col-7">{{ order.recipient_name or order.recipient_email }}</dd>
          <dt class="col-5">Telefon:</dt>
          <dd class="col-7">{{ order.recipient_phone }}</dd>
          <dt class="col-5">Adres:</dt>
          <dd class="col-7">
            {{ order.recipient_line1 }}
            {% if order.recipient_city %}, {{ order.recipient_city }}{% endif %}
            {{ order.recipient_postal_code }}
          </dd>
          {% if order.recipient_locker_code %}
          <dt class="col-5">Paczkomat:</dt>
          <dd class="col-7">{{ order.recipient_locker_code }}</dd>
          {% endif %}
          <dt class="col-5">Rozmiar:</dt>
          <dd class="col-7">{{ order.package_size }}</dd>
          <dt class="col-5">Waga:</dt>
          <dd class="col-7">{{ order.weight_kg }} kg</dd>
        </dl>
      </div>
    </div>
  </div>

  <div class="col-md-6">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Przesyłki</h3>
      </div>
      <div class="card-body">
        {% if order.shipments %}
        <div class="list-group list-group-flush">
          {% for shipment in order.shipments %}
          <a href="/shipments/{{ shipment.id }}"
             class="list-group-item list-group-item-action">
            <div class="d-flex w-100 justify-content-between">
              <h5 class="mb-1">Przesyłka #{{ shipment.id }}</h5>
              <span class="badge bg-{{ status_color(shipment.status) }}">
                {{ status_label(shipment.status) }}
              </span>
            </div>
            <small class="text-muted">
              Dostawca: {{ shipment.provider }}
              {% if shipment.tracking_number %}
              | Śledzenie: {{ shipment.tracking_number }}
              {% endif %}
            </small>
          </a>
          {% endfor %}
        </div>
        {% else %}
        <p class="text-secondary mb-0">Brak przesyłek.</p>
        {% endif %}

        <div class="mt-3">
          <form method="post" action="/orders/{{ order.id }}/ship">
            <input type="hidden" name="provider" value="{{ default_provider }}" />
            <button type="submit" class="btn btn-primary btn-sm">
              Utwórz przesyłkę
            </button>
          </form>
        </div>
      </div>
    </div>
  </div>
</div>

{% if order.notes %}
<div class="card mt-3">
  <div class="card-header"><h3 class="card-title">Notatki</h3></div>
  <div class="card-body">{{ order.notes }}</div>
</div>
{% endif %}
{% endblock %}
```

**Step 5: Create `example/templates/shipment_detail.html`**

```html
{% extends "base.html" %}
{% block title %}Przesyłka #{{ shipment.id }} — Sendparcel Demo{% endblock %}
{% block content %}
<div class="page-header d-print-none mb-3">
  <div class="row align-items-center">
    <div class="col">
      <div class="page-pretitle">Przesyłka</div>
      <h2 class="page-title">#{{ shipment.id }}</h2>
    </div>
    <div class="col-auto ms-auto">
      <a href="/orders/{{ shipment.order_id }}" class="btn btn-outline-secondary">
        Powrót do zamówienia
      </a>
    </div>
  </div>
</div>

<div class="row row-deck row-cards">
  <div class="col-md-6">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Dane przesyłki</h3>
      </div>
      <div class="card-body">
        <dl class="row mb-0">
          <dt class="col-5">Status:</dt>
          <dd class="col-7">
            <span id="shipment-status"
                  class="badge bg-{{ status_color(shipment.status) }}">
              {{ status_label(shipment.status) }}
            </span>
          </dd>
          <dt class="col-5">Dostawca:</dt>
          <dd class="col-7">{{ shipment.provider }}</dd>
          <dt class="col-5">ID zewnętrzny:</dt>
          <dd class="col-7">{{ shipment.external_id or "—" }}</dd>
          <dt class="col-5">Nr śledzenia:</dt>
          <dd class="col-7">{{ shipment.tracking_number or "—" }}</dd>
          <dt class="col-5">Etykieta:</dt>
          <dd class="col-7">
            {% if shipment.label_url %}
            <a href="{{ shipment.label_url }}" class="btn btn-sm btn-outline-primary">
              Pobierz etykietę
            </a>
            {% else %}
            —
            {% endif %}
          </dd>
        </dl>

        <div class="mt-3">
          <button class="btn btn-sm btn-outline-info"
                  hx-get="/shipments/{{ shipment.id }}/refresh-status"
                  hx-target="#shipment-status"
                  hx-swap="outerHTML">
            Odśwież status
          </button>
          {% if shipment.status in ("new", "created", "label_ready") %}
          <form method="post" action="/shipments/{{ shipment.id }}/create-label"
                class="d-inline">
            <button type="submit" class="btn btn-sm btn-outline-success">
              Generuj etykietę
            </button>
          </form>
          {% endif %}
        </div>
      </div>
    </div>
  </div>

  <div class="col-md-6">
    <div class="card">
      <div class="card-header">
        <h3 class="card-title">Symulator dostawy</h3>
      </div>
      <div class="card-body" id="sim-panel"
           hx-get="/sim/panel/{{ shipment.id }}"
           hx-trigger="load"
           hx-swap="innerHTML">
        <div class="text-secondary">Ładowanie panelu symulatora...</div>
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

**Step 6: Create `example/templates/result.html`**

```html
{% extends "base.html" %}
{% block title %}{{ title }} — Sendparcel Demo{% endblock %}
{% block content %}
<div class="row justify-content-center mt-4">
  <div class="col-md-8">
    <div class="card border-{{ card_type }}">
      <div class="card-body text-center">
        <h3 class="card-title text-{{ card_type }}">{{ title }}</h3>
        <p class="text-secondary">{{ message }}</p>
        {% if link_url %}
        <a href="{{ link_url }}" class="btn btn-primary">{{ link_text }}</a>
        {% endif %}
      </div>
    </div>
  </div>
</div>
{% endblock %}
```

**Step 7: Create `example/templates/partials/sim_panel.html`**

```html
<div id="sim-panel-inner">
  <p class="mb-2">
    Aktualny status:
    <span class="badge bg-blue">{{ current_label }}</span>
  </p>
  {% if next_options %}
  <div class="btn-list">
    {% for opt in next_options %}
    <button class="btn btn-sm btn-outline-primary"
            hx-post="/sim/advance/{{ shipment_id }}"
            hx-vals='{"status": "{{ opt.value }}"}'
            hx-target="#sim-panel"
            hx-swap="innerHTML">
      → {{ opt.label }}
    </button>
    {% endfor %}
  </div>
  {% else %}
  <p class="text-muted mb-0">Status końcowy — brak dalszych przejść.</p>
  {% endif %}
</div>
```

**Step 8: Verify templates exist**

Run: `ls litestar-sendparcel/example/templates/ && ls litestar-sendparcel/example/templates/partials/`

Expected:
```
base.html  delivery_gateway.html  home.html  order_detail.html  partials  result.html  shipment_detail.html
sim_panel.html
```

**Step 9: Commit**

```bash
git add example/templates/
git commit -m "feat(example): add Jinja2 templates with Tabler UI and HTMX"
```

---

## Task 5: Create main app with Litestar

**Files:**
- Create: `example/app.py`

This is the Litestar application entry point wiring everything together:
- Jinja2 template engine via `TemplateConfig`
- SQLAlchemy async session management via `lifespan`
- Routes for orders, shipments, label generation, status refresh
- The `delivery-sim` provider registered with the core registry
- The shipping API router from `litestar-sendparcel`
- Template globals for Polish status labels and badge colors

**Step 1: Create `example/app.py`**

```python
"""Litestar example app demonstrating litestar-sendparcel integration."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from decimal import Decimal
from pathlib import Path

from litestar import Litestar, Request, get, post
from litestar.contrib.jinja import JinjaTemplateEngine
from litestar.exceptions import NotFoundException
from litestar.response import Redirect, Template
from litestar.template import TemplateConfig

from sendparcel.enums import ShipmentStatus
from sendparcel.flow import ShipmentFlow
from sendparcel.registry import registry

from delivery_sim import (
    STATUS_LABELS,
    DeliverySimProvider,
    sim_router,
)
from models import (
    Order,
    Shipment,
    ShipmentRepository,
    async_session,
    init_db,
)

TEMPLATES_DIR = Path(__file__).parent / "templates"

# --- Register the simulator provider ---
registry.register(DeliverySimProvider)

# --- Weight presets ---
WEIGHT_BY_SIZE: dict[str, Decimal] = {
    "S": Decimal("0.5"),
    "M": Decimal("1.0"),
    "L": Decimal("2.5"),
}


# --- Template helpers ---
def status_label(status: str) -> str:
    """Polish label for a shipment status."""
    return STATUS_LABELS.get(status, status)


def status_color(status: str) -> str:
    """Tabler badge color for a shipment status."""
    colors: dict[str, str] = {
        ShipmentStatus.NEW: "secondary",
        ShipmentStatus.CREATED: "info",
        ShipmentStatus.LABEL_READY: "cyan",
        ShipmentStatus.IN_TRANSIT: "blue",
        ShipmentStatus.OUT_FOR_DELIVERY: "indigo",
        ShipmentStatus.DELIVERED: "success",
        ShipmentStatus.CANCELLED: "warning",
        ShipmentStatus.FAILED: "danger",
        ShipmentStatus.RETURNED: "orange",
    }
    return colors.get(status, "secondary")


# --- Lifespan: init DB ---
@asynccontextmanager
async def lifespan(app: Litestar) -> AsyncGenerator[None, None]:
    await init_db()
    yield


# --- Route handlers ---


@get("/")
async def home() -> Template:
    """Render order list."""
    async with async_session() as session:
        from sqlalchemy import select

        result = await session.execute(
            select(Order).order_by(Order.id.desc())
        )
        orders = result.scalars().all()
    return Template(
        template_name="home.html",
        context={"orders": orders},
    )


@get("/orders/new")
async def order_new() -> Template:
    """Render new order form."""
    providers = registry.get_choices()
    return Template(
        template_name="delivery_gateway.html",
        context={"providers": providers},
    )


@post("/orders/create")
async def order_create(request: Request) -> Redirect:
    """Create a new order from form submission."""
    form = await request.form()
    package_size = str(form.get("package_size", "M"))
    weight = WEIGHT_BY_SIZE.get(package_size, Decimal("1.0"))

    async with async_session() as session:
        from sqlalchemy import func, select

        count_result = await session.execute(select(func.count(Order.id)))
        count = count_result.scalar() or 0
        reference = f"ZAM-{count + 1:04d}"

        order = Order(
            reference=reference,
            sender_email=str(form.get("sender_email", "")),
            sender_name=str(form.get("sender_name", "")),
            recipient_email=str(form.get("recipient_email", "")),
            recipient_phone=str(form.get("recipient_phone", "")),
            recipient_name=str(form.get("recipient_name", "")),
            recipient_line1=str(form.get("recipient_line1", "")),
            recipient_city=str(form.get("recipient_city", "")),
            recipient_postal_code=str(
                form.get("recipient_postal_code", "")
            ),
            recipient_country_code="PL",
            recipient_locker_code=str(
                form.get("recipient_locker_code", "")
            ),
            package_size=package_size,
            weight_kg=weight,
            notes=str(form.get("notes", "")),
        )
        session.add(order)
        await session.commit()
        return Redirect(path=f"/orders/{order.id}")


@get("/orders/{order_id:int}")
async def order_detail(order_id: int) -> Template:
    """Render order detail page."""
    async with async_session() as session:
        order = await session.get(Order, order_id)
        if order is None:
            raise NotFoundException(detail="Zamówienie nie znalezione")
    default_provider = registry.get_choices()[0][0]
    return Template(
        template_name="order_detail.html",
        context={
            "order": order,
            "default_provider": default_provider,
            "status_label": status_label,
            "status_color": status_color,
        },
    )


@post("/orders/{order_id:int}/ship")
async def order_ship(order_id: int, request: Request) -> Redirect:
    """Create a shipment for an order using sendparcel flow."""
    form = await request.form()
    provider_slug = str(
        form.get("provider", registry.get_choices()[0][0])
    )

    async with async_session() as session:
        order = await session.get(Order, order_id)
        if order is None:
            raise NotFoundException(detail="Zamówienie nie znalezione")

        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await flow.create_shipment(order, provider_slug)
        try:
            shipment = await flow.create_label(shipment)
        except NotImplementedError:
            pass
        await session.commit()
        return Redirect(path=f"/shipments/{shipment.id}")


@get("/shipments/{shipment_id:int}")
async def shipment_detail(shipment_id: int) -> Template:
    """Render shipment detail page."""
    async with async_session() as session:
        shipment = await session.get(Shipment, shipment_id)
        if shipment is None:
            raise NotFoundException(detail="Przesyłka nie znaleziona")
    return Template(
        template_name="shipment_detail.html",
        context={
            "shipment": shipment,
            "status_label": status_label,
            "status_color": status_color,
        },
    )


@post("/shipments/{shipment_id:int}/create-label")
async def shipment_create_label(shipment_id: int) -> Redirect:
    """Generate label for shipment."""
    async with async_session() as session:
        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await repo.get_by_id(str(shipment_id))
        try:
            shipment = await flow.create_label(shipment)
        except NotImplementedError:
            pass
        await session.commit()
    return Redirect(path=f"/shipments/{shipment_id}")


@get("/shipments/{shipment_id:int}/refresh-status")
async def shipment_refresh_status(shipment_id: int) -> Template:
    """HTMX endpoint: fetch latest status and return badge HTML."""
    async with async_session() as session:
        repo = ShipmentRepository(session)
        flow = ShipmentFlow(repository=repo)
        shipment = await repo.get_by_id(str(shipment_id))
        shipment = await flow.fetch_and_update_status(shipment)
        await session.commit()

        return Template(
            template_name="partials/status_badge.html",
            context={
                "shipment": shipment,
                "status_label": status_label,
                "status_color": status_color,
            },
        )


# --- Litestar app ---

app = Litestar(
    route_handlers=[
        home,
        order_new,
        order_create,
        order_detail,
        order_ship,
        shipment_detail,
        shipment_create_label,
        shipment_refresh_status,
        sim_router,
    ],
    template_config=TemplateConfig(
        engine=JinjaTemplateEngine,
        directory=TEMPLATES_DIR,
    ),
    on_startup=[lifespan],
    debug=True,
)
```

**Step 2: Create the missing status badge partial**

Create `example/templates/partials/status_badge.html`:

```html
<span id="shipment-status"
      class="badge bg-{{ status_color(shipment.status) }}">
  {{ status_label(shipment.status) }}
</span>
```

**Step 3: Fix the lifespan — Litestar uses `on_startup` or `lifespan` context manager**

NOTE: The `on_startup` list expects callables, not async context managers. For Litestar 2.x, the correct approach is:

Replace `on_startup=[lifespan]` with Litestar's lifespan parameter. Adjust `app.py`:

The `lifespan` parameter is not a list — it's the async context manager directly. Update the Litestar constructor:

```python
app = Litestar(
    route_handlers=[
        home,
        order_new,
        order_create,
        order_detail,
        order_ship,
        shipment_detail,
        shipment_create_label,
        shipment_refresh_status,
        sim_router,
    ],
    template_config=TemplateConfig(
        engine=JinjaTemplateEngine,
        directory=TEMPLATES_DIR,
    ),
    lifespan=[lifespan],
    debug=True,
)
```

**Step 4: Verify app starts**

Run: `cd litestar-sendparcel/example && uv sync && uv run python -c "from app import app; print('App loaded, routes:', len(app.routes))"`

Expected: App loads without errors and prints the route count.

**Step 5: Commit**

```bash
git add example/app.py example/templates/partials/status_badge.html
git commit -m "feat(example): add main Litestar app with Jinja2 templates and HTMX"
```

---

## Task 6: Delete old example and update pyproject.toml

**Files:**
- Delete: `examples/app.py`
- Delete: `examples/` directory
- Modify: `pyproject.toml` (remove per-file-ignores for `examples/app.py`)

**Step 1: Remove old example**

```bash
rm -rf examples/
```

**Step 2: Update pyproject.toml — remove old per-file-ignores**

In `pyproject.toml`, remove the line:
```toml
"examples/app.py" = ["E501"]
```

from the `[tool.ruff.lint.per-file-ignores]` section. If the section becomes empty, remove it entirely.

**Step 3: Verify old example is gone**

Run: `ls examples/ 2>&1 || echo "Directory removed"`
Expected: `Directory removed`

**Step 4: Run existing tests to ensure nothing breaks**

Run: `cd litestar-sendparcel && uv run pytest tests/ -v`

Expected: All existing tests pass. If `tests/test_example_app.py` references the old example, it must be updated or removed — see substep below.

**Step 4a: Handle `tests/test_example_app.py`**

Read `tests/test_example_app.py`. If it imports from `examples/app.py`, remove the file:
```bash
rm tests/test_example_app.py
```

New tests for the example app are out of scope for this plan (they belong in `example/` itself, not in the library test suite).

**Step 5: Commit**

```bash
git add -A
git commit -m "chore: remove legacy inline-HTML example app"
```

---

## Task 7: Set up Sphinx documentation

**Files:**
- Create: `docs/conf.py`
- Create: `docs/requirements.txt`
- Modify: `docs/index.md`

**Step 1: Create `docs/requirements.txt`**

```
sphinx>=7.0
myst-parser>=3.0
sphinx-rtd-theme>=2.0
sphinx-autodoc2>=0.5
```

**Step 2: Create `docs/conf.py`**

```python
"""Sphinx configuration for litestar-sendparcel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project = "litestar-sendparcel"
copyright = "2026, Dominik Kozaczko"
author = "Dominik Kozaczko"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "plans"]

html_theme = "sphinx_rtd_theme"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "litestar": ("https://docs.litestar.dev/2/", None),
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"
```

**Step 3: Update `docs/index.md`**

```markdown
# litestar-sendparcel

Litestar adapter for [python-sendparcel](https://github.com/your-org/python-sendparcel) — a framework-agnostic parcel shipping library.

## Contents

```{toctree}
:maxdepth: 2

quickstart
configuration
api
```
```

**Step 4: Verify Sphinx builds**

Run: `cd litestar-sendparcel && uv run pip install -r docs/requirements.txt && uv run sphinx-build -b html docs docs/_build 2>&1 | tail -5`

Expected: Build succeeds (warnings about missing files for quickstart/configuration/api are expected at this point).

**Step 5: Add `docs/_build/` to `.gitignore`**

Append to `.gitignore`:
```
docs/_build/
```

**Step 6: Commit**

```bash
git add docs/conf.py docs/requirements.txt docs/index.md .gitignore
git commit -m "docs: set up Sphinx with MyST parser"
```

---

## Task 8: Write quickstart guide

**Files:**
- Create: `docs/quickstart.md`

**Step 1: Create `docs/quickstart.md`**

```markdown
# Quickstart

## Installation

Install `litestar-sendparcel` using pip or uv:

::::{tab-set}

:::{tab-item} uv
```bash
uv add litestar-sendparcel
```
:::

:::{tab-item} pip
```bash
pip install litestar-sendparcel
```
:::

::::

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

For a production example using SQLAlchemy, see the [example app](https://github.com/your-org/litestar-sendparcel/tree/main/example).

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
  -d '{"order_id": "order-001", "provider": "dummy"}'
```

## Order resolver

To use the `POST /shipments` endpoint, you must provide an `OrderResolver` — an async callable that maps `order_id` strings to objects implementing the `Order` protocol:

```python
from litestar_sendparcel.protocols import OrderResolver


class MyOrderResolver:
    async def resolve(self, order_id: str):
        # Load order from your database
        ...


shipping_router = create_shipping_router(
    config=config,
    repository=MyShipmentRepository(),
    order_resolver=MyOrderResolver(),
)
```

## Next steps

- {doc}`configuration` — Full configuration reference
- {doc}`api` — API reference
- [Example app](https://github.com/your-org/litestar-sendparcel/tree/main/example) — Complete working example with SQLAlchemy, Jinja2 templates, and HTMX
```

**Step 2: Verify Sphinx builds with quickstart**

Run: `cd litestar-sendparcel && uv run sphinx-build -b html docs docs/_build 2>&1 | tail -3`

Expected: Build succeeds.

**Step 3: Commit**

```bash
git add docs/quickstart.md
git commit -m "docs: add quickstart guide"
```

---

## Task 9: Write configuration reference

**Files:**
- Create: `docs/configuration.md`

**Step 1: Create `docs/configuration.md`**

```markdown
# Configuration

## `SendparcelConfig`

The main configuration object for `litestar-sendparcel`. It extends
[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/)
`BaseSettings`, so values can be loaded from environment variables.

```python
from litestar_sendparcel import SendparcelConfig

config = SendparcelConfig(
    default_provider="dummy",
    providers={
        "dummy": {
            "latency_seconds": 0.5,
            "label_base_url": "https://labels.example.com",
        },
    },
)
```

### Parameters

`default_provider`
: **Required.** The slug of the provider to use when no provider is specified in a shipment creation request.

`providers`
: **Optional.** A dictionary mapping provider slugs to their configuration dictionaries. Each provider class reads its own keys via `self.get_setting(name, default)`.

### Environment variables

Since `SendparcelConfig` extends `BaseSettings`, you can set values via environment variables:

```bash
export DEFAULT_PROVIDER=dummy
```

## `create_shipping_router`

Factory function that creates a configured Litestar `Router` with all shipment endpoints.

```python
from litestar_sendparcel import create_shipping_router, SendparcelConfig

router = create_shipping_router(
    config=config,
    repository=my_repository,
    registry=my_registry,           # optional
    order_resolver=my_resolver,     # optional
    retry_store=my_retry_store,     # optional
)
```

### Parameters

`config`
: **Required.** `SendparcelConfig` instance.

`repository`
: **Required.** Object implementing `sendparcel.protocols.ShipmentRepository`.

`registry`
: **Optional.** `LitestarPluginRegistry` instance. If not provided, a new one is created and `discover()` is called to load providers from entry points.

`order_resolver`
: **Optional.** Object implementing `litestar_sendparcel.protocols.OrderResolver`. Required for the `POST /shipments` endpoint to resolve order IDs to `Order` objects.

`retry_store`
: **Optional.** Object implementing `litestar_sendparcel.protocols.CallbackRetryStore`. When provided, failed callback payloads are persisted for later retry.

## `LitestarPluginRegistry`

Extended registry with per-provider router support.

```python
from litestar_sendparcel import LitestarPluginRegistry

my_registry = LitestarPluginRegistry()
my_registry.discover()  # loads built-in + entry-point providers
```

### Methods

`register_provider_router(slug, router)`
: Register a Litestar router for a specific provider. Useful for providers that need custom endpoints (e.g., OAuth callbacks, webhook setup).

`get_provider_router(slug)`
: Retrieve a registered provider router by slug. Returns `None` if not found.

## Provider configuration

Each provider class receives its config section as a dict. The built-in `DummyProvider` supports:

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `latency_seconds` | `float` | `0.0` | Simulated API latency |
| `label_base_url` | `str` | `https://dummy.local/labels` | Base URL for generated label URLs |
| `callback_token` | `str` | `dummy-token` | Expected token in `x-dummy-token` header |
| `status_override` | `str` | current status | Override status returned by `fetch_shipment_status` |
| `cancel_success` | `bool` | `True` | Whether cancellation succeeds |

## Protocols

### `OrderResolver`

```python
class OrderResolver(Protocol):
    async def resolve(self, order_id: str) -> Order: ...
```

Maps string order IDs to `sendparcel.protocols.Order` instances.

### `CallbackRetryStore`

```python
class CallbackRetryStore(Protocol):
    async def enqueue(self, payload: dict) -> None: ...
```

Persists failed callback payloads for retry. The payload dict contains:
- `provider` — provider slug
- `shipment_id` — shipment identifier
- `payload` — original callback body
- `headers` — original callback headers
- `reason` — failure reason string
- `queued_at` — ISO 8601 timestamp
```

**Step 2: Verify Sphinx builds**

Run: `cd litestar-sendparcel && uv run sphinx-build -b html docs docs/_build 2>&1 | tail -3`

Expected: Build succeeds.

**Step 3: Commit**

```bash
git add docs/configuration.md
git commit -m "docs: add configuration reference"
```

---

## Task 10: Write API reference with autodoc

**Files:**
- Create: `docs/api.md`

**Step 1: Create `docs/api.md`**

```markdown
# API Reference

## Public API

### `litestar_sendparcel`

```{eval-rst}
.. automodule:: litestar_sendparcel
   :members:
   :undoc-members:
```

### Configuration

```{eval-rst}
.. automodule:: litestar_sendparcel.config
   :members:
   :undoc-members:
   :show-inheritance:
```

### Plugin factory

```{eval-rst}
.. automodule:: litestar_sendparcel.plugin
   :members:
   :undoc-members:
```

### Registry

```{eval-rst}
.. automodule:: litestar_sendparcel.registry
   :members:
   :undoc-members:
   :show-inheritance:
```

### Protocols

```{eval-rst}
.. automodule:: litestar_sendparcel.protocols
   :members:
   :undoc-members:
   :show-inheritance:
```

### Schemas

```{eval-rst}
.. automodule:: litestar_sendparcel.schemas
   :members:
   :undoc-members:
   :show-inheritance:
```

## Route handlers

### Shipment endpoints

```{eval-rst}
.. automodule:: litestar_sendparcel.routes.shipments
   :members:
   :undoc-members:
```

### Callback endpoints

```{eval-rst}
.. automodule:: litestar_sendparcel.routes.callbacks
   :members:
   :undoc-members:
```

### Retry helpers

```{eval-rst}
.. automodule:: litestar_sendparcel.retry
   :members:
   :undoc-members:
```
```

**Step 2: Verify full Sphinx build**

Run: `cd litestar-sendparcel && uv run sphinx-build -b html docs docs/_build 2>&1 | tail -5`

Expected: Build succeeds. Autodoc generates pages for all modules.

**Step 3: Commit**

```bash
git add docs/api.md
git commit -m "docs: add API reference with autodoc"
```

---

## Final Verification

After all tasks are complete, perform these checks:

**1. Example app runs:**

```bash
cd litestar-sendparcel/example
uv sync
uv run litestar --app app:app run
```

Open http://localhost:8000 — should show the order list page in Polish with Tabler UI.

**2. Full test suite passes:**

```bash
cd litestar-sendparcel
uv run pytest tests/ -v
```

**3. Sphinx docs build cleanly:**

```bash
cd litestar-sendparcel
uv run sphinx-build -b html docs docs/_build -W
```

The `-W` flag turns warnings into errors to catch broken references.

**4. Ruff passes:**

```bash
cd litestar-sendparcel
uv run ruff check src/ example/
```
