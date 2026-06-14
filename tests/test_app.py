from fastapi.testclient import TestClient

from ttb_label_reviewer.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"]
    assert body["revision"]


def test_index_serves_html() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "TTB Label Reviewer" in response.text
    assert "Version " in response.text
