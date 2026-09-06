import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


os.environ["VEDIOGEN_DATABASE_URL"] = "sqlite:///./.data/vediogen-test.db"
os.environ["VEDIOGEN_DATA_DIR"] = "./.data/test"

from vediogen_api.database import Base, engine  # noqa: E402
from vediogen_api.main import app  # noqa: E402


@pytest.fixture(scope="session")
def client():
    Base.metadata.drop_all(engine)
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(engine)
    engine.dispose()
    test_db = Path(".data/vediogen-test.db")
    if test_db.exists():
        test_db.unlink()
