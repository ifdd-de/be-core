import os

import pytest

os.environ.setdefault("IFDD_BE_AUTH_ENABLED", "false")
os.environ.setdefault("IFDD_BE_SSL_ENABLED", "false")
os.environ.setdefault("FASTAPI_SECRET_KEY", "test-secret")
os.environ.setdefault(
    "IFDD_SERVICE_DB_URL", "postgresql+psycopg://user:pw@localhost:5432/test"
)


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from ifdd.be.core import create_app
    from ifdd.be.core.config import CoreSettings, reset_settings

    reset_settings()
    app = create_app(CoreSettings())
    with TestClient(app) as test_client:
        yield test_client
