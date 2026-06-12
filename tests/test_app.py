from fastapi.testclient import TestClient

from ttb_label_reviewer.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_serves_html() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "TTB Label Reviewer" in response.text
