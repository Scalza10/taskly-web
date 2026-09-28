import pytest
from fastapi.testclient import TestClient

from taskly.main import create_app
from taskly.settings import Settings


def make_settings(tmp_path, **overrides) -> Settings:
    """Settings on a fresh database in tmp_path. _env_file=None keeps a local .env out of tests."""
    return Settings(_env_file=None, db_path=str(tmp_path / "taskly.db"), **overrides)


@pytest.fixture
def settings(tmp_path):
    return make_settings(tmp_path)


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client
