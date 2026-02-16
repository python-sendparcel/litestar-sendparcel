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
