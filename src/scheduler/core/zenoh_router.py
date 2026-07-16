"""Zenoh router implementation for receiving node heartbeats."""

import asyncio
import json
from typing import Any

import structlog
import zenoh

from scheduler.models.heartbeat import Heartbeat
from scheduler.registry.node_registry import NodeRegistry

logger = structlog.stdlib.get_logger()


class ZenohRouter:
    """Listens for incoming node heartbeats over Zenoh and routes them to NodeRegistry."""

    def __init__(self, registry: NodeRegistry, config: zenoh.Config | None = None) -> None:
        """Initialize the ZenohRouter.

        Args:
            registry: The NodeRegistry where heartbeats should be updated.
            config: Optional Zenoh session configuration.
        """
        self.registry = registry
        self.config = config or zenoh.Config()
        self.session: zenoh.Session | None = None
        self.subscriber: zenoh.Subscriber[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def start(self) -> None:
        """Start the Zenoh router session and declare the subscriber."""
        if self.session is not None:
            return

        self._loop = asyncio.get_running_loop()
        logger.info("zenoh_router_starting", key_expr="public-intelligence/net/*/heartbeat")
        
        # Open a Zenoh session with configured settings
        self.session = zenoh.open(self.config)
        
        # Subscribe to heartbeat path.
        # Zenoh python subscriber takes a callback.
        self.subscriber = self.session.declare_subscriber(
            "public-intelligence/net/*/heartbeat",
            self._on_heartbeat
        )
        logger.info("zenoh_router_started")

    def stop(self) -> None:
        """Stop and clean up the Zenoh router session."""
        if self.session is None:
            return

        logger.info("zenoh_router_stopping")
        if self.subscriber is not None:
            self.subscriber.undeclare()  # type: ignore[no-untyped-call]
            self.subscriber = None
        
        self.session.close()  # type: ignore[no-untyped-call]
        self.session = None
        self._loop = None
        logger.info("zenoh_router_stopped")

    def _on_heartbeat(self, sample: zenoh.Sample) -> None:
        """Callback triggered when a heartbeat is received on the zenoh session.

        Runs in Zenoh's internal thread pool, so we dispatch the async work
        to the running asyncio event loop.
        """
        if self._loop is None or not self._loop.is_running():
            return

        # Attempt to decode sample.payload safely
        try:
            payload_str = sample.payload.to_string()
        except AttributeError:
            try:
                payload_str = sample.payload.decode("utf-8")  # type: ignore[attr-defined]
            except (AttributeError, UnicodeDecodeError):
                payload_str = str(sample.payload)

        # Schedule the processing on the asyncio event loop thread-safely
        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._process_heartbeat(payload_str, str(sample.key_expr)))
        )

    async def _process_heartbeat(self, payload_str: str, key_expr: str) -> None:
        """Asynchronously parse and register/update the heartbeat."""
        try:
            data = json.loads(payload_str)
        except json.JSONDecodeError as e:
            logger.error("zenoh_heartbeat_json_decode_error", error=str(e), key_expr=key_expr)
            return

        try:
            heartbeat = Heartbeat(**data)
        except Exception as e:
            logger.error("zenoh_heartbeat_validation_error", error=str(e), key_expr=key_expr)
            return

        try:
            await self.registry.update_heartbeat(heartbeat)
            logger.info(
                "zenoh_heartbeat_processed",
                node_id=heartbeat.node_id,
                key_expr=key_expr,
            )
        except ValueError as e:
            # Handle unregistered node
            logger.warning(
                "zenoh_heartbeat_ignored_unregistered_node",
                node_id=heartbeat.node_id,
                error=str(e),
                key_expr=key_expr,
            )
