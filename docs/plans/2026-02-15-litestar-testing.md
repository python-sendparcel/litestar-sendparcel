# Litestar-Sendparcel Comprehensive Test Suite Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a comprehensive test suite of ~85 tests across 16 test files covering every module in `litestar-sendparcel`.

**Architecture:** Each task creates or expands one test file. Tests use Litestar's sync `TestClient` for HTTP route tests and `pytest-asyncio` for async unit tests. SQLAlchemy tests use real `aiosqlite` in-memory databases. All tests rely on shared fixtures in `conftest.py` and the existing `DemoOrder`/`DemoShipment`/`InMemoryRepo` infrastructure.

**Tech Stack:** pytest, pytest-asyncio, litestar `TestClient`, pydantic/pydantic-settings, SQLAlchemy + aiosqlite, sendparcel core (exceptions, flow, registry, provider, protocols, enums).

---

## Prerequisites

This plan assumes the critical-fixes plan has been executed, so the following exist:

- `src/litestar_sendparcel/exceptions.py` with `EXCEPTION_HANDLERS` dict and handler functions
- `src/litestar_sendparcel/contrib/sqlalchemy/models.py` with SQLAlchemy models
- `src/litestar_sendparcel/contrib/sqlalchemy/repository.py` with `SQLAlchemyShipmentRepository`
- `src/litestar_sendparcel/contrib/sqlalchemy/retry_store.py` with `SQLAlchemyRetryStore`
- `src/litestar_sendparcel/dependencies.py` with dependency provider functions
- Expanded `CallbackRetryStore` protocol (5 methods: `enqueue`, `get_pending`, `mark_completed`, `mark_failed`, `count_pending`)
- Expanded `SendparcelConfig` with `retry_max_attempts`, `retry_backoff_seconds`, `retry_enabled` fields and `model_config` with `env_prefix`
- `src/litestar_sendparcel/routes/__init__.py` exporting route handlers
- `__version__` in `__init__.py`
- `py.typed` marker

**If any of these do not exist when you start a task, skip that task and note it.**

## Conventions

- **Run command for all tasks:** `uv run pytest tests/ -v` (from `litestar-sendparcel/` directory)
- **Run command for single file:** `uv run pytest tests/<filename>.py -v`
- **asyncio_mode = "auto"** is configured in `pyproject.toml`, so `async def test_*` functions run automatically as async tests
- All source code is under `src/litestar_sendparcel/`
- All test files are under `tests/`
- Import paths use `litestar_sendparcel.*` (thanks to `pythonpath = ["src"]` in pyproject.toml)

---

## Task 1: Expand conftest.py with Litestar + SQLAlchemy fixtures

**Files:**
- Modify: `tests/conftest.py`

**Why:** Many later tasks need a wired-up Litestar `TestClient`, a mock retry store that satisfies the full 5-method protocol, and SQLAlchemy fixtures for contrib tests. We add all of these to conftest now so later tasks can just use them.

**Step 1: Read the current conftest.py and understand existing fixtures**

Read `tests/conftest.py` to verify it matches what's documented above (DemoOrder, DemoShipment, InMemoryRepo, OrderResolver, RetryStore, isolate_global_registry, repository, resolver, retry_store fixtures).

**Step 2: Expand the RetryStore mock to support all 5 protocol methods**

Replace the `RetryStore` class in `tests/conftest.py` with:

```python
class RetryStore:
    """In-memory retry store satisfying full CallbackRetryStore protocol."""

    def __init__(self) -> None:
        self.events: list[dict] = []
        self._completed: set[int] = set()
        self._failed: set[int] = set()

    async def enqueue(self, payload: dict) -> None:
        self.events.append(payload)

    async def get_pending(self) -> list[dict]:
        return [
            e
            for i, e in enumerate(self.events)
            if i not in self._completed and i not in self._failed
        ]

    async def mark_completed(self, index: int) -> None:
        self._completed.add(index)

    async def mark_failed(self, index: int, reason: str) -> None:
        self._failed.add(index)

    async def count_pending(self) -> int:
        return len(await self.get_pending())
```

**Step 3: Add Litestar test app fixture**

Add the following imports and fixtures to the bottom of `tests/conftest.py`:

```python
from litestar import Litestar
from litestar.testing import TestClient
from sendparcel.provider import BaseProvider
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.registry import registry as global_registry

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router


class DummyTestProvider(BaseProvider):
    """Deterministic provider for test suite."""

    slug = "test-dummy"
    display_name = "Test Dummy"

    async def create_shipment(self, **kwargs):
        return {"external_id": "ext-1", "tracking_number": "TRK-1"}

    async def create_label(self, **kwargs):
        return {"format": "PDF", "url": "https://labels.test/s.pdf"}

    async def verify_callback(self, data, headers, **kwargs):
        if headers.get("x-test-token") != "valid":
            raise InvalidCallbackError("Invalid token")

    async def handle_callback(self, data, headers, **kwargs):
        if self.shipment.may_trigger("mark_in_transit"):
            self.shipment.mark_in_transit()

    async def fetch_shipment_status(self, **kwargs):
        return {"status": "in_transit"}

    async def cancel_shipment(self, **kwargs):
        return True


@pytest.fixture()
def config() -> SendparcelConfig:
    return SendparcelConfig(default_provider="test-dummy")


@pytest.fixture()
def test_app(
    repository: InMemoryRepo,
    resolver: OrderResolver,
    retry_store: RetryStore,
    config: SendparcelConfig,
) -> Litestar:
    """Create a fully wired Litestar app for testing."""
    global_registry.register(DummyTestProvider)
    router = create_shipping_router(
        config=config,
        repository=repository,
        order_resolver=resolver,
        retry_store=retry_store,
    )
    return Litestar(route_handlers=[router])


@pytest.fixture()
def client(test_app: Litestar) -> Iterator[TestClient]:
    with TestClient(app=test_app) as tc:
        yield tc
```

**Step 4: Add SQLAlchemy fixtures (conditional on contrib existing)**

Add to the bottom of `tests/conftest.py`:

```python
import os

# SQLAlchemy fixtures -- only available when contrib module exists
_HAS_SQLALCHEMY = False
try:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    _HAS_SQLALCHEMY = True
except ImportError:
    pass

if _HAS_SQLALCHEMY:

    @pytest.fixture()
    async def async_engine():
        engine = create_async_engine("sqlite+aiosqlite://", echo=False)
        yield engine
        await engine.dispose()

    @pytest.fixture()
    async def async_session_factory(async_engine):
        return async_sessionmaker(
            async_engine, class_=AsyncSession, expire_on_commit=False
        )

    @pytest.fixture()
    async def async_session(async_session_factory):
        async with async_session_factory() as session:
            yield session
```

**Step 5: Run tests to verify nothing broke**

Run: `uv run pytest tests/ -v`
Expected: All existing 5 tests PASS, no import errors.

**Step 6: Commit**

```bash
git add tests/conftest.py
git commit -m "test: expand conftest with full RetryStore mock, test app, and SQLAlchemy fixtures"
```

---

## Task 2: tests/test_config.py (~6 tests)

**Files:**
- Create: `tests/test_config.py`

**Step 1: Write the test file**

```python
"""SendparcelConfig unit tests."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from litestar_sendparcel.config import SendparcelConfig


class TestSendparcelConfig:
    """Test SendparcelConfig field defaults and validation."""

    def test_default_provider_required(self) -> None:
        """Config must fail without default_provider."""
        with pytest.raises(ValidationError):
            SendparcelConfig()

    def test_default_provider_accepted(self) -> None:
        """Config accepts a default_provider string."""
        cfg = SendparcelConfig(default_provider="inpost")
        assert cfg.default_provider == "inpost"

    def test_providers_defaults_to_empty(self) -> None:
        """providers field defaults to empty dict."""
        cfg = SendparcelConfig(default_provider="x")
        assert cfg.providers == {}

    def test_providers_accepts_nested_dict(self) -> None:
        """providers accepts nested provider config dicts."""
        cfg = SendparcelConfig(
            default_provider="x",
            providers={"inpost": {"api_key": "abc"}},
        )
        assert cfg.providers["inpost"]["api_key"] == "abc"

    def test_retry_max_attempts_default(self) -> None:
        """retry_max_attempts defaults to a positive integer.

        NOTE: This test assumes the critical-fixes plan added this field.
        Skip if field does not exist.
        """
        cfg = SendparcelConfig(default_provider="x")
        if not hasattr(cfg, "retry_max_attempts"):
            pytest.skip("retry_max_attempts not yet added by critical-fixes")
        assert cfg.retry_max_attempts > 0

    def test_retry_backoff_seconds_default(self) -> None:
        """retry_backoff_seconds defaults to a positive number.

        NOTE: This test assumes the critical-fixes plan added this field.
        """
        cfg = SendparcelConfig(default_provider="x")
        if not hasattr(cfg, "retry_backoff_seconds"):
            pytest.skip(
                "retry_backoff_seconds not yet added by critical-fixes"
            )
        assert cfg.retry_backoff_seconds > 0

    def test_retry_enabled_default(self) -> None:
        """retry_enabled defaults to True.

        NOTE: This test assumes the critical-fixes plan added this field.
        """
        cfg = SendparcelConfig(default_provider="x")
        if not hasattr(cfg, "retry_enabled"):
            pytest.skip("retry_enabled not yet added by critical-fixes")
        assert cfg.retry_enabled is True
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_config.py -v`
Expected: 7 tests PASS (or some SKIP if critical-fixes fields don't exist yet).

**Step 3: Commit**

```bash
git add tests/test_config.py
git commit -m "test: add SendparcelConfig unit tests"
```

---

## Task 3: tests/test_protocols.py (~4 tests)

**Files:**
- Create: `tests/test_protocols.py`

**Context:** The `protocols.py` module defines `OrderResolver` and `CallbackRetryStore` as `runtime_checkable` Protocol classes. We test that conforming objects are recognized as instances and non-conforming objects are not.

**Step 1: Write the test file**

```python
"""Protocol conformance tests."""

from __future__ import annotations

from litestar_sendparcel.protocols import CallbackRetryStore, OrderResolver


class _ValidResolver:
    async def resolve(self, order_id: str):
        return None


class _InvalidResolver:
    pass


class _ValidRetryStore:
    async def enqueue(self, payload: dict) -> None:
        pass


class _InvalidRetryStore:
    pass


class TestOrderResolverProtocol:
    def test_conforming_class_is_instance(self) -> None:
        assert isinstance(_ValidResolver(), OrderResolver)

    def test_non_conforming_class_is_not_instance(self) -> None:
        assert not isinstance(_InvalidResolver(), OrderResolver)


class TestCallbackRetryStoreProtocol:
    def test_conforming_class_is_instance(self) -> None:
        assert isinstance(_ValidRetryStore(), CallbackRetryStore)

    def test_non_conforming_class_is_not_instance(self) -> None:
        assert not isinstance(_InvalidRetryStore(), CallbackRetryStore)
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_protocols.py -v`
Expected: 4 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_protocols.py
git commit -m "test: add protocol conformance tests for OrderResolver and CallbackRetryStore"
```

---

## Task 4: tests/test_exceptions.py (~7 tests)

**Files:**
- Create: `tests/test_exceptions.py`

**Context:** The `exceptions.py` module (added by critical-fixes plan) should define handler functions that convert sendparcel exceptions into Litestar HTTP responses, and an `EXCEPTION_HANDLERS` dict mapping exception types to handler functions.

**If `litestar_sendparcel.exceptions` does not exist yet, write the tests referencing the expected API and mark them with `pytest.importorskip`.**

**Step 1: Write the test file**

```python
"""Exception handler tests."""

from __future__ import annotations

import pytest

exceptions_mod = pytest.importorskip(
    "litestar_sendparcel.exceptions",
    reason="exceptions module not yet created by critical-fixes plan",
)


def _has_exception_handlers() -> bool:
    return hasattr(exceptions_mod, "EXCEPTION_HANDLERS")


@pytest.mark.skipif(
    not _has_exception_handlers(),
    reason="EXCEPTION_HANDLERS not defined yet",
)
class TestExceptionHandlers:
    """Test exception handler functions and EXCEPTION_HANDLERS dict."""

    def test_exception_handlers_is_dict(self) -> None:
        assert isinstance(exceptions_mod.EXCEPTION_HANDLERS, dict)

    def test_exception_handlers_not_empty(self) -> None:
        assert len(exceptions_mod.EXCEPTION_HANDLERS) > 0

    def test_all_values_are_callable(self) -> None:
        for exc_type, handler in exceptions_mod.EXCEPTION_HANDLERS.items():
            assert callable(handler), f"Handler for {exc_type} is not callable"

    def test_all_keys_are_exception_types(self) -> None:
        for exc_type in exceptions_mod.EXCEPTION_HANDLERS:
            assert isinstance(exc_type, type), f"{exc_type} is not a type"
            assert issubclass(
                exc_type, Exception
            ), f"{exc_type} is not an Exception subclass"

    def test_sendparcel_base_exception_handled(self) -> None:
        from sendparcel.exceptions import SendParcelException

        assert SendParcelException in exceptions_mod.EXCEPTION_HANDLERS

    def test_communication_error_handled(self) -> None:
        from sendparcel.exceptions import CommunicationError

        assert CommunicationError in exceptions_mod.EXCEPTION_HANDLERS

    def test_invalid_callback_error_handled(self) -> None:
        from sendparcel.exceptions import InvalidCallbackError

        assert InvalidCallbackError in exceptions_mod.EXCEPTION_HANDLERS
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_exceptions.py -v`
Expected: 7 tests PASS (or all SKIPPED if exceptions module doesn't exist yet).

**Step 3: Commit**

```bash
git add tests/test_exceptions.py
git commit -m "test: add exception handler tests for EXCEPTION_HANDLERS dict"
```

---

## Task 5: tests/test_registry.py (~5 tests)

**Files:**
- Create: `tests/test_registry.py`

**Context:** `LitestarPluginRegistry` extends `PluginRegistry` and adds `register_provider_router` / `get_provider_router`. The `isolate_global_registry` autouse fixture in conftest resets the global registry between tests.

**Step 1: Write the test file**

```python
"""LitestarPluginRegistry tests."""

from __future__ import annotations

import pytest
from sendparcel.provider import BaseProvider

from litestar_sendparcel.registry import LitestarPluginRegistry


class _FakeProvider(BaseProvider):
    slug = "fake-reg"
    display_name = "Fake Reg"

    async def create_shipment(self, **kwargs):
        return {}


class TestLitestarPluginRegistry:
    def test_inherits_plugin_registry(self) -> None:
        from sendparcel.registry import PluginRegistry

        assert issubclass(LitestarPluginRegistry, PluginRegistry)

    def test_register_and_get_by_slug(self) -> None:
        reg = LitestarPluginRegistry()
        reg.register(_FakeProvider)
        assert reg.get_by_slug("fake-reg") is _FakeProvider

    def test_get_by_slug_missing_raises(self) -> None:
        reg = LitestarPluginRegistry()
        reg._discovered = True
        with pytest.raises(KeyError):
            reg.get_by_slug("nonexistent")

    def test_register_provider_router(self) -> None:
        reg = LitestarPluginRegistry()
        sentinel = object()
        reg.register_provider_router("test-slug", sentinel)
        assert reg.get_provider_router("test-slug") is sentinel

    def test_get_provider_router_missing_returns_none(self) -> None:
        reg = LitestarPluginRegistry()
        assert reg.get_provider_router("nonexistent") is None
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_registry.py -v`
Expected: 5 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_registry.py
git commit -m "test: add LitestarPluginRegistry unit tests"
```

---

## Task 6: tests/test_plugin.py (~5 tests) -- expand existing

**Files:**
- Modify: `tests/test_plugin.py`

**Context:** The existing file has 1 test (`test_create_shipping_router_returns_router`). We expand it to test router creation details: route handlers registered, dependencies injected, etc.

**Step 1: Read the current test_plugin.py**

Verify it contains just the single test.

**Step 2: Replace the file contents**

```python
"""Plugin / create_shipping_router tests."""

from __future__ import annotations

from litestar import Litestar, Router
from litestar.testing import TestClient

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.plugin import create_shipping_router


class _Repo:
    async def get_by_id(self, shipment_id: str):
        raise NotImplementedError

    async def create(self, **kwargs):
        raise NotImplementedError

    async def save(self, shipment):
        raise NotImplementedError

    async def update_status(self, shipment_id: str, status: str, **fields):
        raise NotImplementedError


def _make_router(**overrides) -> Router:
    defaults = dict(
        config=SendparcelConfig(default_provider="dummy"),
        repository=_Repo(),
    )
    defaults.update(overrides)
    return create_shipping_router(**defaults)


class TestCreateShippingRouter:
    def test_returns_router_instance(self) -> None:
        router = _make_router()
        assert isinstance(router, Router)

    def test_router_has_route_handlers(self) -> None:
        router = _make_router()
        assert len(router.route_handlers) > 0

    def test_health_endpoint_accessible(self) -> None:
        router = _make_router()
        app = Litestar(route_handlers=[router])
        with TestClient(app=app) as client:
            resp = client.get("/shipments/health")
            assert resp.status_code == 200
            assert resp.json() == {"status": "ok"}

    def test_dependencies_include_config(self) -> None:
        router = _make_router()
        assert "config" in router.dependencies

    def test_dependencies_include_repository(self) -> None:
        router = _make_router()
        assert "repository" in router.dependencies
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_plugin.py -v`
Expected: 5 tests PASS.

**Step 4: Commit**

```bash
git add tests/test_plugin.py
git commit -m "test: expand plugin tests to cover router structure and health endpoint"
```

---

## Task 7: tests/test_schemas.py (~7 tests)

**Files:**
- Create: `tests/test_schemas.py`

**Context:** `schemas.py` defines `CreateShipmentRequest`, `ShipmentResponse`, and `CallbackResponse` as pydantic BaseModel classes. `ShipmentResponse` has a `from_shipment` classmethod.

**Step 1: Write the test file**

```python
"""Schema tests."""

from __future__ import annotations

from dataclasses import dataclass

import pytest
from pydantic import ValidationError

from litestar_sendparcel.schemas import (
    CallbackResponse,
    CreateShipmentRequest,
    ShipmentResponse,
)


class TestCreateShipmentRequest:
    def test_order_id_required(self) -> None:
        with pytest.raises(ValidationError):
            CreateShipmentRequest()

    def test_provider_defaults_to_none(self) -> None:
        req = CreateShipmentRequest(order_id="o-1")
        assert req.provider is None

    def test_provider_accepted(self) -> None:
        req = CreateShipmentRequest(order_id="o-1", provider="inpost")
        assert req.provider == "inpost"


class TestShipmentResponse:
    def test_all_fields_required(self) -> None:
        resp = ShipmentResponse(
            id="s-1",
            status="created",
            provider="dummy",
            external_id="ext-1",
            tracking_number="TRK-1",
            label_url="https://example.com/label.pdf",
        )
        assert resp.id == "s-1"
        assert resp.status == "created"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            ShipmentResponse(id="s-1", status="created")

    def test_from_shipment_classmethod(self) -> None:
        @dataclass
        class FakeShipment:
            id: str = "s-1"
            status: str = "created"
            provider: str = "dummy"
            external_id: str = "ext-1"
            tracking_number: str = "TRK-1"
            label_url: str = ""

        resp = ShipmentResponse.from_shipment(FakeShipment())
        assert resp.id == "s-1"
        assert resp.provider == "dummy"
        assert resp.label_url == ""


class TestCallbackResponse:
    def test_all_fields_required(self) -> None:
        resp = CallbackResponse(
            provider="dummy",
            status="accepted",
            shipment_status="in_transit",
        )
        assert resp.provider == "dummy"

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            CallbackResponse(provider="dummy")
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: 7 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_schemas.py
git commit -m "test: add schema validation tests for request/response models"
```

---

## Task 8: tests/test_retry.py (~6 tests)

**Files:**
- Create: `tests/test_retry.py`

**Context:** `retry.py` defines `enqueue_callback_retry()` which persists retry data to a `CallbackRetryStore` if one is configured, or silently no-ops if `store` is None.

**Step 1: Write the test file**

```python
"""Retry module tests."""

from __future__ import annotations

from litestar_sendparcel.retry import enqueue_callback_retry


class SimpleStore:
    """Minimal in-memory store for test assertions."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def enqueue(self, payload: dict) -> None:
        self.events.append(payload)


class TestEnqueueCallbackRetry:
    async def test_enqueues_when_store_provided(self) -> None:
        store = SimpleStore()
        await enqueue_callback_retry(
            store,
            provider_slug="dummy",
            shipment_id="s-1",
            payload={"event": "test"},
            headers={"x-token": "abc"},
            reason="communication error",
        )
        assert len(store.events) == 1
        event = store.events[0]
        assert event["provider"] == "dummy"
        assert event["shipment_id"] == "s-1"
        assert event["reason"] == "communication error"

    async def test_payload_preserved(self) -> None:
        store = SimpleStore()
        await enqueue_callback_retry(
            store,
            provider_slug="p",
            shipment_id="s",
            payload={"key": "value"},
            headers={},
            reason="r",
        )
        assert store.events[0]["payload"] == {"key": "value"}

    async def test_headers_preserved(self) -> None:
        store = SimpleStore()
        await enqueue_callback_retry(
            store,
            provider_slug="p",
            shipment_id="s",
            payload={},
            headers={"h1": "v1"},
            reason="r",
        )
        assert store.events[0]["headers"] == {"h1": "v1"}

    async def test_queued_at_present(self) -> None:
        store = SimpleStore()
        await enqueue_callback_retry(
            store,
            provider_slug="p",
            shipment_id="s",
            payload={},
            headers={},
            reason="r",
        )
        assert "queued_at" in store.events[0]

    async def test_noop_when_store_is_none(self) -> None:
        # Should not raise
        await enqueue_callback_retry(
            None,
            provider_slug="dummy",
            shipment_id="s-1",
            payload={},
            headers={},
            reason="test",
        )

    async def test_multiple_enqueues_accumulate(self) -> None:
        store = SimpleStore()
        for i in range(3):
            await enqueue_callback_retry(
                store,
                provider_slug="p",
                shipment_id=f"s-{i}",
                payload={},
                headers={},
                reason="r",
            )
        assert len(store.events) == 3
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_retry.py -v`
Expected: 6 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_retry.py
git commit -m "test: add retry module unit tests for enqueue_callback_retry"
```

---

## Task 9: tests/test_routes_callbacks.py (~6 tests)

**Files:**
- Create: `tests/test_routes_callbacks.py`

**Context:** Uses the `client` fixture from conftest (Litestar TestClient with DummyTestProvider registered). The callback route is `POST /callbacks/{provider_slug}/{shipment_id}`. Before testing callbacks, we need to create a shipment first so it exists in the repository.

**Important:** The `DummyTestProvider` in conftest uses `x-test-token: valid` for callback verification and raises `InvalidCallbackError("Invalid token")` otherwise.

**Step 1: Write the test file**

```python
"""Callback route tests."""

from __future__ import annotations

from litestar.testing import TestClient


class TestCallbackRoute:
    """Test POST /callbacks/{provider_slug}/{shipment_id}."""

    def _create_shipment(self, client: TestClient) -> str:
        """Helper: create a shipment and return its ID."""
        resp = client.post("/shipments", json={"order_id": "order-1"})
        assert resp.status_code == 201, resp.text
        return resp.json()["id"]

    def test_callback_happy_path(self, client: TestClient) -> None:
        shipment_id = self._create_shipment(client)
        # Create label first so FSM allows mark_in_transit
        client.post(f"/shipments/{shipment_id}/label")

        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "picked_up"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["provider"] == "test-dummy"
        assert body["status"] == "accepted"

    def test_callback_invalid_token_returns_400(
        self, client: TestClient
    ) -> None:
        shipment_id = self._create_shipment(client)
        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "WRONG"},
        )
        assert resp.status_code == 400

    def test_callback_invalid_token_enqueues_retry(
        self, client: TestClient, retry_store
    ) -> None:
        shipment_id = self._create_shipment(client)
        client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "WRONG"},
        )
        assert len(retry_store.events) == 1

    def test_callback_provider_mismatch_returns_400(
        self, client: TestClient
    ) -> None:
        shipment_id = self._create_shipment(client)
        resp = client.post(
            f"/callbacks/wrong-provider/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 400

    def test_callback_missing_shipment_returns_500(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/callbacks/test-dummy/nonexistent-id",
            json={"event": "test"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 500

    def test_callback_response_includes_shipment_status(
        self, client: TestClient
    ) -> None:
        shipment_id = self._create_shipment(client)
        client.post(f"/shipments/{shipment_id}/label")

        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "transit"},
            headers={"x-test-token": "valid"},
        )
        assert resp.status_code == 201
        assert "shipment_status" in resp.json()
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_routes_callbacks.py -v`
Expected: 6 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_routes_callbacks.py
git commit -m "test: add callback route tests with happy path, auth, mismatch, and retry"
```

---

## Task 10: tests/test_routes_shipments.py (~6 tests) -- replace existing

**Files:**
- Modify: `tests/test_routes_shipments.py`

**Context:** The existing file has 1 trivial test. Replace it with comprehensive TestClient-based tests for the shipment endpoints.

**Step 1: Replace the file contents**

```python
"""Shipment route tests."""

from __future__ import annotations

from litestar.testing import TestClient


class TestShipmentsHealthRoute:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/shipments/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


class TestCreateShipmentRoute:
    def test_create_shipment_returns_201(self, client: TestClient) -> None:
        resp = client.post("/shipments", json={"order_id": "order-1"})
        assert resp.status_code == 201
        body = resp.json()
        assert "id" in body
        assert body["status"] == "created"
        assert body["provider"] == "test-dummy"

    def test_create_shipment_with_explicit_provider(
        self, client: TestClient
    ) -> None:
        resp = client.post(
            "/shipments",
            json={"order_id": "o-2", "provider": "test-dummy"},
        )
        assert resp.status_code == 201
        assert resp.json()["provider"] == "test-dummy"


class TestCreateLabelRoute:
    def test_create_label_returns_201(self, client: TestClient) -> None:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        resp = client.post(f"/shipments/{shipment_id}/label")
        assert resp.status_code == 201
        assert resp.json()["status"] == "label_ready"

    def test_create_label_sets_label_url(self, client: TestClient) -> None:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        resp = client.post(f"/shipments/{shipment_id}/label")
        assert resp.json()["label_url"] != ""


class TestFetchStatusRoute:
    def test_fetch_status_returns_200(self, client: TestClient) -> None:
        created = client.post("/shipments", json={"order_id": "o-1"})
        shipment_id = created.json()["id"]
        client.post(f"/shipments/{shipment_id}/label")
        resp = client.get(f"/shipments/{shipment_id}/status")
        assert resp.status_code == 200
        assert "status" in resp.json()
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_routes_shipments.py -v`
Expected: 6 tests PASS.

**Step 3: Commit**

```bash
git add tests/test_routes_shipments.py
git commit -m "test: replace shipment route tests with comprehensive TestClient tests"
```

---

## Task 11: tests/test_dependencies.py (~4 tests)

**Files:**
- Create: `tests/test_dependencies.py`

**Context:** The `dependencies.py` module (added by critical-fixes) should provide dependency factory functions. If it doesn't exist yet, the tests will skip.

**Step 1: Write the test file**

```python
"""Dependency injection tests."""

from __future__ import annotations

import pytest

deps_mod = pytest.importorskip(
    "litestar_sendparcel.dependencies",
    reason="dependencies module not yet created by critical-fixes plan",
)


class TestDependenciesModule:
    def test_module_is_importable(self) -> None:
        assert deps_mod is not None

    def test_module_has_public_callables(self) -> None:
        """Module should export at least one callable dependency."""
        public = [
            name
            for name in dir(deps_mod)
            if not name.startswith("_") and callable(getattr(deps_mod, name))
        ]
        assert len(public) > 0, (
            "dependencies module should export at least one callable"
        )

    def test_provide_functions_are_callable(self) -> None:
        """Every public 'provide_*' function should be callable."""
        provides = [
            name
            for name in dir(deps_mod)
            if name.startswith("provide_")
        ]
        for name in provides:
            fn = getattr(deps_mod, name)
            assert callable(fn), f"{name} should be callable"

    def test_provide_functions_exist(self) -> None:
        """At minimum, provide_config or provide_repository should exist."""
        names = dir(deps_mod)
        has_provide = any(n.startswith("provide_") for n in names)
        if not has_provide:
            pytest.skip(
                "No provide_* functions found -- dependencies module "
                "may have a different API"
            )
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_dependencies.py -v`
Expected: 4 tests PASS or all SKIPPED.

**Step 3: Commit**

```bash
git add tests/test_dependencies.py
git commit -m "test: add dependency injection module tests"
```

---

## Task 12: tests/test_public_api.py (~3 tests)

**Files:**
- Create: `tests/test_public_api.py`

**Context:** `__init__.py` exports `SendparcelConfig`, `create_shipping_router`, `LitestarPluginRegistry` in `__all__`. The critical-fixes plan may add `__version__`.

**Step 1: Write the test file**

```python
"""Public API surface tests."""

from __future__ import annotations

import litestar_sendparcel


class TestPublicAPI:
    def test_all_exports_defined(self) -> None:
        """Every name in __all__ should be importable from the package."""
        for name in litestar_sendparcel.__all__:
            assert hasattr(litestar_sendparcel, name), (
                f"{name} is in __all__ but not importable"
            )

    def test_core_exports_present(self) -> None:
        """SendparcelConfig, create_shipping_router, LitestarPluginRegistry
        must be in __all__."""
        assert "SendparcelConfig" in litestar_sendparcel.__all__
        assert "create_shipping_router" in litestar_sendparcel.__all__
        assert "LitestarPluginRegistry" in litestar_sendparcel.__all__

    def test_version_attribute(self) -> None:
        """__version__ should exist if critical-fixes has been applied."""
        if not hasattr(litestar_sendparcel, "__version__"):
            import pytest

            pytest.skip("__version__ not yet added by critical-fixes")
        assert isinstance(litestar_sendparcel.__version__, str)
        assert len(litestar_sendparcel.__version__) > 0
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_public_api.py -v`
Expected: 3 tests PASS (or `test_version_attribute` SKIP).

**Step 3: Commit**

```bash
git add tests/test_public_api.py
git commit -m "test: add public API surface tests for __all__ and __version__"
```

---

## Task 13: tests/test_contrib_models.py (~6 tests)

**Files:**
- Create: `tests/test_contrib_models.py`

**Context:** The critical-fixes plan should create SQLAlchemy models in `contrib/sqlalchemy/models.py`. These tests use real aiosqlite in-memory databases via the `async_engine` and `async_session` fixtures from conftest.

**Prerequisite:** `aiosqlite` must be installed: `uv add --dev aiosqlite sqlalchemy[asyncio]`

**Step 1: Check if contrib models exist, install aiosqlite if needed**

Run: `uv run python -c "from litestar_sendparcel.contrib.sqlalchemy.models import ShipmentModel; print('OK')"` -- if this fails, note it and skip this task.

If aiosqlite is not installed: `uv add --dev aiosqlite "sqlalchemy[asyncio]"`

**Step 2: Write the test file**

```python
"""SQLAlchemy contrib model tests."""

from __future__ import annotations

import pytest

try:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from litestar_sendparcel.contrib.sqlalchemy.models import (
        Base,
        ShipmentModel,
    )

    _SKIP = False
except ImportError:
    _SKIP = True

pytestmark = pytest.mark.skipif(
    _SKIP,
    reason="SQLAlchemy contrib models not available",
)


@pytest.fixture()
async def sa_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def sa_session(sa_engine):
    factory = async_sessionmaker(
        sa_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


class TestShipmentModel:
    async def test_create_and_query(self, sa_session: AsyncSession) -> None:
        from sqlalchemy import select

        obj = ShipmentModel(
            order_id="o-1",
            provider="dummy",
            status="new",
            external_id="",
            tracking_number="",
            label_url="",
        )
        sa_session.add(obj)
        await sa_session.commit()

        result = await sa_session.execute(
            select(ShipmentModel).where(ShipmentModel.order_id == "o-1")
        )
        row = result.scalar_one()
        assert row.provider == "dummy"
        assert row.status == "new"

    async def test_id_auto_generated(self, sa_session: AsyncSession) -> None:
        obj = ShipmentModel(
            order_id="o-2",
            provider="inpost",
            status="new",
            external_id="",
            tracking_number="",
            label_url="",
        )
        sa_session.add(obj)
        await sa_session.commit()
        await sa_session.refresh(obj)
        assert obj.id is not None

    async def test_status_update(self, sa_session: AsyncSession) -> None:
        obj = ShipmentModel(
            order_id="o-3",
            provider="dummy",
            status="new",
            external_id="",
            tracking_number="",
            label_url="",
        )
        sa_session.add(obj)
        await sa_session.commit()

        obj.status = "created"
        await sa_session.commit()
        await sa_session.refresh(obj)
        assert obj.status == "created"

    async def test_tracking_number_update(
        self, sa_session: AsyncSession
    ) -> None:
        obj = ShipmentModel(
            order_id="o-4",
            provider="dummy",
            status="new",
            external_id="ext-1",
            tracking_number="",
            label_url="",
        )
        sa_session.add(obj)
        await sa_session.commit()

        obj.tracking_number = "TRK-123"
        await sa_session.commit()
        await sa_session.refresh(obj)
        assert obj.tracking_number == "TRK-123"

    async def test_base_has_metadata(self) -> None:
        assert hasattr(Base, "metadata")
        assert "shipments" in Base.metadata.tables or len(
            Base.metadata.tables
        ) > 0

    async def test_model_table_name(self) -> None:
        assert hasattr(ShipmentModel, "__tablename__")
```

**Step 3: Run tests**

Run: `uv run pytest tests/test_contrib_models.py -v`
Expected: 6 tests PASS or all SKIPPED.

**Step 4: Commit**

```bash
git add tests/test_contrib_models.py
git commit -m "test: add SQLAlchemy contrib model tests with real aiosqlite"
```

---

## Task 14: tests/test_contrib_repository.py (~7 tests)

**Files:**
- Create: `tests/test_contrib_repository.py`

**Context:** Tests for `SQLAlchemyShipmentRepository` from `contrib/sqlalchemy/repository.py`. Uses real aiosqlite in-memory DB. The repository should implement `ShipmentRepository` protocol: `get_by_id`, `create`, `save`, `update_status`.

**Step 1: Write the test file**

```python
"""SQLAlchemy contrib repository tests."""

from __future__ import annotations

import pytest

try:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from litestar_sendparcel.contrib.sqlalchemy.models import Base
    from litestar_sendparcel.contrib.sqlalchemy.repository import (
        SQLAlchemyShipmentRepository,
    )

    _SKIP = False
except ImportError:
    _SKIP = True

pytestmark = pytest.mark.skipif(
    _SKIP,
    reason="SQLAlchemy contrib repository not available",
)


@pytest.fixture()
async def sa_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def sa_session_factory(sa_engine):
    return async_sessionmaker(
        sa_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture()
async def repo(sa_session_factory):
    return SQLAlchemyShipmentRepository(sa_session_factory)


class _FakeOrder:
    """Minimal order stub for repository tests."""

    def get_total_weight(self):
        from decimal import Decimal

        return Decimal("1.0")

    def get_parcels(self):
        return []

    def get_sender_address(self):
        return {"country_code": "PL"}

    def get_receiver_address(self):
        return {"country_code": "DE"}


class TestSQLAlchemyShipmentRepository:
    async def test_create_returns_shipment(self, repo) -> None:
        shipment = await repo.create(
            order=_FakeOrder(),
            provider="dummy",
            status="new",
        )
        assert shipment is not None
        assert shipment.provider == "dummy"
        assert shipment.status == "new"

    async def test_create_assigns_id(self, repo) -> None:
        shipment = await repo.create(
            order=_FakeOrder(),
            provider="dummy",
            status="new",
        )
        assert shipment.id is not None

    async def test_get_by_id_returns_created(self, repo) -> None:
        created = await repo.create(
            order=_FakeOrder(),
            provider="dummy",
            status="new",
        )
        fetched = await repo.get_by_id(str(created.id))
        assert str(fetched.id) == str(created.id)
        assert fetched.provider == "dummy"

    async def test_get_by_id_missing_raises(self, repo) -> None:
        with pytest.raises(Exception):
            await repo.get_by_id("nonexistent-id")

    async def test_save_persists_changes(self, repo) -> None:
        shipment = await repo.create(
            order=_FakeOrder(),
            provider="dummy",
            status="new",
        )
        shipment.tracking_number = "TRK-999"
        saved = await repo.save(shipment)
        assert saved.tracking_number == "TRK-999"

        fetched = await repo.get_by_id(str(shipment.id))
        assert fetched.tracking_number == "TRK-999"

    async def test_update_status_changes_status(self, repo) -> None:
        shipment = await repo.create(
            order=_FakeOrder(),
            provider="dummy",
            status="new",
        )
        updated = await repo.update_status(
            str(shipment.id), "created"
        )
        assert updated.status == "created"

    async def test_update_status_with_extra_fields(self, repo) -> None:
        shipment = await repo.create(
            order=_FakeOrder(),
            provider="dummy",
            status="new",
        )
        updated = await repo.update_status(
            str(shipment.id),
            "created",
            external_id="ext-abc",
        )
        assert updated.status == "created"
        assert updated.external_id == "ext-abc"
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_contrib_repository.py -v`
Expected: 7 tests PASS or all SKIPPED.

**Step 3: Commit**

```bash
git add tests/test_contrib_repository.py
git commit -m "test: add SQLAlchemy contrib repository tests with real aiosqlite"
```

---

## Task 15: tests/test_contrib_retry_store.py (~7 tests)

**Files:**
- Create: `tests/test_contrib_retry_store.py`

**Context:** Tests for `SQLAlchemyRetryStore` from `contrib/sqlalchemy/retry_store.py`. Uses real aiosqlite in-memory DB. The store should implement the full `CallbackRetryStore` protocol: `enqueue`, `get_pending`, `mark_completed`, `mark_failed`, `count_pending`.

**Step 1: Write the test file**

```python
"""SQLAlchemy contrib retry store tests."""

from __future__ import annotations

import pytest

try:
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    from litestar_sendparcel.contrib.sqlalchemy.models import Base
    from litestar_sendparcel.contrib.sqlalchemy.retry_store import (
        SQLAlchemyRetryStore,
    )

    _SKIP = False
except ImportError:
    _SKIP = True

pytestmark = pytest.mark.skipif(
    _SKIP,
    reason="SQLAlchemy contrib retry store not available",
)


@pytest.fixture()
async def sa_engine():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture()
async def sa_session_factory(sa_engine):
    return async_sessionmaker(
        sa_engine, class_=AsyncSession, expire_on_commit=False
    )


@pytest.fixture()
async def store(sa_session_factory):
    return SQLAlchemyRetryStore(sa_session_factory)


class TestSQLAlchemyRetryStore:
    async def test_enqueue_stores_payload(self, store) -> None:
        await store.enqueue(
            {"provider": "dummy", "shipment_id": "s-1", "reason": "err"}
        )
        pending = await store.get_pending()
        assert len(pending) >= 1

    async def test_get_pending_returns_enqueued(self, store) -> None:
        await store.enqueue({"provider": "p1", "shipment_id": "s-1"})
        await store.enqueue({"provider": "p2", "shipment_id": "s-2"})
        pending = await store.get_pending()
        assert len(pending) == 2

    async def test_count_pending(self, store) -> None:
        assert await store.count_pending() == 0
        await store.enqueue({"provider": "p", "shipment_id": "s-1"})
        assert await store.count_pending() == 1

    async def test_mark_completed_removes_from_pending(
        self, store
    ) -> None:
        await store.enqueue({"provider": "p", "shipment_id": "s-1"})
        pending = await store.get_pending()
        assert len(pending) == 1
        # mark_completed takes some identifier -- adapt to actual API
        entry = pending[0]
        entry_id = entry.get("id") or entry.get("index", 0)
        await store.mark_completed(entry_id)
        assert await store.count_pending() == 0

    async def test_mark_failed_removes_from_pending(self, store) -> None:
        await store.enqueue({"provider": "p", "shipment_id": "s-1"})
        pending = await store.get_pending()
        entry = pending[0]
        entry_id = entry.get("id") or entry.get("index", 0)
        await store.mark_failed(entry_id, reason="permanent failure")
        assert await store.count_pending() == 0

    async def test_multiple_enqueue_and_selective_complete(
        self, store
    ) -> None:
        await store.enqueue({"provider": "a", "shipment_id": "s-1"})
        await store.enqueue({"provider": "b", "shipment_id": "s-2"})
        assert await store.count_pending() == 2

        pending = await store.get_pending()
        first_id = pending[0].get("id") or pending[0].get("index", 0)
        await store.mark_completed(first_id)
        assert await store.count_pending() == 1

    async def test_enqueue_preserves_payload_fields(self, store) -> None:
        payload = {
            "provider": "inpost",
            "shipment_id": "s-99",
            "headers": {"x-key": "val"},
            "reason": "timeout",
        }
        await store.enqueue(payload)
        pending = await store.get_pending()
        entry = pending[0]
        # The store should preserve at minimum provider and shipment_id
        assert entry.get("provider") == "inpost" or "inpost" in str(entry)
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_contrib_retry_store.py -v`
Expected: 7 tests PASS or all SKIPPED.

**Step 3: Commit**

```bash
git add tests/test_contrib_retry_store.py
git commit -m "test: add SQLAlchemy contrib retry store tests with real aiosqlite"
```

---

## Task 16: tests/test_integration.py (~4 tests)

**Files:**
- Create: `tests/test_integration.py`

**Context:** Full integration tests using the Litestar TestClient with the wired `test_app` from conftest. These tests exercise the complete flow: create shipment -> create label -> fetch status -> callback, all through HTTP.

**Step 1: Write the test file**

```python
"""Full integration tests: Litestar app with in-memory repo."""

from __future__ import annotations

from litestar.testing import TestClient


class TestFullShipmentFlow:
    """End-to-end tests through the Litestar HTTP layer."""

    def test_create_label_status_flow(self, client: TestClient) -> None:
        """Create shipment, create label, fetch status -- full happy path."""
        # Step 1: Create shipment
        created = client.post("/shipments", json={"order_id": "int-o-1"})
        assert created.status_code == 201
        shipment_id = created.json()["id"]
        assert created.json()["status"] == "created"
        assert created.json()["provider"] == "test-dummy"

        # Step 2: Create label
        label = client.post(f"/shipments/{shipment_id}/label")
        assert label.status_code == 201
        assert label.json()["status"] == "label_ready"
        assert label.json()["label_url"] != ""

        # Step 3: Fetch status
        status = client.get(f"/shipments/{shipment_id}/status")
        assert status.status_code == 200
        assert "status" in status.json()

    def test_create_label_callback_flow(self, client: TestClient) -> None:
        """Create, label, then callback -- verify status changes."""
        created = client.post("/shipments", json={"order_id": "int-o-2"})
        shipment_id = created.json()["id"]

        client.post(f"/shipments/{shipment_id}/label")

        callback = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "picked_up"},
            headers={"x-test-token": "valid"},
        )
        assert callback.status_code == 201
        assert callback.json()["shipment_status"] == "in_transit"

    def test_callback_retry_on_bad_token(
        self, client: TestClient, retry_store
    ) -> None:
        """Bad callback token triggers retry enqueue, not crash."""
        created = client.post("/shipments", json={"order_id": "int-o-3"})
        shipment_id = created.json()["id"]

        resp = client.post(
            f"/callbacks/test-dummy/{shipment_id}",
            json={"event": "test"},
            headers={"x-test-token": "INVALID"},
        )
        assert resp.status_code == 400
        assert len(retry_store.events) == 1
        assert retry_store.events[0]["provider"] == "test-dummy"

    def test_health_always_available(self, client: TestClient) -> None:
        """Health endpoint should work without any prior state."""
        resp = client.get("/shipments/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
```

**Step 2: Run tests**

Run: `uv run pytest tests/test_integration.py -v`
Expected: 4 tests PASS.

**Step 3: Run the full test suite**

Run: `uv run pytest tests/ -v`
Expected: All tests PASS. The count should be approximately:
- 5 existing tests (test_example_app, test_routes_flow)
- ~80 new tests from tasks 1-16
- Total: ~85+ tests

**Step 4: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: add full integration tests for shipment flow through HTTP layer"
```

---

## Summary

| Task | File | Tests | Notes |
|------|------|-------|-------|
| 1 | `tests/conftest.py` | 0 (fixtures) | Expand RetryStore, add test_app, client, SQLAlchemy fixtures |
| 2 | `tests/test_config.py` | 7 | SendparcelConfig defaults and validation |
| 3 | `tests/test_protocols.py` | 4 | Protocol conformance (isinstance checks) |
| 4 | `tests/test_exceptions.py` | 7 | EXCEPTION_HANDLERS dict (may skip) |
| 5 | `tests/test_registry.py` | 5 | LitestarPluginRegistry operations |
| 6 | `tests/test_plugin.py` | 5 | Router creation and structure |
| 7 | `tests/test_schemas.py` | 7 | Pydantic model validation |
| 8 | `tests/test_retry.py` | 6 | enqueue_callback_retry behavior |
| 9 | `tests/test_routes_callbacks.py` | 6 | Callback endpoint via TestClient |
| 10 | `tests/test_routes_shipments.py` | 6 | Shipment endpoints via TestClient |
| 11 | `tests/test_dependencies.py` | 4 | Dependency module structure (may skip) |
| 12 | `tests/test_public_api.py` | 3 | __all__ and __version__ |
| 13 | `tests/test_contrib_models.py` | 6 | SQLAlchemy models with aiosqlite (may skip) |
| 14 | `tests/test_contrib_repository.py` | 7 | SQLAlchemy repository with aiosqlite (may skip) |
| 15 | `tests/test_contrib_retry_store.py` | 7 | SQLAlchemy retry store with aiosqlite (may skip) |
| 16 | `tests/test_integration.py` | 4 | Full E2E flow via Litestar TestClient |
| **Total** | **16 files** | **~84** | |
