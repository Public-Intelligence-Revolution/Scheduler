"""Tests for the heartbeat domain model."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scheduler.models.heartbeat import Heartbeat
from scheduler.models.node import NodeStatus


class TestNodeStatus:
    """Tests for the NodeStatus enum."""

    def test_values(self):
        assert NodeStatus.ONLINE == "online"
        assert NodeStatus.OFFLINE == "offline"
        assert NodeStatus.BUSY == "busy"
        assert NodeStatus.UNKNOWN == "unknown"

    def test_member_count(self):
        assert len(NodeStatus) == 4

    def test_is_string(self):
        assert isinstance(NodeStatus.ONLINE, str)


class TestHeartbeat:
    """Tests for the Heartbeat model."""

    @pytest.fixture()
    def now(self) -> datetime:
        return datetime.now(tz=UTC)

    def test_valid_construction(self, now: datetime):
        heartbeat = Heartbeat(
            node_id="node-001",
            timestamp=now,
            status=NodeStatus.ONLINE,
            queue_length=2,
            cpu_utilization=25.5,
            ram_available_gb=16.0,
            gpu_utilization=80.0,
            vram_available_gb=12.0,
        )
        assert heartbeat.node_id == "node-001"
        assert heartbeat.timestamp == now
        assert heartbeat.status == NodeStatus.ONLINE
        assert heartbeat.queue_length == 2
        assert heartbeat.cpu_utilization == 25.5
        assert heartbeat.ram_available_gb == 16.0
        assert heartbeat.gpu_utilization == 80.0
        assert heartbeat.vram_available_gb == 12.0

    def test_negative_queue_length_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=-1,
                cpu_utilization=25.5,
                ram_available_gb=16.0,
                gpu_utilization=80.0,
                vram_available_gb=12.0,
            )

    def test_negative_cpu_utilization_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=0,
                cpu_utilization=-0.1,
                ram_available_gb=16.0,
                gpu_utilization=80.0,
                vram_available_gb=12.0,
            )

    def test_cpu_utilization_greater_than_100_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=0,
                cpu_utilization=100.1,
                ram_available_gb=16.0,
                gpu_utilization=80.0,
                vram_available_gb=12.0,
            )

    def test_negative_ram_available_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=0,
                cpu_utilization=25.5,
                ram_available_gb=-0.1,
                gpu_utilization=80.0,
                vram_available_gb=12.0,
            )

    def test_negative_gpu_utilization_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=0,
                cpu_utilization=25.5,
                ram_available_gb=16.0,
                gpu_utilization=-0.1,
                vram_available_gb=12.0,
            )

    def test_gpu_utilization_greater_than_100_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=0,
                cpu_utilization=25.5,
                ram_available_gb=16.0,
                gpu_utilization=100.1,
                vram_available_gb=12.0,
            )

    def test_negative_vram_available_rejected(self, now: datetime):
        with pytest.raises(ValidationError):
            Heartbeat(
                node_id="node-001",
                timestamp=now,
                status=NodeStatus.ONLINE,
                queue_length=0,
                cpu_utilization=25.5,
                ram_available_gb=16.0,
                gpu_utilization=80.0,
                vram_available_gb=-0.1,
            )
