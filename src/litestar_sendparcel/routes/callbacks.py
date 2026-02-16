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

    path = "/callbacks"
    tags = ["callbacks"]

    @post("/{provider_slug:str}/{shipment_id:str}")
    async def handle_callback(
        self,
        provider_slug: str,
        shipment_id: str,
        request: Request,
        config: Annotated[SendparcelConfig, Dependency(skip_validation=True)],
        repository: Annotated[
            ShipmentRepository, Dependency(skip_validation=True)
        ],
        retry_store: Annotated[
            CallbackRetryStore | None,
            Dependency(skip_validation=True),
        ] = None,
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
