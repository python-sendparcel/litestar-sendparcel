"""Callback endpoints."""

from __future__ import annotations

from litestar import Request, post
from litestar.exceptions import HTTPException
from sendparcel.exceptions import InvalidCallbackError
from sendparcel.flow import ShipmentFlow
from sendparcel.protocols import ShipmentRepository

from litestar_sendparcel.config import SendparcelConfig
from litestar_sendparcel.protocols import CallbackRetryStore
from litestar_sendparcel.retry import enqueue_callback_retry
from litestar_sendparcel.schemas import CallbackResponse


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
    shipment = await repository.get_by_id(shipment_id)
    if str(shipment.provider) != provider_slug:
        raise HTTPException(status_code=400, detail="Provider slug mismatch")

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
    except InvalidCallbackError as exc:
        await enqueue_callback_retry(
            retry_store,
            provider_slug=provider_slug,
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
            reason=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await enqueue_callback_retry(
            retry_store,
            provider_slug=provider_slug,
            shipment_id=shipment_id,
            payload=payload,
            headers=headers,
            reason=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail="Callback handling failed",
        ) from exc

    return CallbackResponse(
        provider=provider_slug,
        status="accepted",
        shipment_status=str(updated.status),
    )
