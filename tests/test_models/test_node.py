"""Tests for node representation models."""

import pytest
from pydantic import ValidationError

from scheduler.models.node import GPUInfo, Node


class TestGPUInfo:
    """Tests for the GPUInfo model."""

    def test_valid_construction(self):
        gpu = GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=40.0)
        assert gpu.name == "NVIDIA A100"
        assert gpu.vram_total_gb == 80.0
        assert gpu.vram_available_gb == 40.0

    def test_zero_available_vram(self):
        gpu = GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=0.0)
        assert gpu.vram_available_gb == 0.0

    def test_negative_vram_total_rejected(self):
        with pytest.raises(ValidationError):
            GPUInfo(name="NVIDIA A100", vram_total_gb=-1.0, vram_available_gb=0.0)

    def test_zero_vram_total_rejected(self):
        with pytest.raises(ValidationError):
            GPUInfo(name="NVIDIA A100", vram_total_gb=0.0, vram_available_gb=0.0)

    def test_negative_available_vram_rejected(self):
        with pytest.raises(ValidationError):
            GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=-1.0)

    def test_missing_name_rejected(self):
        with pytest.raises(ValidationError):
            GPUInfo(vram_total_gb=80.0, vram_available_gb=40.0)  # type: ignore[call-arg]


class TestNode:
    """Tests for the Node model."""

    @pytest.fixture()
    def gpu(self) -> GPUInfo:
        return GPUInfo(name="NVIDIA A100", vram_total_gb=80.0, vram_available_gb=60.0)

    def test_full_construction(self, gpu: GPUInfo):
        node = Node(
            node_id="node-001",
            hostname="worker-1",
            ip_address="10.0.0.1",
            region="us-east-1",
            gpu=gpu,
            cpu_cores=32,
            ram_total_gb=128.0,
            available_models=["llama-3-70b", "mistral-7b"],
        )
        assert node.node_id == "node-001"
        assert node.hostname == "worker-1"
        assert node.ip_address == "10.0.0.1"
        assert node.region == "us-east-1"
        assert node.gpu == gpu
        assert node.cpu_cores == 32
        assert node.ram_total_gb == 128.0
        assert node.available_models == ["llama-3-70b", "mistral-7b"]

    def test_defaults(self, gpu: GPUInfo):
        node = Node(
            node_id="node-002",
            hostname="worker-2",
            ip_address="10.0.0.2",
            region="us-west-1",
            gpu=gpu,
            cpu_cores=16,
            ram_total_gb=64.0,
        )
        assert node.available_models == []

    def test_zero_cpu_cores_rejected(self, gpu: GPUInfo):
        with pytest.raises(ValidationError):
            Node(
                node_id="node-003",
                hostname="worker-3",
                ip_address="10.0.0.3",
                region="eu-west-1",
                gpu=gpu,
                cpu_cores=0,
                ram_total_gb=64.0,
            )

    def test_negative_ram_rejected(self, gpu: GPUInfo):
        with pytest.raises(ValidationError):
            Node(
                node_id="node-004",
                hostname="worker-4",
                ip_address="10.0.0.4",
                region="eu-west-1",
                gpu=gpu,
                cpu_cores=8,
                ram_total_gb=-1.0,
            )
