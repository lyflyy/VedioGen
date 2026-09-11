import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


os.environ["VEDIOGEN_DATABASE_URL"] = "sqlite:///./.data/vediogen-test.db"
os.environ["VEDIOGEN_DATA_DIR"] = "./.data/test"
os.environ["VEDIOGEN_ALLOW_FAKE_PROVIDER"] = "true"
os.environ["VEDIOGEN_ALLOW_EXTERNAL_MODELS"] = "false"
os.environ["VEDIOGEN_ALLOW_EXTERNAL_SEARCH"] = "false"
os.environ["VEDIOGEN_ALLOW_LOCAL_MODELS"] = "false"

from vediogen_api.database import Base, engine  # noqa: E402
from vediogen_api.main import app  # noqa: E402


@pytest.fixture(autouse=True)
def deny_live_search(monkeypatch):
    from ddgs.http_client import HttpClient

    def deny(*args, **kwargs):
        raise AssertionError("Live search is prohibited in API tests")

    monkeypatch.setattr(HttpClient, "request", deny)


@pytest.fixture
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
    engine.dispose()
    test_db = Path(".data/vediogen-test.db")
    if test_db.exists():
        test_db.unlink()
