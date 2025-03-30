import pytest

from app.main import create_app


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("APP_VERSION", "abc123-20260101T000000Z")
    return create_app().test_client()


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "ok"}


def test_readyz(client):
    assert client.get("/readyz").status_code == 200


def test_index_reports_version(client):
    body = client.get("/").get_json()
    assert body["service"] == "hello-service"
    assert body["version"] == "abc123-20260101T000000Z"
