"""Shared test fixtures. Each test module gets a fresh in-memory database."""

from __future__ import annotations

import os
import tempfile

import pytest

# Must be set before app modules import settings.
_tmpdir = tempfile.mkdtemp(prefix="rang-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["IMAGE_PROVIDER"] = "local"
os.environ["RATE_LIMIT_GENERATE"] = "1000/minute"
os.environ["RATE_LIMIT_DEFAULT"] = "1000/minute"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="function")
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def auth_client(client):
    """A client already registered and carrying a bearer token."""
    resp = client.post(
        "/api/auth/register",
        json={
            "email": "tester@rang.pk",
            "display_name": "Tester",
            "password": "supersecret123",
        },
    )
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client
