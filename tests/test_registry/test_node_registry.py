"""Tests for the in-memory NodeRegistry."""

import threading
from datetime import UTC, datetime

import pytest

from scheduler.models.node import GPUInfo, Node, NodeStatus
from scheduler.registry.node_registry import NodeRegistry


@pytest.fixture()
def gpu() -> GPUInfo:
    return GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=60.0)


@pytest.fixture()
def now() -> datetime:
    return datetime.now(tz=UTC)


def _make_node(node_id: str, gpu: GPUInfo, now: datetime) -> Node:
    """Helper to build a Node with sensible defaults."""
    return Node(
        node_id=node_id,
        hostname=f"host-{node_id}",
        ip_address=f"10.0.0.{node_id}",
        region="us-east-1",
        gpu=gpu,
        cpu_cores=32,
        ram_gb=128.0,
        models=["llama-3-70b"],
        queue_length=0,
        status=NodeStatus.ONLINE,
        last_heartbeat=now,
    )


class TestEmptyRegistry:
    """Tests for a freshly-created registry."""

    def test_count_is_zero(self):
        registry = NodeRegistry()
        assert registry.count() == 0

    def test_list_is_empty(self):
        registry = NodeRegistry()
        assert registry.list() == []

    def test_get_returns_none(self):
        registry = NodeRegistry()
        assert registry.get("nonexistent") is None

    def test_exists_returns_false(self):
        registry = NodeRegistry()
        assert registry.exists("nonexistent") is False


class TestRegister:
    """Tests for node registration."""

    def test_register_node(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("1", gpu, now)
        registry.register(node)
        assert registry.count() == 1
        assert registry.get("1") == node

    def test_register_duplicate_raises(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("1", gpu, now)
        registry.register(node)
        with pytest.raises(ValueError, match="Node already registered: 1"):
            registry.register(node)


class TestExists:
    """Tests for existence checks."""

    def test_exists_after_register(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        registry.register(_make_node("1", gpu, now))
        assert registry.exists("1") is True

    def test_not_exists_after_unregister(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        registry.register(_make_node("1", gpu, now))
        registry.unregister("1")
        assert registry.exists("1") is False


class TestGet:
    """Tests for node retrieval."""

    def test_get_registered_node(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("1", gpu, now)
        registry.register(node)
        assert registry.get("1") == node

    def test_get_missing_node_returns_none(self):
        registry = NodeRegistry()
        assert registry.get("missing") is None


class TestList:
    """Tests for listing nodes."""

    def test_list_preserves_insertion_order(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node_a = _make_node("a", gpu, now)
        node_b = _make_node("b", gpu, now)
        node_c = _make_node("c", gpu, now)
        registry.register(node_a)
        registry.register(node_b)
        registry.register(node_c)
        result = registry.list()
        assert result == [node_a, node_b, node_c]

    def test_list_returns_copy(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        registry.register(_make_node("1", gpu, now))
        list_a = registry.list()
        list_b = registry.list()
        assert list_a is not list_b


class TestUpdate:
    """Tests for node updates."""

    def test_update_existing_node(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("1", gpu, now)
        registry.register(node)
        updated = node.model_copy(update={"queue_length": 5, "status": NodeStatus.BUSY})
        registry.update(updated)
        assert registry.get("1") == updated
        assert registry.get("1") is not None
        assert registry.get("1").queue_length == 5  # type: ignore[union-attr]

    def test_update_missing_node_raises(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        node = _make_node("missing", gpu, now)
        with pytest.raises(ValueError, match="Node not found: missing"):
            registry.update(node)


class TestUnregister:
    """Tests for node removal."""

    def test_unregister_node(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        registry.register(_make_node("1", gpu, now))
        registry.unregister("1")
        assert registry.count() == 0
        assert registry.get("1") is None

    def test_unregister_missing_node_raises(self):
        registry = NodeRegistry()
        with pytest.raises(ValueError, match="Node not found: missing"):
            registry.unregister("missing")


class TestClear:
    """Tests for clearing the registry."""

    def test_clear_removes_all(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        registry.register(_make_node("1", gpu, now))
        registry.register(_make_node("2", gpu, now))
        registry.clear()
        assert registry.count() == 0
        assert registry.list() == []

    def test_clear_empty_registry(self):
        registry = NodeRegistry()
        registry.clear()
        assert registry.count() == 0


class TestCount:
    """Tests for counting nodes."""

    def test_count_increments(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        assert registry.count() == 0
        registry.register(_make_node("1", gpu, now))
        assert registry.count() == 1
        registry.register(_make_node("2", gpu, now))
        assert registry.count() == 2

    def test_count_decrements_on_unregister(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        registry.register(_make_node("1", gpu, now))
        registry.register(_make_node("2", gpu, now))
        registry.unregister("1")
        assert registry.count() == 1


class TestThreadSafety:
    """Basic thread-safety sanity check."""

    def test_concurrent_register(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        errors: list[Exception] = []

        def register_node(node_id: str) -> None:
            try:
                registry.register(_make_node(node_id, gpu, now))
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=register_node, args=(str(i),)) for i in range(100)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert registry.count() == 100

    def test_concurrent_register_and_read(self, gpu: GPUInfo, now: datetime):
        registry = NodeRegistry()
        # Pre-register some nodes
        for i in range(50):
            registry.register(_make_node(f"pre-{i}", gpu, now))

        read_results: list[int] = []
        errors: list[Exception] = []

        def register_node(node_id: str) -> None:
            try:
                registry.register(_make_node(node_id, gpu, now))
            except Exception as e:
                errors.append(e)

        def read_nodes() -> None:
            try:
                read_results.append(len(registry.list()))
            except Exception as e:
                errors.append(e)

        threads: list[threading.Thread] = []
        for i in range(50):
            threads.append(threading.Thread(target=register_node, args=(f"new-{i}",)))
            threads.append(threading.Thread(target=read_nodes))

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        assert registry.count() == 100
