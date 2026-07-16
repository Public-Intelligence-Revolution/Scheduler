#!/usr/bin/env python3
"""Interactive terminal demonstration of the Public Intelligence Scheduler."""

import sys
import time
from datetime import UTC, datetime
from pathlib import Path

# Add src/ to Python path if running locally
src_path = str(Path(__file__).parent.parent / "src")
if src_path not in sys.path:
    sys.path.insert(0, src_path)

from scheduler.models.heartbeat import Heartbeat
from scheduler.models.node import GPUInfo, Node, NodeStatus
from scheduler.registry.node_registry import NodeRegistry
from scheduler.scheduler.algorithm import Scheduler


def print_title(text: str) -> None:
    print("\n" + "=" * 60)
    print(f"        {text}")
    print("=" * 60)


def print_section(text: str) -> None:
    print(f"\n>>> {text}")
    print("-" * 60)


def format_node(node: Node) -> str:
    models_str = "\n".join(f"  - {m}" for m in node.available_models)
    return (
        f"Node ID: {node.node_id} (Hostname: {node.hostname})\n"
        f"Region:  {node.region} | IP: {node.ip_address}\n"
        f"GPU:     {node.gpu.name} ({node.gpu.vram_total_gb} GB VRAM)\n"
        f"CPU:     {node.cpu_cores} Cores | RAM: {node.ram_total_gb} GB\n"
        f"Models:\n{models_str}"
    )


def format_heartbeat(hb: Heartbeat) -> str:
    return (
        f"Status:          {hb.status.name}\n"
        f"Queue Length:    {hb.queue_length}\n"
        f"CPU Utilization: {hb.cpu_utilization}%\n"
        f"GPU Utilization: {hb.gpu_utilization}%\n"
        f"VRAM Available:  {hb.vram_available_gb} GB"
    )


def main() -> None:
    # Set up registry and scheduler
    registry = NodeRegistry()
    scheduler = Scheduler(registry)

    print_title("PUBLIC INTELLIGENCE SCHEDULER DEMO")
    time.sleep(1)

    # ==================================================
    # STEP 1 — NODE REGISTRATION
    # ==================================================
    print_section("STEP 1 — NODE REGISTRATION")
    time.sleep(1)

    node_a = Node(
        node_id="Node-A",
        hostname="worker-a-4090",
        ip_address="10.0.0.10",
        region="us-east",
        gpu=GPUInfo(name="RTX 4090", vram_total_gb=24.0, vram_available_gb=24.0),
        cpu_cores=16,
        ram_total_gb=64.0,
        available_models=["llama3-8b", "mistral-7b"],
    )

    node_b = Node(
        node_id="Node-B",
        hostname="worker-b-3090",
        ip_address="10.0.0.11",
        region="us-west",
        gpu=GPUInfo(name="RTX 3090", vram_total_gb=24.0, vram_available_gb=24.0),
        cpu_cores=12,
        ram_total_gb=32.0,
        available_models=["gemma-7b"],
    )

    node_c = Node(
        node_id="Node-C",
        hostname="worker-c-a100",
        ip_address="10.0.0.12",
        region="eu-west",
        gpu=GPUInfo(name="A100", vram_total_gb=80.0, vram_available_gb=80.0),
        cpu_cores=32,
        ram_total_gb=128.0,
        available_models=["llama3-70b", "llama3-8b"],
    )

    for node in [node_a, node_b, node_c]:
        print(f"Creating Node {node.node_id}...")
        print(format_node(node))
        print("-" * 40)
        time.sleep(0.5)

    print("\nRegistering nodes with NodeRegistry...")
    time.sleep(0.8)
    for node in [node_a, node_b, node_c]:
        registry.register(node)
        print(f"✓ Registered {node.node_id}")
        time.sleep(0.5)

    # ==================================================
    # STEP 2 — HEARTBEATS
    # ==================================================
    print_section("STEP 2 — HEARTBEATS")
    time.sleep(1)

    now = datetime.now(tz=UTC)

    hb_a = Heartbeat(
        node_id="Node-A",
        timestamp=now,
        status=NodeStatus.ONLINE,
        queue_length=2,
        cpu_utilization=11.0,
        ram_available_gb=48.0,
        gpu_utilization=18.0,
        vram_available_gb=21.0,
    )

    hb_b = Heartbeat(
        node_id="Node-B",
        timestamp=now,
        status=NodeStatus.ONLINE,
        queue_length=11,
        cpu_utilization=74.0,
        ram_available_gb=8.0,
        gpu_utilization=87.0,
        vram_available_gb=6.0,
    )

    hb_c = Heartbeat(
        node_id="Node-C",
        timestamp=now,
        status=NodeStatus.ONLINE,
        queue_length=0,
        cpu_utilization=5.0,
        ram_available_gb=120.0,
        gpu_utilization=10.0,
        vram_available_gb=75.0,
    )

    for hb in [hb_a, hb_b, hb_c]:
        print(f"Updating dynamic state for {hb.node_id}...")
        print(format_heartbeat(hb))
        registry.update_heartbeat(hb)
        print(f"✓ Updated heartbeat for {hb.node_id}")
        print("-" * 40)
        time.sleep(0.5)

    # ==================================================
    # STEP 3 — SCHEDULING REQUESTS
    # ==================================================
    print_section("STEP 3 — SCHEDULING REQUESTS")
    time.sleep(1)

    requests = [
        "llama3-8b",
        "gemma-7b",
        "gpt-5",
    ]

    for idx, model in enumerate(requests, start=1):
        print(f"\n--- Request {idx}: Model '{model}' ---")
        time.sleep(1.0)

        # Walk through selection process manually to explain to the user
        for node in [node_a, node_b, node_c]:
            print(f"Checking {node.node_id}...")
            time.sleep(0.4)

            # Check model support
            if model not in node.available_models:
                print(f"  ✗ Model unavailable on {node.node_id}")
                print("-" * 25)
                continue
            print("  ✓ Model available")

            # Check heartbeat
            hb = registry.get_heartbeat(node.node_id)
            if hb is None:
                print("  ✗ Heartbeat missing")
                print("-" * 25)
                continue
            print("  ✓ Heartbeat present")

            # Check status
            if hb.status == NodeStatus.OFFLINE:
                print("  ✗ Node is OFFLINE")
                print("-" * 25)
                continue
            print("  ✓ Node is ONLINE")

            # Compute score
            score = (
                (hb.queue_length * 0.5)
                + (hb.gpu_utilization * 0.3)
                + (hb.cpu_utilization * 0.1)
                - (hb.vram_available_gb * 0.1)
            )
            print("  * Score Calculation:")
            print(
                f"    (queue_length * 0.5)     = {hb.queue_length} * 0.5  = {hb.queue_length * 0.5:.2f}"
            )
            print(
                f"    + (gpu_utilization * 0.3) = {hb.gpu_utilization} * 0.3 = {hb.gpu_utilization * 0.3:.2f}"
            )
            print(
                f"    + (cpu_utilization * 0.1) = {hb.cpu_utilization} * 0.1 = {hb.cpu_utilization * 0.1:.2f}"
            )
            print(
                f"    - (vram_available_gb * 0.1) = {hb.vram_available_gb} * 0.1 = {hb.vram_available_gb * 0.1:.2f}"
            )
            print(f"    Total Score: {score:.2f}")
            print("-" * 25)

        time.sleep(0.8)
        try:
            winner = scheduler.select_node(model)
            print(f"\nWinner: {winner.node_id}")
            print("Reason: Lowest scheduler score.")
        except ValueError as e:
            print(f"\nNo eligible node found: {e}")

    # ==================================================
    # END
    # ==================================================
    print("\n" + "=" * 60)
    print("Scheduler Demonstration Complete")
    print("\nSummary:")
    print("✓ Node Registration")
    print("✓ Heartbeats")
    print("✓ Scheduling")
    print("✓ Deterministic Selection")
    print("\nScheduler v1 Successfully Demonstrated")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
