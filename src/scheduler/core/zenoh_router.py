"""Zenoh router implementation for receiving node heartbeats."""

import asyncio
import json
import uuid
from typing import Any

import structlog
import zenoh

from scheduler.core.consensus import RaftConsensusEngine
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
        if config is None:
            from scheduler.core.config import get_settings

            settings = get_settings()
            config = zenoh.Config()
            if settings.zenoh_listen_endpoints:
                config.insert_json5(
                    "listen/endpoints", json.dumps(settings.zenoh_listen_endpoints)
                )
                config.insert_json5("mode", '"router"')
            if settings.zenoh_peer_endpoints:
                config.insert_json5("connect/endpoints", json.dumps(settings.zenoh_peer_endpoints))
            if not settings.zenoh_multicast_scouting:
                config.insert_json5("scouting/multicast/enabled", "false")
        self.config = config
        self.session: zenoh.Session | None = None
        self.subscriber: zenoh.Subscriber[Any] | None = None
        self.liveliness_subscriber: zenoh.Subscriber[Any] | None = None
        self.telemetry_subscriber: zenoh.Subscriber[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

        # Generate unique scheduler ID and instantiate the consensus engine
        scheduler_id = f"scheduler-{uuid.uuid4().hex[:8]}"
        self.consensus_engine = RaftConsensusEngine(scheduler_id, self.registry, self.config)
        self._background_tasks: set[asyncio.Task[Any]] = set()

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
            "public-intelligence/net/*/heartbeat", self._on_heartbeat
        )

        # Subscribe to liveliness tokens.
        # Zenoh liveliness subscriber detects PUT/DELETE events for liveliness tokens.
        self.liveliness_subscriber = self.session.liveliness().declare_subscriber(
            "public-intelligence/net/liveliness/*", self._on_liveliness
        )

        # Subscribe to telemetry feed.
        self.telemetry_subscriber = self.session.declare_subscriber(
            "public-intelligence/net/nodes/*/telemetry", self._on_telemetry
        )

        # Start consensus engine
        start_task = asyncio.create_task(self.consensus_engine.start())
        self._background_tasks.add(start_task)
        start_task.add_done_callback(self._background_tasks.discard)

        logger.info("zenoh_router_started")

    def stop(self) -> None:
        """Stop and clean up the Zenoh router session."""
        if self.session is None:
            return

        logger.info("zenoh_router_stopping")
        if self.subscriber is not None:
            self.subscriber.undeclare()  # type: ignore[no-untyped-call]
            self.subscriber = None

        if self.liveliness_subscriber is not None:
            self.liveliness_subscriber.undeclare()  # type: ignore[no-untyped-call]
            self.liveliness_subscriber = None

        if self.telemetry_subscriber is not None:
            self.telemetry_subscriber.undeclare()  # type: ignore[no-untyped-call]
            self.telemetry_subscriber = None

        # Stop consensus engine
        stop_task = asyncio.create_task(self.consensus_engine.stop())
        self._background_tasks.add(stop_task)
        stop_task.add_done_callback(self._background_tasks.discard)

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

    def _on_liveliness(self, sample: zenoh.Sample) -> None:
        """Callback triggered when a liveliness token is updated (PUT/DELETE).

        We process DELETE events as node deathrattles to trigger self-correcting unregistration.
        """
        if self._loop is None or not self._loop.is_running():
            return

        if sample.kind == zenoh.SampleKind.DELETE:
            key_expr = str(sample.key_expr)
            # key_expr format: public-intelligence/net/liveliness/<node_id>
            parts = key_expr.split("/")
            if len(parts) >= 4:
                node_id = parts[3]
                self._loop.call_soon_threadsafe(
                    lambda: asyncio.create_task(self._process_deathrattle(node_id, key_expr))
                )

    async def _process_deathrattle(self, node_id: str, key_expr: str) -> None:
        """Unregister the dead node and log cluster group resizing."""
        logger.info("zenoh_liveliness_deathrattle_detected", node_id=node_id, key_expr=key_expr)
        await self.registry.unregister_node(node_id)
        logger.info("zenoh_liveliness_cluster_group_resized", node_id=node_id)

    def _on_telemetry(self, sample: zenoh.Sample) -> None:
        """Callback triggered when telemetry is received on the zenoh session."""
        if self._loop is None or not self._loop.is_running():
            return

        try:
            payload_str = sample.payload.to_string()
        except AttributeError:
            try:
                payload_str = sample.payload.decode("utf-8")  # type: ignore[attr-defined]
            except (AttributeError, UnicodeDecodeError):
                payload_str = str(sample.payload)

        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._process_telemetry(payload_str, str(sample.key_expr)))
        )

    async def _process_telemetry(self, payload_str: str, key_expr: str) -> None:
        """Asynchronously decrypt and map the hardware health metrics straight into registry."""
        import base64
        import hashlib
        import hmac
        import os

        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        try:
            envelope = json.loads(payload_str)
        except json.JSONDecodeError as e:
            logger.error("zenoh_telemetry_json_decode_error", error=str(e), key_expr=key_expr)
            return

        iv_b64 = envelope.get("iv")
        ciphertext_b64 = envelope.get("ciphertext")
        sig = envelope.get("signature")

        if not iv_b64 or not ciphertext_b64 or not sig:
            logger.warning("zenoh_telemetry_malformed_envelope", key_expr=key_expr)
            return

        secret_key = os.environ.get(
            "TELEMETRY_SECRET_KEY", "pi_telemetry_secure_default_secret_key"
        )

        # Derive keys
        secret_bytes = secret_key.encode("utf-8")
        enc_key = hashlib.sha256(secret_bytes + b"-encryption").digest()
        hmac_key = hashlib.sha256(secret_bytes + b"-hmac").digest()

        # Verify HMAC signature first
        message_to_verify = f"{iv_b64}:{ciphertext_b64}".encode()
        expected_sig = hmac.new(hmac_key, message_to_verify, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(sig, expected_sig):
            logger.error(
                "security_breach_warning",
                reason="HMAC signature verification failed. Tampered or unauthorized payload.",
                key_expr=key_expr,
            )
            return

        # Decrypt payload
        try:
            iv = base64.b64decode(iv_b64)
            ciphertext = base64.b64decode(ciphertext_b64)
            aesgcm = AESGCM(enc_key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None).decode("utf-8")
            data = json.loads(plaintext)
        except Exception as e:
            logger.error(
                "security_breach_warning",
                reason=f"Decryption failed or payload altered: {e}",
                key_expr=key_expr,
            )
            return

        node_id = data.get("node_id")
        if not node_id:
            parts = key_expr.split("/")
            if len(parts) >= 5:
                node_id = parts[4]

        if not node_id:
            logger.warning("zenoh_telemetry_missing_node_id", key_expr=key_expr)
            return

        # Map the hardware health metrics straight into the active NodeRegistry state metadata
        if not hasattr(self.registry, "_telemetry"):
            self.registry._telemetry = {}

        self.registry._telemetry[node_id] = data
        logger.info("zenoh_telemetry_mapped", node_id=node_id, key_expr=key_expr)
