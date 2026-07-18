"""Integration tests for the edge ingress gateway and rate-limiting."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from scheduler.core.rate_limiter import TokenBucketLimiter
from scheduler.main import app


@pytest.fixture(scope="module")
def key_pair() -> tuple[rsa.RSAPrivateKey, str]:
    """Generate an RSA key pair for signing and verifying JWTs in tests."""
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key_pem = (
        private_key.public_key()
        .public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )
    return private_key, public_key_pem


@pytest.fixture(autouse=True)
def setup_test_app(key_pair: tuple[rsa.RSAPrivateKey, str]) -> MagicMock:
    """Configure the FastAPI app state with test keys and mock consensus engine."""
    _, public_key_pem = key_pair
    app.state.jwt_public_key = public_key_pem

    # Reset rate limiter
    app.state.rate_limiter = TokenBucketLimiter(capacity=5, refill_rate=0.5)

    # Set up mock consensus engine
    mock_consensus = MagicMock()
    mock_consensus.is_active.return_value = True
    mock_consensus.propose = AsyncMock()
    app.state.registry.consensus_engine = mock_consensus
    return mock_consensus


def generate_token(
    private_key: rsa.RSAPrivateKey, tenant_id: str | None, expired: bool = False
) -> str:
    """Generate a signed JWT for testing."""
    payload = {
        "sub": "client-user",
        "iat": datetime.now(UTC),
        "exp": datetime.now(UTC) + timedelta(minutes=10)
        if not expired
        else datetime.now(UTC) - timedelta(minutes=10),
    }
    if tenant_id is not None:
        payload["tenant_id"] = tenant_id

    return jwt.encode(payload, private_key, algorithm="RS256")


def test_ingress_submit_invalid_auth(
    key_pair: tuple[rsa.RSAPrivateKey, str],
) -> None:
    """Verify that requests with invalid authentication are rejected with 401."""
    client = TestClient(app)
    task_payload = {"task_id": "task-1", "action": "test_action", "data": {}}

    # 1. No Authorization Header
    response = client.post("/api/v1/tasks/submit", json=task_payload)
    assert response.status_code == 422 or response.status_code == 401

    # 2. Malformed Header format
    response = client.post(
        "/api/v1/tasks/submit",
        json=task_payload,
        headers={"Authorization": "BearerInvalidToken"},
    )
    assert response.status_code == 401
    assert "Invalid Authorization header format" in response.json()["detail"]

    # 3. Invalid signature (signed with different key)
    other_private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    invalid_token = generate_token(other_private_key, tenant_id="tenant-A")
    response = client.post(
        "/api/v1/tasks/submit",
        json=task_payload,
        headers={"Authorization": f"Bearer {invalid_token}"},
    )
    assert response.status_code == 401
    assert "JWT signature verification failed" in response.json()["detail"]

    # 4. Token missing tenant_id claim
    private_key, _ = key_pair
    no_tenant_token = generate_token(private_key, tenant_id=None)
    response = client.post(
        "/api/v1/tasks/submit",
        json=task_payload,
        headers={"Authorization": f"Bearer {no_tenant_token}"},
    )
    assert response.status_code == 401
    assert "Missing 'tenant_id'" in response.json()["detail"]


def test_ingress_submit_authorized_handoff(
    key_pair: tuple[rsa.RSAPrivateKey, str], setup_test_app: MagicMock
) -> None:
    """Verify that authorized requests pass JWT verification and forward to consensus."""
    private_key, _ = key_pair
    mock_consensus = setup_test_app
    token = generate_token(private_key, tenant_id="tenant-A")

    client = TestClient(app)
    task_payload = {
        "task_id": "task-abc",
        "action": "replicate_model",
        "data": {"model_name": "llama3"},
    }

    response = client.post(
        "/api/v1/tasks/submit",
        json=task_payload,
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "committed", "task_id": "task-abc"}
    mock_consensus.propose.assert_called_once_with("replicate_model", {"model_name": "llama3"})


def test_ingress_token_bucket_rate_limiter(
    key_pair: tuple[rsa.RSAPrivateKey, str],
) -> None:
    """Verify rate-limiting triggers HTTP 429 when burst capacity is exceeded."""
    private_key, _ = key_pair
    client = TestClient(app)
    token_a = generate_token(private_key, tenant_id="tenant-A")
    token_b = generate_token(private_key, tenant_id="tenant-B")

    task_payload = {"task_id": "task-1", "action": "test_action", "data": {}}

    # Flood tenant-A (burst capacity = 5)
    for i in range(5):
        response = client.post(
            "/api/v1/tasks/submit",
            json=task_payload,
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert response.status_code == 200, f"Request {i + 1} failed"

    # 6th request from tenant-A should trigger rate limit (429)
    response_429 = client.post(
        "/api/v1/tasks/submit",
        json=task_payload,
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert response_429.status_code == 429
    assert "Rate limit exceeded" in response_429.json()["detail"]

    # Verify multi-tenant isolation: tenant-B is not affected by tenant-A's exhaust
    response_b = client.post(
        "/api/v1/tasks/submit",
        json=task_payload,
        headers={"Authorization": f"Bearer {token_b}"},
    )
    assert response_b.status_code == 200
