"""Raft-based consensus engine for multi-scheduler state replication."""

import asyncio
import json
import random
import time
from typing import Any

import structlog
import zenoh

from scheduler.registry.node_registry import NodeRegistry

logger = structlog.stdlib.get_logger()


class RaftConsensusEngine:
    """Consensus engine implementing a lightweight Raft protocol over Zenoh."""

    def __init__(
        self,
        scheduler_id: str,
        registry: NodeRegistry,
        config: zenoh.Config | None = None,
    ) -> None:
        """Initialize the RaftConsensusEngine.

        Args:
            scheduler_id: Unique identifier for this scheduler instance.
            registry: The NodeRegistry where committed logs are applied.
            config: Optional Zenoh configuration.
        """
        self.scheduler_id = scheduler_id
        self.registry = registry
        self.config = config or zenoh.Config()

        self.state = "FOLLOWER"  # LEADER, CANDIDATE, FOLLOWER
        self.current_term = 0
        self.voted_for: str | None = None
        self.log: list[dict[str, Any]] = []
        self.commit_index = -1
        self.last_applied = -1

        # Peer tracking and match indexes
        self.peers: dict[str, float] = {}  # peer_id -> last_seen_time
        self.match_index: dict[str, int] = {}  # peer_id -> match_index
        self.votes: set[str] = set()

        self.session: zenoh.Session | None = None
        self.subscriber: zenoh.Subscriber[Any] | None = None
        self.publisher: zenoh.Publisher | None = None

        self._loop: asyncio.AbstractEventLoop | None = None
        self._heartbeat_task: asyncio.Task[None] | None = None
        self._election_timeout_task: asyncio.Task[None] | None = None

        self._commit_events: dict[int, asyncio.Event] = {}
        self.last_heartbeat_time = time.time()
        self._lock = asyncio.Lock()
        self._is_active = False
        self.leader_id: str | None = None

        # Link registry back to consensus
        self.registry.consensus_engine = self

    def is_active(self) -> bool:
        """Check if the consensus engine is active."""
        return self._is_active

    async def start(self) -> None:
        """Start the Raft consensus engine and connect to Zenoh consensus planes."""
        async with self._lock:
            if self._is_active:
                return

            self._loop = asyncio.get_running_loop()
            self.session = zenoh.open(self.config)
            self.publisher = self.session.declare_publisher("public-intelligence/net/consensus/*")
            self.subscriber = self.session.declare_subscriber(
                "public-intelligence/net/consensus/*", self._on_message
            )

            self._is_active = True
            self.last_heartbeat_time = time.time()

            self._election_timeout_task = asyncio.create_task(self._run_election_timeout_loop())
            self._heartbeat_task = asyncio.create_task(self._run_heartbeat_loop())

            logger.info("consensus_engine_started", id=self.scheduler_id)

    async def stop(self) -> None:
        """Stop the Raft consensus engine cleanly."""
        async with self._lock:
            if not self._is_active:
                return
            self._is_active = False

        if self._election_timeout_task is not None:
            self._election_timeout_task.cancel()
            self._election_timeout_task = None
        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None

        if self.subscriber is not None:
            self.subscriber.undeclare()  # type: ignore[no-untyped-call]
            self.subscriber = None
        if self.publisher is not None:
            self.publisher.undeclare()  # type: ignore[no-untyped-call]
            self.publisher = None
        if self.session is not None:
            self.session.close()  # type: ignore[no-untyped-call]
            self.session = None

        logger.info("consensus_engine_stopped", id=self.scheduler_id)

    async def propose(self, action: str, data: Any) -> None:
        """Propose a state change (register/unregister) to the replicated log.

        Blocks until the change has achieved majority consensus quorum and committed.
        """
        async with self._lock:
            if not self._is_active:
                raise RuntimeError("Consensus engine is not active")
            if not self.peers and self.state != "LEADER":
                self.state = "LEADER"
                self.leader_id = self.scheduler_id

            term = self.current_term
            entry = {"term": term, "action": action, "data": data}

            if self.state == "LEADER":
                self.log.append(entry)
                proposal_index = len(self.log) - 1
                event = asyncio.Event()
                self._commit_events[proposal_index] = event
                await self._send_heartbeats()
            else:
                leader = self.leader_id
                if leader is not None:
                    # Forward proposal to the leader
                    await self._send_message(
                        leader,
                        {
                            "type": "Propose",
                            "sender_id": self.scheduler_id,
                            "action": action,
                            "data": data,
                        },
                    )
                    # Follower wait loop for entry replication/commitment
                    start_time = time.time()
                    while time.time() - start_time < 5.0:
                        for i in range(self.commit_index + 1):
                            if i < len(self.log):
                                logged = self.log[i]
                                if logged.get("action") == action and logged.get("data") == data:
                                    return
                        await asyncio.sleep(0.05)
                    raise TimeoutError("Proposal replication timed out")
                else:
                    raise RuntimeError("No leader found in consensus cluster")

        if self.state == "LEADER":
            required_quorum = (len(self.peers) + 1) // 2 + 1
            if required_quorum <= 1:
                # Commit immediately if single node
                await self._apply_log_entries(proposal_index)
                return

            try:
                await asyncio.wait_for(event.wait(), timeout=5.0)
            except TimeoutError:
                raise TimeoutError("Proposal replication timed out") from None
            finally:
                self._commit_events.pop(proposal_index, None)

    async def _broadcast(self, msg: dict[str, Any]) -> None:
        if self.session is not None:
            payload = json.dumps(msg)
            self.session.put("public-intelligence/net/consensus/broadcast", payload)

    async def _send_message(self, target_id: str, msg: dict[str, Any]) -> None:
        if self.session is not None:
            payload = json.dumps(msg)
            self.session.put(f"public-intelligence/net/consensus/{target_id}", payload)

    def _on_message(self, sample: zenoh.Sample) -> None:
        if self._loop is None or not self._loop.is_running() or not self._is_active:
            return

        try:
            payload_str = sample.payload.to_string()
        except AttributeError:
            try:
                payload_str = sample.payload.decode("utf-8")  # type: ignore[attr-defined]
            except (AttributeError, UnicodeDecodeError):
                payload_str = str(sample.payload)

        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(self._process_message(payload_str))
        )

    async def _process_message(self, payload_str: str) -> None:
        try:
            msg = json.loads(payload_str)
        except Exception:
            return

        sender_id = msg.get("sender_id")
        if sender_id == self.scheduler_id:
            return

        # Prune dead peers and register active ones
        now = time.time()
        async with self._lock:
            self.peers[sender_id] = now
            # Clean peers not seen for 5 seconds
            for p, last_seen in list(self.peers.items()):
                if now - last_seen > 5.0:
                    self.peers.pop(p, None)
                    self.match_index.pop(p, None)

        msg_type = msg.get("type")
        if msg_type == "RequestVote":
            await self._handle_request_vote(msg)
        elif msg_type == "RequestVoteResponse":
            await self._handle_request_vote_response(msg)
        elif msg_type == "AppendEntries":
            await self._handle_append_entries(msg)
        elif msg_type == "AppendEntriesResponse":
            await self._handle_append_entries_response(msg)
        elif msg_type == "Propose":
            await self._handle_propose(msg)

    async def _run_election_timeout_loop(self) -> None:
        while self._is_active:
            timeout = random.uniform(0.3, 0.6)
            try:
                await asyncio.sleep(timeout)
            except asyncio.CancelledError:
                break

            async with self._lock:
                if self.state == "LEADER":
                    continue
                if time.time() - self.last_heartbeat_time >= timeout:
                    await self._start_election()

    async def _run_heartbeat_loop(self) -> None:
        while self._is_active:
            try:
                await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                break

            async with self._lock:
                if self.state == "LEADER":
                    await self._send_heartbeats()

    async def _start_election(self) -> None:
        self.state = "CANDIDATE"
        self.current_term += 1
        self.voted_for = self.scheduler_id
        self.votes = {self.scheduler_id}
        self.last_heartbeat_time = time.time()

        last_log_index = len(self.log) - 1
        last_log_term = self.log[-1]["term"] if self.log else 0

        await self._broadcast(
            {
                "type": "RequestVote",
                "sender_id": self.scheduler_id,
                "term": self.current_term,
                "candidate_id": self.scheduler_id,
                "last_log_index": last_log_index,
                "last_log_term": last_log_term,
            }
        )

    async def _become_leader(self) -> None:
        self.state = "LEADER"
        self.leader_id = self.scheduler_id
        logger.info("consensus_leader_elected", term=self.current_term, id=self.scheduler_id)

        for peer in self.peers:
            self.match_index[peer] = -1

        self.last_heartbeat_time = time.time()
        await self._send_heartbeats()

    async def _send_heartbeats(self) -> None:
        last_log_index = len(self.log) - 1
        last_log_term = self.log[-1]["term"] if self.log else 0

        await self._broadcast(
            {
                "type": "AppendEntries",
                "sender_id": self.scheduler_id,
                "term": self.current_term,
                "leader_id": self.scheduler_id,
                "prev_log_index": last_log_index,
                "prev_log_term": last_log_term,
                "entries": self.log,
                "leader_commit": self.commit_index,
            }
        )

    async def _handle_request_vote(self, msg: dict[str, Any]) -> None:
        term = msg.get("term", 0)
        candidate_id = msg.get("candidate_id")
        if not isinstance(candidate_id, str):
            return
        last_log_index = msg.get("last_log_index", -1)
        last_log_term = msg.get("last_log_term", 0)

        async with self._lock:
            if term > self.current_term:
                self.current_term = term
                self.state = "FOLLOWER"
                self.voted_for = None
                self.leader_id = None

            if term < self.current_term:
                await self._send_message(
                    candidate_id,
                    {
                        "type": "RequestVoteResponse",
                        "sender_id": self.scheduler_id,
                        "term": self.current_term,
                        "vote_granted": False,
                        "peer_id": self.scheduler_id,
                    },
                )
                return

            my_last_log_index = len(self.log) - 1
            my_last_log_term = self.log[-1]["term"] if self.log else 0

            log_ok = last_log_term > my_last_log_term or (
                last_log_term == my_last_log_term and last_log_index >= my_last_log_index
            )

            if (self.voted_for is None or self.voted_for == candidate_id) and log_ok:
                self.voted_for = candidate_id
                self.last_heartbeat_time = time.time()
                await self._send_message(
                    candidate_id,
                    {
                        "type": "RequestVoteResponse",
                        "sender_id": self.scheduler_id,
                        "term": self.current_term,
                        "vote_granted": True,
                        "peer_id": self.scheduler_id,
                    },
                )
            else:
                await self._send_message(
                    candidate_id,
                    {
                        "type": "RequestVoteResponse",
                        "sender_id": self.scheduler_id,
                        "term": self.current_term,
                        "vote_granted": False,
                        "peer_id": self.scheduler_id,
                    },
                )

    async def _handle_request_vote_response(self, msg: dict[str, Any]) -> None:
        term = msg.get("term", 0)
        peer_id = msg.get("peer_id")
        if not isinstance(peer_id, str):
            return
        vote_granted = msg.get("vote_granted", False)

        async with self._lock:
            if self.state != "CANDIDATE" or term != self.current_term:
                return

            if vote_granted:
                self.votes.add(peer_id)
                required_votes = (len(self.peers) + 1) // 2 + 1
                if len(self.votes) >= required_votes:
                    await self._become_leader()

    async def _handle_append_entries(self, msg: dict[str, Any]) -> None:
        term = msg.get("term", 0)
        leader_id = msg.get("leader_id")
        if not isinstance(leader_id, str):
            return
        entries = msg.get("entries", [])
        leader_commit = msg.get("leader_commit", -1)

        async with self._lock:
            if term >= self.current_term:
                if term > self.current_term or self.state != "FOLLOWER":
                    self.current_term = term
                    self.state = "FOLLOWER"
                    self.voted_for = None
                self.leader_id = leader_id
                self.last_heartbeat_time = time.time()

            if term < self.current_term:
                await self._send_message(
                    leader_id,
                    {
                        "type": "AppendEntriesResponse",
                        "sender_id": self.scheduler_id,
                        "term": self.current_term,
                        "success": False,
                        "match_index": len(self.log) - 1,
                        "peer_id": self.scheduler_id,
                    },
                )
                return

            # Replicate entries (self-healing configuration log replacement)
            self.log = entries

            if leader_commit > self.commit_index:
                await self._apply_log_entries(leader_commit)

            await self._send_message(
                leader_id,
                {
                    "type": "AppendEntriesResponse",
                    "sender_id": self.scheduler_id,
                    "term": self.current_term,
                    "success": True,
                    "match_index": len(self.log) - 1,
                    "peer_id": self.scheduler_id,
                },
            )

    async def _handle_append_entries_response(self, msg: dict[str, Any]) -> None:
        term = msg.get("term", 0)
        success = msg.get("success", False)
        match_index = msg.get("match_index", -1)
        peer_id = msg.get("peer_id")
        if not isinstance(peer_id, str):
            return

        async with self._lock:
            if term > self.current_term:
                self.current_term = term
                self.state = "FOLLOWER"
                self.voted_for = None
                self.leader_id = None
                self.last_heartbeat_time = time.time()
                return

            if self.state != "LEADER" or term != self.current_term:
                return

            if success:
                self.match_index[peer_id] = match_index

                # Quorum check for log replication commitment
                for n in range(len(self.log) - 1, self.commit_index, -1):
                    match_count = 1
                    for _, m_idx in self.match_index.items():
                        if m_idx >= n:
                            match_count += 1

                    required_quorum = (len(self.peers) + 1) // 2 + 1
                    if match_count >= required_quorum:
                        await self._apply_log_entries(n)
                        break

    async def _handle_propose(self, msg: dict[str, Any]) -> None:
        action = msg.get("action")
        data = msg.get("data")
        async with self._lock:
            if self.state == "LEADER":
                entry = {"term": self.current_term, "action": action, "data": data}
                self.log.append(entry)
                await self._send_heartbeats()

    async def _apply_log_entries(self, new_commit_index: int) -> None:
        for idx in range(self.commit_index + 1, new_commit_index + 1):
            if idx >= len(self.log):
                break
            entry = self.log[idx]
            action = entry.get("action")
            data = entry.get("data")

            logger.info("consensus_applying_log_entry", index=idx, action=action)
            try:
                if action == "register":
                    from scheduler.models.node import Node

                    if isinstance(data, dict):
                        node = Node(**data)
                        await self.registry.local_register(node)
                elif action in ("unregister", "unregister_node"):
                    if isinstance(data, dict):
                        node_id = data.get("node_id")
                        if isinstance(node_id, str):
                            if action == "unregister":
                                await self.registry.local_unregister(node_id)
                            else:
                                await self.registry.local_unregister_node(node_id)
            except Exception as e:
                logger.warning("consensus_apply_log_entry_error", index=idx, error=str(e))

            if idx in self._commit_events:
                self._commit_events[idx].set()

        self.commit_index = new_commit_index
