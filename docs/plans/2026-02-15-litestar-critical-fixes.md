# Litestar-Sendparcel Critical Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix critical bugs, add SQLAlchemy contrib, complete retry lifecycle, and adopt Litestar Controller patterns in `litestar-sendparcel`.

**Architecture:** Add structured exception handling with `EXCEPTION_HANDLERS` dict wired into the router. Create `contrib/sqlalchemy/` with ShipmentModel, CallbackRetryModel, repository, and retry store — all following the litestar-getpaid reference. Expand `CallbackRetryStore` protocol to a full 5-method lifecycle. Replace standalone handler functions with Litestar `Controller` classes using `Annotated[..., Dependency(skip_validation=True)]`.

**Tech Stack:** Litestar 2.x, SQLAlchemy 2.x async (aiosqlite for tests), Pydantic Settings, pytest-asyncio

---

## Pre-requisites

- Working directory: `litestar-sendparcel/`
- Run tests: `uv run pytest tests/ -v`
- Core exception hierarchy (from `sendparcel.exceptions`):
  - `SendParcelException(Exception)` — base, has `.context` dict
  - `CommunicationError(SendParcelException)`
  - `InvalidCallbackError(SendParcelException)`
  - `InvalidTransitionError(SendParcelException)`

---

### Task 1: Add exceptions module with EXCEPTION_HANDLERS dict

**Files:**
- Create: `src/litestar_sendparcel/exceptions.py`
- Test: `tests/test_exceptions.py`

**Step 1: Write the test file**

```python
# tests/test_exceptions.py
"""Tests for exception-to-HTTP-response mapping."""

from litestar import Litestar, get
from litestar.testing import TestClient

from litestar_sendparcel.exceptions import EXCEPTION_HANDLERS


def test_sendparcel_exception_returns_400():
    """SendParcelException maps to 400."""
    from sendparcel.exceptions import SendParcelException

    @get("/test")
    async def handler() -> None:
        raise SendParcelException("bad request")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 400
        data = resp.json()
        assert data["detail"] == "bad request"
        assert data["code"] == "sendparcel_error"


def test_communication_error_returns_502():
    """CommunicationError maps to 502."""
    from sendparcel.exceptions import CommunicationError

    @get("/test")
    async def handler() -> None:
        raise CommunicationError("gateway down")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 502
        assert resp.json()["code"] == "communication_error"


def test_invalid_callback_returns_400():
    """InvalidCallbackError maps to 400."""
    from sendparcel.exceptions import InvalidCallbackError

    @get("/test")
    async def handler() -> None:
        raise InvalidCallbackError("bad signature")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_callback"


def test_invalid_transition_returns_409():
    """InvalidTransitionError maps to 409."""
    from sendparcel.exceptions import InvalidTransitionError

    @get("/test")
    async def handler() -> None:
        raise InvalidTransitionError("wrong state")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 409
        assert resp.json()["code"] == "invalid_transition"


def test_shipment_not_found_returns_404():
    """ShipmentNotFoundError maps to 404."""
    from litestar_sendparcel.exceptions import ShipmentNotFoundError

    @get("/test")
    async def handler() -> None:
        raise ShipmentNotFoundError("ship-123")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 404
        data = resp.json()
        assert data["code"] == "not_found"
        assert "ship-123" in data["detail"]


def test_configuration_error_returns_500():
    """ConfigurationError maps to 500."""
    from litestar_sendparcel.exceptions import ConfigurationError

    @get("/test")
    async def handler() -> None:
        raise ConfigurationError("missing order resolver")

    app = Litestar(
        route_handlers=[handler],
        exception_handlers=EXCEPTION_HANDLERS,
    )
    with TestClient(app) as client:
        resp = client.get("/test")
        assert resp.status_code == 500
        assert resp.json()["code"] == "configuration_error"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'litestar_sendparcel.exceptions'`

**Step 3: Write the implementation**

```python
# src/litestar_sendparcel/exceptions.py
"""Exception handling for litestar-sendparcel."""

from litestar import Request, Response
from sendparcel.exceptions import (
    CommunicationError,
    InvalidCallbackError,
    InvalidTransitionError,
    SendParcelException,
)


class ShipmentNotFoundError(Exception):
    """Shipment with given ID was not found."""

    def __init__(self, shipment_id: str) -> None:
        self.shipment_id = shipment_id
        super().__init__(f"Shipment {shipment_id!r} not found")


class ConfigurationError(Exception):
    """A required component is not configured."""

    def __init__(self, message: str) -> None:
        super().__init__(message)


def _error_response(
    request: Request, detail: str, code: str, status_code: int
) -> Response:
    return Response(
        content={"detail": detail, "code": code},
        status_code=status_code,
    )


def handle_communication_error(
    request: Request, exc: CommunicationError
) -> Response:
    """Map CommunicationError to 502."""
    return _error_response(request, str(exc), "communication_error", 502)


def handle_invalid_callback(
    request: Request, exc: InvalidCallbackError
) -> Response:
    """Map InvalidCallbackError to 400."""
    return _error_response(request, str(exc), "invalid_callback", 400)


def handle_invalid_transition(
    request: Request, exc: InvalidTransitionError
) -> Response:
    """Map InvalidTransitionError to 409."""
    return _error_response(request, str(exc), "invalid_transition", 409)


def handle_shipment_not_found(
    request: Request, exc: ShipmentNotFoundError
) -> Response:
    """Map ShipmentNotFoundError to 404."""
    return _error_response(request, str(exc), "not_found", 404)


def handle_configuration_error(
    request: Request, exc: ConfigurationError
) -> Response:
    """Map ConfigurationError to 500."""
    return _error_response(request, str(exc), "configuration_error", 500)


def handle_sendparcel_exception(
    request: Request, exc: SendParcelException
) -> Response:
    """Map generic SendParcelException to 400."""
    return _error_response(request, str(exc), "sendparcel_error", 400)


EXCEPTION_HANDLERS = {
    CommunicationError: handle_communication_error,
    InvalidCallbackError: handle_invalid_callback,
    InvalidTransitionError: handle_invalid_transition,
    ShipmentNotFoundError: handle_shipment_not_found,
    ConfigurationError: handle_configuration_error,
    SendParcelException: handle_sendparcel_exception,
}
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: 6 passed

**Step 5: Commit**

```bash
git add src/litestar_sendparcel/exceptions.py tests/test_exceptions.py
git commit -m "feat: add exceptions module with EXCEPTION_HANDLERS dict"
```

---

### Task 2: Wire EXCEPTION_HANDLERS into router

**Files:**
- Modify: `src/litestar_sendparcel/plugin.py`
- Test: `tests/test_plugin.py`

**Step 1: Write the test**

Add to `tests/test_plugin.py`:

```python
# Append to existing tests/test_plugin.py

from sendparcel.exceptions import CommunicationError

from litestar_sendparcel.exceptions import EXCEPTION_HANDLERS


def test_router_has_exception_handlers() -> None:
    """Router includes EXCEPTION_HANDLERS."""
    router = create_shipping_router(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    for exc_type, handler_fn in EXCEPTION_HANDLERS.items():
        assert exc_type in router.exception_handlers
        assert router.exception_handlers[exc_type] is handler_fn
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_plugin.py::test_router_has_exception_handlers -v`
Expected: FAIL — `AssertionError` (exception_handlers not present on router)

**Step 3: Modify plugin.py to wire in exception handlers**

In `src/litestar_sendparcel/plugin.py`, add the import and pass `exception_handlers` to `Router`:

```python
# Add import at top:
from litestar_sendparcel.exceptions import EXCEPTION_HANDLERS

# Modify the Router() call — add exception_handlers parameter:
    return Router(
        path="/",
        route_handlers=[
            shipments_health,
            create_shipment,
            create_label,
            fetch_status,
            provider_callback,
        ],
        dependencies={
            "config": Provide(lambda: config, sync_to_thread=False),
            "repository": Provide(lambda: repository, sync_to_thread=False),
            "registry": Provide(
                lambda: actual_registry,
                sync_to_thread=False,
            ),
            "order_resolver": Provide(
                lambda: order_resolver,
                sync_to_thread=False,
            ),
            "retry_store": Provide(lambda: retry_store, sync_to_thread=False),
        },
        exception_handlers=EXCEPTION_HANDLERS,
    )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_plugin.py -v`
Expected: all passed

**Step 5: Run full suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 6: Commit**

```bash
git add src/litestar_sendparcel/plugin.py tests/test_plugin.py
git commit -m "feat: wire EXCEPTION_HANDLERS into shipping router"
```

---

### Task 3: Fix callback route error handling

**Files:**
- Modify: `src/litestar_sendparcel/routes/callbacks.py`
- Test: `tests/test_routes_flow.py` (existing tests verify behavior)

**Context:** Currently `callbacks.py` catches `InvalidCallbackError` and enqueues a retry — this is wrong, invalid callbacks should NOT be retried. Also catches bare `Exception` which should be replaced by catching `CommunicationError` only, then re-raising the exception for the exception handler to map to HTTP.

**Step 1: Write new test for communication error retry**

Add to `tests/test_routes_flow.py`:

```python
# Append to existing tests/test_routes_flow.py
from sendparcel.exceptions import CommunicationError


class FailingProvider(BaseProvider):
    """Provider that raises CommunicationError on callback."""

    slug = "failing"
    display_name = "Failing"

    async def create_shipment(self, **kwargs):
        return {"external_id": "ext-1", "tracking_number": "trk-1"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels/s-1.pdf"}

    async def verify_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        pass

    async def handle_callback(
        self, data: dict, headers: dict, **kwargs
    ) -> None:
        raise CommunicationError("provider unreachable")

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


def _create_failing_client(repo, resolver, retry_store):
    registry.register(FailingProvider)
    router = create_shipping_router(
        config=SendparcelConfig(
            default_provider="failing",
            providers={"failing": {}},
        ),
        repository=repo,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    app = Litestar(route_handlers=[router])
    return TestClient(app=app)


def test_communication_error_enqueues_retry_and_returns_502(
    repository, resolver, retry_store
) -> None:
    """CommunicationError should enqueue retry and return 502."""
    client = _create_failing_client(repository, resolver, retry_store)

    with client:
        created = client.post(
            "/shipments", json={"order_id": "o-1"}
        )
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/failing/{shipment_id}",
            headers={"x-token": "ok"},
            json={"event": "picked_up"},
        )

        assert callback.status_code == 502
        assert len(retry_store.events) == 1
        assert retry_store.events[0]["reason"] == "provider unreachable"


def test_invalid_callback_does_not_enqueue_retry(
    repository, resolver, retry_store
) -> None:
    """InvalidCallbackError should NOT enqueue a retry."""
    client = _create_client(repository, resolver, retry_store)

    with client:
        created = client.post(
            "/shipments", json={"order_id": "o-1"}
        )
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/dummy/{shipment_id}",
            headers={"x-dummy-token": "bad"},
            json={"event": "picked_up"},
        )

        assert callback.status_code == 400
        assert len(retry_store.events) == 0
```

**Step 2: Run tests to verify the new tests fail**

Run: `uv run pytest tests/test_routes_flow.py::test_invalid_callback_does_not_enqueue_retry -v`
Expected: FAIL — `assert len(retry_store.events) == 0` fails because current code enqueues on InvalidCallbackError

**Step 3: Fix the callback route**

Replace the entire content of `src/litestar_sendparcel/routes/callbacks.py`:

```python
"""Callback endpoints."""

from __future__ import annotations

import logging

from litestar import Request, post
from sendparcel.exceptions import CommunicationError, InvalidCallbackError
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import ShipmentNotFoundError
from litestar_sendparcel.protocols import CallbackRetryStore
from litestar_sendparcel.retry import enqueue_callback_retry
from litestar_sendparcel.schemas import CallbackResponse

logger = logging.getLogger(__name__)


@post("/callbacks/{provider_slug:str}/{shipment_id:str}")
async def provider_callback(
    provider_slug: str,
    shipment_id: str,
    request: Request,
    config: SendparcelConfig,
    repository: ShipmentRepository,
    retry_store: CallbackRetryStore | None = None,
) -> CallbackResponse:
    """Handle provider callback using core flow and retry hooks."""
    flow = ShipmentFlow(repository=repository, config=config.providers)

    try:
        shipment = await repository.get_by_id(shipment_id)
    except KeyError as exc:
        raise ShipmentNotFoundError(shipment_id) from exc

    if str(shipment.provider) != provider_slug:
        raise InvalidCallbackError("Provider slug mismatch")

    raw_body = await request.body()
    payload = await request.json()
    headers = dict(request.headers)

    try:
        updated = await flow.handle_callback(
            shipment,
            payload,
            headers,
            raw_body=raw_body,
        )
    except InvalidCallbackError:
        raise
    except CommunicationError as exc:
        await enqueue_callback_retry(
            retry_store,
            provider_slug=provider_slug,
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
            reason=str(exc),
        )
        raise

    return CallbackResponse(
        provider=provider_slug,
        status="accepted",
        shipment_status=str(updated.status),
    )
```

**Step 4: Run all route tests**

Run: `uv run pytest tests/test_routes_flow.py -v`
Expected: all passed

**Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 6: Commit**

```bash
git add src/litestar_sendparcel/routes/callbacks.py tests/test_routes_flow.py
git commit -m "fix: callback route re-raises exceptions, only retries CommunicationError"
```

---

### Task 4: Add __version__ and py.typed marker

**Files:**
- Modify: `src/litestar_sendparcel/__init__.py`
- Create: `src/litestar_sendparcel/py.typed`
- Modify: `pyproject.toml`
- Test: `tests/test_public_api.py`

**Step 1: Write the test**

```python
# tests/test_public_api.py
"""Tests for public API surface."""

from pathlib import Path


def test_version_is_set():
    """Package exposes __version__."""
    import litestar_sendparcel

    assert hasattr(litestar_sendparcel, "__version__")
    assert litestar_sendparcel.__version__ == "0.1.0"


def test_py_typed_marker_exists():
    """PEP 561 py.typed marker file exists."""
    marker = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "litestar_sendparcel"
        / "py.typed"
    )
    assert marker.exists()
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL — `AttributeError: module 'litestar_sendparcel' has no attribute '__version__'`

**Step 3: Create py.typed marker**

Create an empty file at `src/litestar_sendparcel/py.typed` (zero bytes).

**Step 4: Add __version__ to __init__.py**

At the top of `src/litestar_sendparcel/__init__.py`, after the docstring and before the imports, add:

```python
__version__ = "0.1.0"
```

The file should now look like:

```python
"""Litestar adapter public API."""

__version__ = "0.1.0"

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router
from litestar_sendparcel.registry import LitestarPluginRegistry

__all__ = [
    "LitestarPluginRegistry",
    "SendparcelConfig",
    "__version__",
    "create_shipping_router",
]
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 2 passed

**Step 6: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 7: Commit**

```bash
git add src/litestar_sendparcel/__init__.py src/litestar_sendparcel/py.typed tests/test_public_api.py
git commit -m "feat: add __version__ and PEP 561 py.typed marker"
```

---

### Task 5: Add routes/__init__.py

**Files:**
- Create: `src/litestar_sendparcel/routes/__init__.py`

**Step 1: Create the file**

```python
# src/litestar_sendparcel/routes/__init__.py
"""Route modules for litestar-sendparcel."""
```

**Step 2: Run full suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 3: Commit**

```bash
git add src/litestar_sendparcel/routes/__init__.py
git commit -m "chore: add routes __init__.py for proper packaging"
```

---

### Task 6: Add [sqlalchemy] optional extra to pyproject.toml

**Files:**
- Modify: `pyproject.toml`

**Step 1: Add the optional dependency group**

In `pyproject.toml`, add to `[project.optional-dependencies]`:

```toml
[project.optional-dependencies]
sqlalchemy = [
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24.0",
    "ruff>=0.9.0",
    "sqlalchemy[asyncio]>=2.0.0",
    "aiosqlite>=0.20.0",
]
```

**Step 2: Install the new dependencies**

Run: `uv sync --extra dev --extra sqlalchemy`
Expected: installs sqlalchemy and aiosqlite

**Step 3: Verify import works**

Run: `uv run python -c "from sqlalchemy.ext.asyncio import create_async_engine; print('ok')"`
Expected: `ok`

**Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "feat: add [sqlalchemy] optional extra with aiosqlite"
```

---

### Task 7: Create contrib/sqlalchemy/ models

**Files:**
- Create: `src/litestar_sendparcel/contrib/__init__.py`
- Create: `src/litestar_sendparcel/contrib/sqlalchemy/__init__.py`
- Create: `src/litestar_sendparcel/contrib/sqlalchemy/models.py`
- Test: `tests/test_contrib_sqlalchemy_models.py`

**Step 1: Write the test**

```python
# tests/test_contrib_sqlalchemy_models.py
"""Tests for SQLAlchemy 2.0 async models."""

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from litestar_sendparcel.contrib.sqlalchemy.models import (
    Base,
    CallbackRetryModel,
    ShipmentModel,
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session(engine):
    session_factory = async_sessionmaker(engine, class_=AsyncSession)
    async with session_factory() as session:
        yield session


async def test_shipment_model_create(session):
    """Can create a ShipmentModel with defaults."""
    shipment = ShipmentModel(
        order_id="order-1",
        provider="dummy",
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)

    assert shipment.id is not None
    assert len(shipment.id) == 36  # UUID
    assert shipment.status == "new"
    assert shipment.external_id == ""
    assert shipment.tracking_number == ""
    assert shipment.label_url == ""


async def test_shipment_model_with_all_fields(session):
    """Can create a ShipmentModel with all fields populated."""
    shipment = ShipmentModel(
        order_id="order-2",
        provider="inpost",
        status="label_ready",
        external_id="ext-123",
        tracking_number="trk-456",
        label_url="https://labels/s-1.pdf",
    )
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)

    assert shipment.provider == "inpost"
    assert shipment.status == "label_ready"
    assert shipment.external_id == "ext-123"
    assert shipment.created_at is not None
    assert shipment.updated_at is not None


async def test_shipment_model_table_name():
    """ShipmentModel uses correct table name."""
    assert ShipmentModel.__tablename__ == "sendparcel_shipments"


async def test_callback_retry_model_create(session):
    """Can create a CallbackRetryModel with defaults."""
    retry = CallbackRetryModel(
        shipment_id="s-1",
        provider_slug="dummy",
        payload={"event": "picked_up"},
        headers={"content-type": "application/json"},
    )
    session.add(retry)
    await session.commit()
    await session.refresh(retry)

    assert retry.id is not None
    assert len(retry.id) == 36  # UUID
    assert retry.attempts == 0
    assert retry.status == "pending"
    assert retry.last_error is None
    assert retry.next_retry_at is None


async def test_callback_retry_model_table_name():
    """CallbackRetryModel uses correct table name."""
    assert CallbackRetryModel.__tablename__ == "sendparcel_callback_retries"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'litestar_sendparcel.contrib'`

**Step 3: Create the package structure**

Create `src/litestar_sendparcel/contrib/__init__.py`:

```python
"""Contrib modules for litestar-sendparcel."""
```

Create `src/litestar_sendparcel/contrib/sqlalchemy/__init__.py`:

```python
"""SQLAlchemy 2.0 async contrib module for litestar-sendparcel."""
```

**Step 4: Write the models module**

```python
# src/litestar_sendparcel/contrib/sqlalchemy/models.py
"""SQLAlchemy 2.0 async models for shipment processing."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import JSON, DateTime, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all sendparcel models."""


class ShipmentModel(Base):
    """Shipment record implementing the ShipmentRepository protocol."""

    __tablename__ = "sendparcel_shipments"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    order_id: Mapped[str] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(32), default="new")
    provider: Mapped[str] = mapped_column(String(64))
    external_id: Mapped[str] = mapped_column(String(128), default="")
    tracking_number: Mapped[str] = mapped_column(String(128), default="")
    label_url: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )


class CallbackRetryModel(Base):
    """Webhook callback retry queue entry."""

    __tablename__ = "sendparcel_callback_retries"

    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    shipment_id: Mapped[str] = mapped_column(String(36), index=True)
    provider_slug: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict] = mapped_column(JSON)
    headers: Mapped[dict] = mapped_column(JSON)
    attempts: Mapped[int] = mapped_column(default=0)
    next_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, nullable=True, default=None
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
    )
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_contrib_sqlalchemy_models.py -v`
Expected: 5 passed

**Step 6: Commit**

```bash
git add src/litestar_sendparcel/contrib/ tests/test_contrib_sqlalchemy_models.py
git commit -m "feat: add SQLAlchemy contrib models (ShipmentModel, CallbackRetryModel)"
```

---

### Task 8: Create contrib/sqlalchemy/ repository

**Files:**
- Create: `src/litestar_sendparcel/contrib/sqlalchemy/repository.py`
- Test: `tests/test_contrib_sqlalchemy_repository.py`

**Step 1: Write the test**

```python
# tests/test_contrib_sqlalchemy_repository.py
"""Tests for SQLAlchemy ShipmentRepository implementation."""

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from litestar_sendparcel.contrib.sqlalchemy.models import Base
from litestar_sendparcel.contrib.sqlalchemy.repository import (
    SQLAlchemyShipmentRepository,
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession)


@pytest.fixture
def repo(session_factory):
    return SQLAlchemyShipmentRepository(session_factory=session_factory)


async def test_create_shipment(repo):
    """Repository creates a shipment."""
    shipment = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    assert shipment.id is not None
    assert shipment.order_id == "order-1"
    assert shipment.status == "new"
    assert shipment.provider == "dummy"


async def test_get_by_id(repo):
    """Repository retrieves a shipment by ID."""
    created = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    fetched = await repo.get_by_id(created.id)
    assert fetched.id == created.id
    assert fetched.order_id == "order-1"


async def test_get_by_id_not_found(repo):
    """KeyError when shipment not found."""
    with pytest.raises(KeyError):
        await repo.get_by_id("nonexistent")


async def test_save_shipment(repo):
    """Repository saves updated shipment fields."""
    shipment = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    shipment.external_id = "ext-123"
    saved = await repo.save(shipment)
    assert saved.external_id == "ext-123"

    fetched = await repo.get_by_id(shipment.id)
    assert fetched.external_id == "ext-123"


async def test_update_status(repo):
    """Repository updates shipment status."""
    shipment = await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    updated = await repo.update_status(
        shipment.id, "label_ready", external_id="ext-456"
    )
    assert updated.status == "label_ready"
    assert updated.external_id == "ext-456"


async def test_list_by_order(repo):
    """Repository lists shipments for an order."""
    await repo.create(
        order_id="order-1",
        provider="dummy",
        status="new",
    )
    await repo.create(
        order_id="order-1",
        provider="inpost",
        status="new",
    )
    await repo.create(
        order_id="order-2",
        provider="dummy",
        status="new",
    )

    shipments = await repo.list_by_order("order-1")
    assert len(shipments) == 2
    assert all(s.order_id == "order-1" for s in shipments)


async def test_list_by_order_empty(repo):
    """Empty list when no shipments for order."""
    shipments = await repo.list_by_order("nonexistent")
    assert shipments == []
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'litestar_sendparcel.contrib.sqlalchemy.repository'`

**Step 3: Write the implementation**

```python
# src/litestar_sendparcel/contrib/sqlalchemy/repository.py
"""SQLAlchemy 2.0 async ShipmentRepository implementation."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from litestar_sendparcel.contrib.sqlalchemy.models import ShipmentModel


class SQLAlchemyShipmentRepository:
    """Shipment repository backed by SQLAlchemy async sessions.

    Implements the ShipmentRepository protocol from sendparcel.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory

    async def get_by_id(self, shipment_id: str) -> ShipmentModel:
        """Get a shipment by ID. Raises KeyError if not found."""
        async with self._session_factory() as session:
            result = await session.get(ShipmentModel, shipment_id)
            if result is None:
                raise KeyError(shipment_id)
            session.expunge(result)
            return result

    async def create(self, **kwargs) -> ShipmentModel:
        """Create a new shipment record."""
        order = kwargs.pop("order", None)
        if order is not None and "order_id" not in kwargs:
            kwargs["order_id"] = str(getattr(order, "id", order))
        # Ensure status is a string
        if "status" in kwargs:
            kwargs["status"] = str(kwargs["status"])
        async with self._session_factory() as session:
            shipment = ShipmentModel(**kwargs)
            session.add(shipment)
            await session.commit()
            await session.refresh(shipment)
            session.expunge(shipment)
            return shipment

    async def save(self, shipment: ShipmentModel) -> ShipmentModel:
        """Save an existing shipment (merge and commit)."""
        async with self._session_factory() as session:
            merged = await session.merge(shipment)
            await session.commit()
            await session.refresh(merged)
            session.expunge(merged)
            return merged

    async def update_status(
        self,
        shipment_id: str,
        status: str,
        **fields,
    ) -> ShipmentModel:
        """Update shipment status and optional extra fields."""
        async with self._session_factory() as session:
            shipment = await session.get(ShipmentModel, shipment_id)
            if shipment is None:
                raise KeyError(shipment_id)
            shipment.status = status
            for key, value in fields.items():
                if hasattr(shipment, key):
                    setattr(shipment, key, value)
            await session.commit()
            await session.refresh(shipment)
            session.expunge(shipment)
            return shipment

    async def list_by_order(
        self, order_id: str
    ) -> list[ShipmentModel]:
        """List all shipments for an order."""
        async with self._session_factory() as session:
            stmt = select(ShipmentModel).where(
                ShipmentModel.order_id == order_id
            )
            result = await session.execute(stmt)
            shipments = list(result.scalars().all())
            for s in shipments:
                session.expunge(s)
            return shipments
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_contrib_sqlalchemy_repository.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add src/litestar_sendparcel/contrib/sqlalchemy/repository.py tests/test_contrib_sqlalchemy_repository.py
git commit -m "feat: add SQLAlchemy shipment repository"
```

---

### Task 9: Expand CallbackRetryStore protocol to 5 methods

**Files:**
- Modify: `src/litestar_sendparcel/protocols.py`
- Test: `tests/test_protocols.py`

**Step 1: Write the test**

```python
# tests/test_protocols.py
"""Tests for protocol definitions."""

from litestar_sendparcel.protocols import CallbackRetryStore


def test_callback_retry_store_has_all_methods():
    """CallbackRetryStore protocol defines the full lifecycle."""
    method_names = [
        "store_failed_callback",
        "get_due_retries",
        "mark_succeeded",
        "mark_failed",
        "mark_exhausted",
    ]
    for method_name in method_names:
        assert hasattr(CallbackRetryStore, method_name), (
            f"CallbackRetryStore missing method: {method_name}"
        )


def test_callback_retry_store_is_runtime_checkable():
    """CallbackRetryStore can be used with isinstance()."""

    class GoodStore:
        async def store_failed_callback(
            self,
            shipment_id: str,
            provider_slug: str,
            payload: dict,
            headers: dict,
        ) -> str:
            return "id"

        async def get_due_retries(
            self, limit: int = 10
        ) -> list[dict]:
            return []

        async def mark_succeeded(self, retry_id: str) -> None:
            pass

        async def mark_failed(
            self, retry_id: str, error: str
        ) -> None:
            pass

        async def mark_exhausted(self, retry_id: str) -> None:
            pass

    assert isinstance(GoodStore(), CallbackRetryStore)
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: FAIL — `store_failed_callback` not in protocol, or isinstance check fails

**Step 3: Update the protocol**

Replace the entire `src/litestar_sendparcel/protocols.py`:

```python
"""Litestar adapter protocol extensions."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from sendparcel.protocols import Order

__all__ = [
    "CallbackRetryStore",
    "Order",
    "OrderResolver",
]


@runtime_checkable
class OrderResolver(Protocol):
    """Resolves order IDs to core Order objects."""

    async def resolve(self, order_id: str) -> Order: ...


@runtime_checkable
class CallbackRetryStore(Protocol):
    """Storage abstraction for the webhook retry queue.

    Full lifecycle: store -> get_due -> mark_succeeded/mark_failed/mark_exhausted.
    """

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict,
        headers: dict,
    ) -> str:
        """Store a failed callback for later retry. Returns retry ID."""
        ...

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        """Get retries that are due for processing."""
        ...

    async def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry as successfully processed."""
        ...

    async def mark_failed(self, retry_id: str, error: str) -> None:
        """Mark a retry as failed and schedule next attempt."""
        ...

    async def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry as exhausted (dead letter)."""
        ...
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: 2 passed

**Step 5: Run full suite to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: all passed (existing code still uses `store.enqueue()` which is fine — the old InMemoryRetryStore in conftest still works for route tests)

**Step 6: Commit**

```bash
git add src/litestar_sendparcel/protocols.py tests/test_protocols.py
git commit -m "feat: expand CallbackRetryStore protocol to full 5-method lifecycle"
```

---

### Task 10: Implement exponential backoff in retry.py

**Files:**
- Modify: `src/litestar_sendparcel/retry.py`
- Test: `tests/test_retry.py`

**Step 1: Write the test**

```python
# tests/test_retry.py
"""Tests for the webhook retry mechanism."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from litestar_sendparcel.config import SendparcelConfig


@pytest.fixture
def mock_retry_store():
    store = AsyncMock()
    store.get_due_retries = AsyncMock(return_value=[])
    store.mark_succeeded = AsyncMock()
    store.mark_failed = AsyncMock()
    store.mark_exhausted = AsyncMock()
    return store


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def config():
    return SendparcelConfig(
        default_provider="dummy",
        providers={"dummy": {}},
        retry_max_attempts=3,
        retry_backoff_seconds=10,
    )


def test_compute_backoff():
    """Backoff increases exponentially."""
    from litestar_sendparcel.retry import compute_next_retry_at

    base = 10
    t1 = compute_next_retry_at(attempt=1, backoff_seconds=base)
    t2 = compute_next_retry_at(attempt=2, backoff_seconds=base)
    t3 = compute_next_retry_at(attempt=3, backoff_seconds=base)

    now = datetime.now(tz=UTC)
    assert t1 > now
    assert t2 > t1
    assert t3 > t2


def test_compute_backoff_first_attempt():
    """First attempt backoff is base_seconds."""
    from litestar_sendparcel.retry import compute_next_retry_at

    now = datetime.now(tz=UTC)
    result = compute_next_retry_at(attempt=1, backoff_seconds=60)
    expected_min = now + timedelta(seconds=55)
    expected_max = now + timedelta(seconds=65)
    assert expected_min < result < expected_max


async def test_process_retries_empty(mock_retry_store, mock_repo, config):
    """No retries to process — does nothing."""
    from litestar_sendparcel.retry import process_due_retries

    processed = await process_due_retries(
        retry_store=mock_retry_store,
        repository=mock_repo,
        config=config,
    )
    assert processed == 0


async def test_process_retries_success(mock_retry_store, mock_repo, config):
    """Successful retry marks as succeeded."""
    from litestar_sendparcel.retry import process_due_retries

    shipment = AsyncMock()
    shipment.id = "s-1"
    shipment.provider = "dummy"
    mock_repo.get_by_id = AsyncMock(return_value=shipment)

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {"event": "picked_up"},
                "headers": {},
                "attempts": 1,
            }
        ]
    )

    with patch("litestar_sendparcel.retry.ShipmentFlow") as mock_flow_cls:
        instance = AsyncMock()
        mock_flow_cls.return_value = instance
        instance.handle_callback = AsyncMock()

        processed = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repo,
            config=config,
        )

    assert processed == 1
    mock_retry_store.mark_succeeded.assert_called_once_with("retry-1")


async def test_process_retries_failure_under_max(
    mock_retry_store, mock_repo, config
):
    """Failed retry under max_attempts marks as failed."""
    from litestar_sendparcel.retry import process_due_retries

    shipment = AsyncMock()
    shipment.id = "s-1"
    shipment.provider = "dummy"
    mock_repo.get_by_id = AsyncMock(return_value=shipment)

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {"event": "picked_up"},
                "headers": {},
                "attempts": 1,
            }
        ]
    )

    with patch("litestar_sendparcel.retry.ShipmentFlow") as mock_flow_cls:
        instance = AsyncMock()
        mock_flow_cls.return_value = instance
        instance.handle_callback = AsyncMock(
            side_effect=Exception("still failing")
        )

        processed = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repo,
            config=config,
        )

    assert processed == 1
    mock_retry_store.mark_failed.assert_called_once()


async def test_process_retries_exhausted(mock_retry_store, mock_repo, config):
    """Failed retry at max_attempts marks as exhausted."""
    from litestar_sendparcel.retry import process_due_retries

    shipment = AsyncMock()
    shipment.id = "s-1"
    shipment.provider = "dummy"
    mock_repo.get_by_id = AsyncMock(return_value=shipment)

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {"event": "picked_up"},
                "headers": {},
                "attempts": 3,
            }
        ]
    )

    with patch("litestar_sendparcel.retry.ShipmentFlow") as mock_flow_cls:
        instance = AsyncMock()
        mock_flow_cls.return_value = instance
        instance.handle_callback = AsyncMock(
            side_effect=Exception("still failing")
        )

        processed = await process_due_retries(
            retry_store=mock_retry_store,
            repository=mock_repo,
            config=config,
        )

    assert processed == 1
    mock_retry_store.mark_exhausted.assert_called_once_with("retry-1")


async def test_process_retries_shipment_not_found(
    mock_retry_store, mock_repo, config
):
    """Retry for missing shipment is marked exhausted."""
    from litestar_sendparcel.retry import process_due_retries

    mock_repo.get_by_id = AsyncMock(side_effect=KeyError("s-1"))

    mock_retry_store.get_due_retries = AsyncMock(
        return_value=[
            {
                "id": "retry-1",
                "shipment_id": "s-1",
                "provider_slug": "dummy",
                "payload": {},
                "headers": {},
                "attempts": 1,
            }
        ]
    )

    processed = await process_due_retries(
        retry_store=mock_retry_store,
        repository=mock_repo,
        config=config,
    )

    assert processed == 1
    mock_retry_store.mark_exhausted.assert_called_once_with("retry-1")
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_retry.py -v`
Expected: FAIL — `ImportError: cannot import name 'compute_next_retry_at'`

**Step 3: Rewrite retry.py with full lifecycle**

Replace the entire `src/litestar_sendparcel/retry.py`:

```python
"""Webhook retry mechanism with exponential backoff."""

import logging
from datetime import UTC, datetime, timedelta

from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.protocols import CallbackRetryStore

logger = logging.getLogger(__name__)


def compute_next_retry_at(
    attempt: int,
    backoff_seconds: int,
) -> datetime:
    """Compute the next retry time with exponential backoff.

    delay = backoff_seconds * 2^(attempt - 1)
    """
    delay = backoff_seconds * (2 ** (attempt - 1))
    return datetime.now(tz=UTC) + timedelta(seconds=delay)


async def enqueue_callback_retry(
    store: CallbackRetryStore | None,
    *,
    provider_slug: str,
    shipment_id: str,
    payload: dict,
    headers: dict[str, str],
    reason: str,
) -> None:
    """Persist callback retry payload when a retry store is configured."""
    if store is None:
        return

    await store.store_failed_callback(
        shipment_id=shipment_id,
        provider_slug=provider_slug,
        payload=payload,
        headers=headers,
    )
    logger.warning(
        "Callback for shipment %s failed, queued for retry: %s",
        shipment_id,
        reason,
    )


async def process_due_retries(
    *,
    retry_store: CallbackRetryStore,
    repository: ShipmentRepository,
    config: SendparcelConfig,
    limit: int = 10,
) -> int:
    """Process all due callback retries.

    Returns the number of retries processed.
    """
    retries = await retry_store.get_due_retries(limit=limit)
    processed = 0

    for retry in retries:
        retry_id = retry["id"]
        shipment_id = retry["shipment_id"]
        payload = retry["payload"]
        headers = retry["headers"]
        attempts = retry["attempts"]

        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError:
            logger.error(
                "Retry %s: shipment %s not found, marking exhausted",
                retry_id,
                shipment_id,
            )
            await retry_store.mark_exhausted(retry_id)
            processed += 1
            continue

        flow = ShipmentFlow(
            repository=repository,
            config=config.providers,
        )

        try:
            await flow.handle_callback(
                shipment,
                payload,
                headers,
            )
            await retry_store.mark_succeeded(retry_id)
            logger.info(
                "Retry %s: callback for shipment %s succeeded",
                retry_id,
                shipment_id,
            )
        except Exception as exc:
            if attempts >= config.retry_max_attempts:
                await retry_store.mark_exhausted(retry_id)
                logger.warning(
                    "Retry %s: exhausted after %d attempts: %s",
                    retry_id,
                    attempts,
                    exc,
                )
            else:
                await retry_store.mark_failed(
                    retry_id,
                    error=str(exc),
                )
                logger.info(
                    "Retry %s: attempt %d failed: %s",
                    retry_id,
                    attempts,
                    exc,
                )

        processed += 1

    return processed
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_retry.py -v`
Expected: 6 passed

**Step 5: Update conftest.py RetryStore to also support store_failed_callback**

The existing `RetryStore` in `tests/conftest.py` has only `enqueue()`. Update it to also provide `store_failed_callback()` so both old and new call patterns work:

```python
# In tests/conftest.py, replace the RetryStore class:

class RetryStore:
    def __init__(self) -> None:
        self.events: list[dict] = []
        self._counter = 0

    async def enqueue(self, payload: dict) -> None:
        self.events.append(payload)

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict,
        headers: dict,
    ) -> str:
        self._counter += 1
        retry_id = f"retry-{self._counter}"
        self.events.append(
            {
                "id": retry_id,
                "shipment_id": shipment_id,
                "provider_slug": provider_slug,
                "payload": payload,
                "headers": headers,
                "reason": "stored",
            }
        )
        return retry_id

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        return []

    async def mark_succeeded(self, retry_id: str) -> None:
        pass

    async def mark_failed(self, retry_id: str, error: str) -> None:
        pass

    async def mark_exhausted(self, retry_id: str) -> None:
        pass
```

**Step 6: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 7: Commit**

```bash
git add src/litestar_sendparcel/retry.py tests/test_retry.py tests/conftest.py
git commit -m "feat: implement exponential backoff and process_due_retries"
```

---

### Task 11: Create contrib/sqlalchemy/ retry store

**Files:**
- Create: `src/litestar_sendparcel/contrib/sqlalchemy/retry_store.py`
- Test: `tests/test_contrib_sqlalchemy_retry_store.py`

**Step 1: Write the test**

```python
# tests/test_contrib_sqlalchemy_retry_store.py
"""Tests for SQLAlchemy retry store implementation."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from litestar_sendparcel.contrib.sqlalchemy.models import (
    Base,
    CallbackRetryModel,
)
from litestar_sendparcel.contrib.sqlalchemy.retry_store import (
    SQLAlchemyRetryStore,
)


@pytest.fixture
async def engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession)


@pytest.fixture
def store(session_factory):
    return SQLAlchemyRetryStore(
        session_factory=session_factory,
        backoff_seconds=10,
    )


async def test_store_failed_callback(store):
    """Stores a failed callback and returns an ID."""
    retry_id = await store.store_failed_callback(
        shipment_id="s-1",
        provider_slug="dummy",
        payload={"event": "picked_up"},
        headers={"content-type": "application/json"},
    )
    assert retry_id is not None
    assert isinstance(retry_id, str)


async def test_get_due_retries_empty(store):
    """No retries when store is empty."""
    retries = await store.get_due_retries()
    assert retries == []


async def test_get_due_retries_finds_due(store, session_factory):
    """Finds retries that are past their next_retry_at."""
    async with session_factory() as session:
        retry = CallbackRetryModel(
            shipment_id="s-1",
            provider_slug="dummy",
            payload={"event": "picked_up"},
            headers={},
            attempts=1,
            next_retry_at=datetime.now(tz=UTC) - timedelta(minutes=1),
            status="pending",
        )
        session.add(retry)
        await session.commit()

    retries = await store.get_due_retries()
    assert len(retries) == 1
    assert retries[0]["shipment_id"] == "s-1"
    assert retries[0]["provider_slug"] == "dummy"


async def test_get_due_retries_skips_future(store, session_factory):
    """Skips retries that aren't due yet."""
    async with session_factory() as session:
        retry = CallbackRetryModel(
            shipment_id="s-1",
            provider_slug="dummy",
            payload={"event": "picked_up"},
            headers={},
            attempts=1,
            next_retry_at=datetime.now(tz=UTC) + timedelta(hours=1),
            status="pending",
        )
        session.add(retry)
        await session.commit()

    retries = await store.get_due_retries()
    assert retries == []


async def test_mark_succeeded(store, session_factory):
    """Marks a retry as succeeded."""
    retry_id = await store.store_failed_callback(
        shipment_id="s-1",
        provider_slug="dummy",
        payload={},
        headers={},
    )
    await store.mark_succeeded(retry_id)

    async with session_factory() as session:
        retry = await session.get(CallbackRetryModel, retry_id)
        assert retry is not None
        assert retry.status == "succeeded"


async def test_mark_failed(store, session_factory):
    """Marks a retry as failed with error and increments attempts."""
    retry_id = await store.store_failed_callback(
        shipment_id="s-1",
        provider_slug="dummy",
        payload={},
        headers={},
    )
    await store.mark_failed(retry_id, error="Connection timeout")

    async with session_factory() as session:
        retry = await session.get(CallbackRetryModel, retry_id)
        assert retry is not None
        assert retry.status == "pending"
        assert retry.attempts == 1
        assert retry.last_error == "Connection timeout"
        assert retry.next_retry_at is not None


async def test_mark_exhausted(store, session_factory):
    """Marks a retry as exhausted (dead letter)."""
    retry_id = await store.store_failed_callback(
        shipment_id="s-1",
        provider_slug="dummy",
        payload={},
        headers={},
    )
    await store.mark_exhausted(retry_id)

    async with session_factory() as session:
        retry = await session.get(CallbackRetryModel, retry_id)
        assert retry is not None
        assert retry.status == "exhausted"
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_contrib_sqlalchemy_retry_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'litestar_sendparcel.contrib.sqlalchemy.retry_store'`

**Step 3: Write the implementation**

```python
# src/litestar_sendparcel/contrib/sqlalchemy/retry_store.py
"""SQLAlchemy-backed retry store for webhook callbacks."""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from litestar_sendparcel.contrib.sqlalchemy.models import CallbackRetryModel
from litestar_sendparcel.retry import compute_next_retry_at


class SQLAlchemyRetryStore:
    """Callback retry store backed by SQLAlchemy.

    Implements the CallbackRetryStore protocol.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        backoff_seconds: int = 60,
    ) -> None:
        self._session_factory = session_factory
        self._backoff_seconds = backoff_seconds

    async def store_failed_callback(
        self,
        shipment_id: str,
        provider_slug: str,
        payload: dict,
        headers: dict,
    ) -> str:
        """Store a failed callback for later retry."""
        async with self._session_factory() as session:
            retry = CallbackRetryModel(
                shipment_id=shipment_id,
                provider_slug=provider_slug,
                payload=payload,
                headers=headers,
                attempts=0,
                next_retry_at=compute_next_retry_at(
                    attempt=1,
                    backoff_seconds=self._backoff_seconds,
                ),
                status="pending",
            )
            session.add(retry)
            await session.commit()
            await session.refresh(retry)
            return retry.id

    async def get_due_retries(self, limit: int = 10) -> list[dict]:
        """Get retries that are due for processing."""
        now = datetime.now(tz=UTC)
        async with self._session_factory() as session:
            stmt = (
                select(CallbackRetryModel)
                .where(CallbackRetryModel.status == "pending")
                .where(CallbackRetryModel.next_retry_at <= now)
                .order_by(CallbackRetryModel.next_retry_at.asc())
                .limit(limit)
            )
            result = await session.execute(stmt)
            retries = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "shipment_id": r.shipment_id,
                    "provider_slug": r.provider_slug,
                    "payload": r.payload,
                    "headers": r.headers,
                    "attempts": r.attempts,
                }
                for r in retries
            ]

    async def mark_succeeded(self, retry_id: str) -> None:
        """Mark a retry as successfully processed."""
        async with self._session_factory() as session:
            retry = await session.get(CallbackRetryModel, retry_id)
            if retry is not None:
                retry.status = "succeeded"
                await session.commit()

    async def mark_failed(self, retry_id: str, error: str) -> None:
        """Mark a retry as failed and schedule next attempt."""
        async with self._session_factory() as session:
            retry = await session.get(CallbackRetryModel, retry_id)
            if retry is not None:
                retry.attempts += 1
                retry.last_error = error
                retry.next_retry_at = compute_next_retry_at(
                    attempt=retry.attempts + 1,
                    backoff_seconds=self._backoff_seconds,
                )
                retry.status = "pending"
                await session.commit()

    async def mark_exhausted(self, retry_id: str) -> None:
        """Mark a retry as exhausted (dead letter)."""
        async with self._session_factory() as session:
            retry = await session.get(CallbackRetryModel, retry_id)
            if retry is not None:
                retry.status = "exhausted"
                await session.commit()
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_contrib_sqlalchemy_retry_store.py -v`
Expected: 7 passed

**Step 5: Commit**

```bash
git add src/litestar_sendparcel/contrib/sqlalchemy/retry_store.py tests/test_contrib_sqlalchemy_retry_store.py
git commit -m "feat: add SQLAlchemy retry store with full lifecycle"
```

---

### Task 12: Expand config with retry settings and env_prefix

**Files:**
- Modify: `src/litestar_sendparcel/config.py`
- Test: `tests/test_config.py`

**Step 1: Write the test**

```python
# tests/test_config.py
"""Tests for SendparcelConfig."""

from litestar_sendparcel.config import SendparcelConfig


def test_config_defaults():
    """Config has retry defaults."""
    config = SendparcelConfig(default_provider="dummy")
    assert config.retry_max_attempts == 5
    assert config.retry_backoff_seconds == 60
    assert config.retry_enabled is True
    assert config.providers == {}


def test_config_custom_retry():
    """Config accepts custom retry settings."""
    config = SendparcelConfig(
        default_provider="inpost",
        retry_max_attempts=3,
        retry_backoff_seconds=30,
        retry_enabled=False,
    )
    assert config.retry_max_attempts == 3
    assert config.retry_backoff_seconds == 30
    assert config.retry_enabled is False


def test_config_env_prefix(monkeypatch):
    """Config reads from SENDPARCEL_ env vars."""
    monkeypatch.setenv("SENDPARCEL_DEFAULT_PROVIDER", "inpost")
    monkeypatch.setenv("SENDPARCEL_RETRY_MAX_ATTEMPTS", "10")
    config = SendparcelConfig()
    assert config.default_provider == "inpost"
    assert config.retry_max_attempts == 10
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `retry_max_attempts` attribute missing, or env_prefix not configured

**Step 3: Update config.py**

```python
# src/litestar_sendparcel/config.py
"""Litestar adapter configuration."""

from __future__ import annotations

from typing import Any

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SendparcelConfig(BaseSettings):
    """Runtime config for Litestar adapter.

    Reads from environment variables with SENDPARCEL_ prefix.
    """

    model_config = SettingsConfigDict(env_prefix="SENDPARCEL_")

    default_provider: str
    providers: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Retry settings
    retry_max_attempts: int = 5
    retry_backoff_seconds: int = 60
    retry_enabled: bool = True
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: 3 passed

**Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 6: Commit**

```bash
git add src/litestar_sendparcel/config.py tests/test_config.py
git commit -m "feat: add retry settings and SENDPARCEL_ env prefix to config"
```

---

### Task 13: Convert handlers to Controller classes

**Files:**
- Modify: `src/litestar_sendparcel/routes/shipments.py`
- Modify: `src/litestar_sendparcel/routes/callbacks.py`
- Modify: `src/litestar_sendparcel/plugin.py`
- Test: existing tests must still pass + `tests/test_controllers.py`

**Step 1: Write tests for controller structure**

```python
# tests/test_controllers.py
"""Tests verifying Controller-based route structure."""

from litestar import Controller

from litestar_sendparcel.routes.callbacks import CallbackController
from litestar_sendparcel.routes.shipments import ShipmentController


def test_shipment_controller_is_controller():
    """ShipmentController extends Litestar Controller."""
    assert issubclass(ShipmentController, Controller)


def test_callback_controller_is_controller():
    """CallbackController extends Litestar Controller."""
    assert issubclass(CallbackController, Controller)


def test_shipment_controller_has_tags():
    """ShipmentController has tags set."""
    assert ShipmentController.tags == ["shipments"]


def test_callback_controller_has_tags():
    """CallbackController has tags set."""
    assert CallbackController.tags == ["callbacks"]
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_controllers.py -v`
Expected: FAIL — `ImportError: cannot import name 'ShipmentController'`

**Step 3: Rewrite routes/shipments.py with Controller**

```python
# src/litestar_sendparcel/routes/shipments.py
"""Shipment endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from litestar import Controller, get, post
from litestar.params import Dependency
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import (
    ConfigurationError,
    ShipmentNotFoundError,
)
from litestar_sendparcel.protocols import OrderResolver
from litestar_sendparcel.schemas import CreateShipmentRequest, ShipmentResponse

logger = logging.getLogger(__name__)


class ShipmentController(Controller):
    """Shipment CRUD endpoints."""

    path = "/shipments"
    tags = ["shipments"]

    @get("/health")
    async def shipments_health(self) -> dict[str, str]:
        """Healthcheck endpoint for shipment routes."""
        return {"status": "ok"}

    @post("/")
    async def create_shipment(
        self,
        data: CreateShipmentRequest,
        config: Annotated[
            SendparcelConfig, Dependency(skip_validation=True)
        ],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
        order_resolver: Annotated[
            OrderResolver | None, Dependency(skip_validation=True)
        ] = None,
    ) -> ShipmentResponse:
        """Create a shipment via ShipmentFlow."""
        if order_resolver is None:
            raise ConfigurationError("Order resolver not configured")

        provider_slug = data.provider or config.default_provider
        order = await order_resolver.resolve(data.order_id)
        flow = ShipmentFlow(
            repository=repository, config=config.providers
        )
        shipment = await flow.create_shipment(order, provider_slug)
        return ShipmentResponse.from_shipment(shipment)

    @post("/{shipment_id:str}/label")
    async def create_label(
        self,
        shipment_id: str,
        config: Annotated[
            SendparcelConfig, Dependency(skip_validation=True)
        ],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
    ) -> ShipmentResponse:
        """Create shipment label via provider."""
        flow = ShipmentFlow(
            repository=repository, config=config.providers
        )
        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError as exc:
            raise ShipmentNotFoundError(shipment_id) from exc
        shipment = await flow.create_label(shipment)
        return ShipmentResponse.from_shipment(shipment)

    @get("/{shipment_id:str}/status")
    async def fetch_status(
        self,
        shipment_id: str,
        config: Annotated[
            SendparcelConfig, Dependency(skip_validation=True)
        ],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
    ) -> ShipmentResponse:
        """Fetch and persist latest provider shipment status."""
        flow = ShipmentFlow(
            repository=repository, config=config.providers
        )
        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError as exc:
            raise ShipmentNotFoundError(shipment_id) from exc
        shipment = await flow.fetch_and_update_status(shipment)
        return ShipmentResponse.from_shipment(shipment)
```

**Step 4: Rewrite routes/callbacks.py with Controller**

```python
# src/litestar_sendparcel/routes/callbacks.py
"""Callback endpoints."""

from __future__ import annotations

import logging
from typing import Annotated

from litestar import Controller, Request, post
from litestar.params import Dependency
from sendparcel.exceptions import CommunicationError, InvalidCallbackError
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import ShipmentNotFoundError
from litestar_sendparcel.protocols import CallbackRetryStore
from litestar_sendparcel.retry import enqueue_callback_retry
from litestar_sendparcel.schemas import CallbackResponse

logger = logging.getLogger(__name__)


class CallbackController(Controller):
    """Provider callback endpoints."""

    tags = ["callbacks"]

    @post("/callbacks/{provider_slug:str}/{shipment_id:str}")
    async def handle_callback(
        self,
        provider_slug: str,
        shipment_id: str,
        request: Request,
        config: Annotated[
            SendparcelConfig, Dependency(skip_validation=True)
        ],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
        retry_store: Annotated[
            CallbackRetryStore | None,
            Dependency(skip_validation=True),
        ] = None,
    ) -> CallbackResponse:
        """Handle provider callback using core flow and retry hooks."""
        flow = ShipmentFlow(
            repository=repository, config=config.providers
        )

        try:
            shipment = await repository.get_by_id(shipment_id)
        except KeyError as exc:
            raise ShipmentNotFoundError(shipment_id) from exc

        if str(shipment.provider) != provider_slug:
            raise InvalidCallbackError("Provider slug mismatch")

        raw_body = await request.body()
        payload = await request.json()
        headers = dict(request.headers)

        try:
            updated = await flow.handle_callback(
                shipment,
                payload,
                headers,
                raw_body=raw_body,
            )
        except InvalidCallbackError:
            raise
        except CommunicationError as exc:
            await enqueue_callback_retry(
                retry_store,
                provider_slug=provider_slug,
                shipment_id=shipment_id,
                payload=payload,
                headers=headers,
                reason=str(exc),
            )
            raise

        return CallbackResponse(
            provider=provider_slug,
            status="accepted",
            shipment_status=str(updated.status),
        )
```

**Step 5: Update plugin.py to use Controllers**

```python
# src/litestar_sendparcel/plugin.py
"""Router/plugin factory for litestar-sendparcel."""

from __future__ import annotations

from litestar import Router
from litestar.di import Provide
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.exceptions import EXCEPTION_HANDLERS
from litestar_sendparcel.protocols import CallbackRetryStore, OrderResolver
from litestar_sendparcel.registry import LitestarPluginRegistry
from litestar_sendparcel.routes.callbacks import CallbackController
from litestar_sendparcel.routes.shipments import ShipmentController


def create_shipping_router(
    *,
    config: SendparcelConfig,
    repository: ShipmentRepository,
    registry: LitestarPluginRegistry | None = None,
    order_resolver: OrderResolver | None = None,
    retry_store: CallbackRetryStore | None = None,
) -> Router:
    """Create a configured Litestar router.

    Args:
        config: Shipping configuration.
        repository: Shipment persistence backend.
        registry: Plugin registry. Creates a new one if not provided.
        order_resolver: Resolves order IDs to Order objects.
        retry_store: Storage for webhook retry queue.

    Returns:
        A Litestar Router with all shipping endpoints.
    """
    actual_registry = registry or LitestarPluginRegistry()
    actual_registry.discover()

    return Router(
        path="/",
        route_handlers=[
            ShipmentController,
            CallbackController,
        ],
        dependencies={
            "config": Provide(lambda: config, sync_to_thread=False),
            "repository": Provide(
                lambda: repository, sync_to_thread=False
            ),
            "registry": Provide(
                lambda: actual_registry,
                sync_to_thread=False,
            ),
            "order_resolver": Provide(
                lambda: order_resolver,
                sync_to_thread=False,
            ),
            "retry_store": Provide(
                lambda: retry_store, sync_to_thread=False
            ),
        },
        exception_handlers=EXCEPTION_HANDLERS,
    )
```

**Step 6: Update test_routes_shipments.py for Controller**

The old test referenced `shipments_health` function directly. Update it:

```python
# tests/test_routes_shipments.py
"""Shipment route tests."""

from litestar import Controller

from litestar_sendparcel.routes.shipments import ShipmentController


def test_shipment_controller_is_controller() -> None:
    assert issubclass(ShipmentController, Controller)


def test_shipment_controller_path() -> None:
    assert ShipmentController.path == "/shipments"
```

**Step 7: Update test_routes_flow.py**

The existing flow tests use routes like `POST /shipments` — with the Controller having `path = "/shipments"` and `@post("/")`, the full URL stays `/shipments`. The callback route is `POST /callbacks/{slug}/{id}` with no path prefix on CallbackController. The healthcheck becomes `GET /shipments/health`. All URLs remain the same.

Verify by reviewing: ShipmentController has `path = "/shipments"` with sub-routes `"/health"`, `"/"`, `"/{id}/label"`, `"/{id}/status"`. CallbackController has no `path` prefix and sub-route `"/callbacks/{slug}/{id}"`. These match the existing URLs.

**Step 8: Run tests**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 9: Commit**

```bash
git add src/litestar_sendparcel/routes/shipments.py src/litestar_sendparcel/routes/callbacks.py src/litestar_sendparcel/plugin.py tests/test_controllers.py tests/test_routes_shipments.py
git commit -m "refactor: convert standalone handlers to Controller classes"
```

---

### Task 14: Add dependencies.py module

**Files:**
- Create: `src/litestar_sendparcel/dependencies.py`
- Test: `tests/test_dependencies.py`

**Context:** This is a placeholder module (matching litestar-getpaid). Controllers construct `ShipmentFlow` directly, so no shared providers are needed yet. But having the module ensures the package structure is complete.

**Step 1: Write the test**

```python
# tests/test_dependencies.py
"""Tests for dependencies module."""


def test_dependencies_module_importable():
    """Dependencies module is importable."""
    import litestar_sendparcel.dependencies  # noqa: F401
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dependencies.py -v`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Create the module**

```python
# src/litestar_sendparcel/dependencies.py
"""Dependency providers for litestar-sendparcel.

This module is a placeholder for future shared dependency providers.
Controllers currently construct ShipmentFlow directly, so no providers
are needed at this time.
"""
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_dependencies.py -v`
Expected: 1 passed

**Step 5: Commit**

```bash
git add src/litestar_sendparcel/dependencies.py tests/test_dependencies.py
git commit -m "chore: add dependencies.py placeholder module"
```

---

### Task 15: Update __init__.py with lazy imports and full public API

**Files:**
- Modify: `src/litestar_sendparcel/__init__.py`
- Test: `tests/test_public_api.py` (extend)

**Step 1: Update the test**

Replace `tests/test_public_api.py`:

```python
# tests/test_public_api.py
"""Tests for public API surface."""

from pathlib import Path

import litestar_sendparcel


def test_version_is_set():
    """Package exposes __version__."""
    assert hasattr(litestar_sendparcel, "__version__")
    assert litestar_sendparcel.__version__ == "0.1.0"


def test_py_typed_marker_exists():
    """PEP 561 py.typed marker file exists."""
    marker = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "litestar_sendparcel"
        / "py.typed"
    )
    assert marker.exists()


def test_all_exports_are_importable():
    """Every name in __all__ is importable."""
    for name in litestar_sendparcel.__all__:
        attr = getattr(litestar_sendparcel, name)
        assert attr is not None, f"{name} resolved to None"


def test_lazy_import_config():
    """SendparcelConfig is lazily importable."""
    cls = litestar_sendparcel.SendparcelConfig
    assert cls.__name__ == "SendparcelConfig"


def test_lazy_import_router_factory():
    """create_shipping_router is lazily importable."""
    fn = litestar_sendparcel.create_shipping_router
    assert callable(fn)


def test_lazy_import_exceptions():
    """Exception classes are lazily importable."""
    assert litestar_sendparcel.ShipmentNotFoundError is not None
    assert litestar_sendparcel.ConfigurationError is not None


def test_lazy_import_protocols():
    """Protocol classes are lazily importable."""
    assert litestar_sendparcel.OrderResolver is not None
    assert litestar_sendparcel.CallbackRetryStore is not None


def test_lazy_import_schemas():
    """Schema classes are lazily importable."""
    assert litestar_sendparcel.CreateShipmentRequest is not None
    assert litestar_sendparcel.ShipmentResponse is not None
    assert litestar_sendparcel.CallbackResponse is not None


def test_getattr_raises_for_unknown():
    """Unknown attribute raises AttributeError."""
    import pytest

    with pytest.raises(AttributeError, match="no_such_attribute"):
        litestar_sendparcel.no_such_attribute
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: FAIL — missing lazy imports, missing names in `__all__`

**Step 3: Rewrite __init__.py with lazy imports**

```python
# src/litestar_sendparcel/__init__.py
"""Litestar framework adapter for sendparcel shipping processing."""

from typing import TYPE_CHECKING

__version__ = "0.1.0"

__all__ = [
    "CallbackResponse",
    "CallbackRetryStore",
    "ConfigurationError",
    "CreateShipmentRequest",
    "LitestarPluginRegistry",
    "OrderResolver",
    "SendparcelConfig",
    "ShipmentNotFoundError",
    "ShipmentResponse",
    "__version__",
    "create_shipping_router",
]

if TYPE_CHECKING:
    from litestar_sendparcel.config import SendparcelConfig
    from litestar_sendparcel.exceptions import (
        ConfigurationError,
        ShipmentNotFoundError,
    )
    from litestar_sendparcel.plugin import create_shipping_router
    from litestar_sendparcel.protocols import (
        CallbackRetryStore,
        OrderResolver,
    )
    from litestar_sendparcel.registry import LitestarPluginRegistry
    from litestar_sendparcel.schemas import (
        CallbackResponse,
        CreateShipmentRequest,
        ShipmentResponse,
    )


def __getattr__(name: str):
    # Lazy imports to avoid loading all submodules on package import.
    if name == "SendparcelConfig":
        from litestar_sendparcel.config import SendparcelConfig

        return SendparcelConfig
    if name == "create_shipping_router":
        from litestar_sendparcel.plugin import create_shipping_router

        return create_shipping_router
    if name == "LitestarPluginRegistry":
        from litestar_sendparcel.registry import LitestarPluginRegistry

        return LitestarPluginRegistry
    if name == "ShipmentNotFoundError":
        from litestar_sendparcel.exceptions import ShipmentNotFoundError

        return ShipmentNotFoundError
    if name == "ConfigurationError":
        from litestar_sendparcel.exceptions import ConfigurationError

        return ConfigurationError
    if name in ("OrderResolver", "CallbackRetryStore"):
        from litestar_sendparcel import protocols

        return getattr(protocols, name)
    if name in (
        "CreateShipmentRequest",
        "ShipmentResponse",
        "CallbackResponse",
    ):
        from litestar_sendparcel import schemas

        return getattr(schemas, name)
    raise AttributeError(
        f"module 'litestar_sendparcel' has no attribute {name!r}"
    )
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: all passed

**Step 5: Run full suite**

Run: `uv run pytest tests/ -v`
Expected: all passed

**Step 6: Commit**

```bash
git add src/litestar_sendparcel/__init__.py tests/test_public_api.py
git commit -m "feat: add lazy imports and expanded public API to __init__.py"
```

---

### Task 16: Final verification

**Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: all tests pass

**Step 2: Run ruff linter**

Run: `uv run ruff check src/ tests/`
Expected: no errors

**Step 3: Run ruff formatter**

Run: `uv run ruff format --check src/ tests/`
Expected: all files formatted correctly (or fix if needed)

**Step 4: Verify imports work end-to-end**

Run: `uv run python -c "from litestar_sendparcel import SendparcelConfig, create_shipping_router, ShipmentNotFoundError, ConfigurationError, CallbackRetryStore, OrderResolver; print('All imports OK')"`
Expected: `All imports OK`

Run: `uv run python -c "from litestar_sendparcel.contrib.sqlalchemy.models import Base, ShipmentModel, CallbackRetryModel; from litestar_sendparcel.contrib.sqlalchemy.repository import SQLAlchemyShipmentRepository; from litestar_sendparcel.contrib.sqlalchemy.retry_store import SQLAlchemyRetryStore; print('SQLAlchemy contrib OK')"`
Expected: `SQLAlchemy contrib OK`

**Step 5: Final commit if any formatting fixes were needed**

```bash
git add -A
git commit -m "chore: apply formatting fixes"
```
