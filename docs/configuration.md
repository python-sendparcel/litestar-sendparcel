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
