"""POST /api/review endpoint tests — API-free (D-5): the extractor
dependency is overridden with a fake; no model call ever happens here."""

import pytest
from fastapi.testclient import TestClient
from helpers import make_extraction

from ttb_label_reviewer.extraction import ExtractionError
from ttb_label_reviewer.main import app, get_extractor

client = TestClient(app)

FORM = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": "45.0",
    "net_contents": "750 mL",
}


def png_upload(name="front.png", data=b"not-a-real-png"):
    return ("images", (name, data, "image/png"))


class FakeExtractor:
    def __init__(self, extraction=None, error=None):
        self.extraction = extraction
        self.error = error

    def extract(self, images):
        if self.error is not None:
            raise self.error
        return self.extraction


@pytest.fixture
def fake_extractor():
    fake = FakeExtractor(extraction=make_extraction())
    app.dependency_overrides[get_extractor] = lambda: fake
    yield fake
    app.dependency_overrides.clear()


def test_review_returns_contract_shape(fake_extractor):
    response = client.post(
        "/api/review", data=FORM, files=[png_upload(), png_upload("back.png")]
    )
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == "pass"
    # contracts.md §4: counts keyed by outcome, "pass" not "pass_"
    assert set(body["counts"]) == {"fail", "needs_review", "pass", "not_applicable"}
    assert body["counts"]["not_applicable"] == 1  # DS-7, not imported
    assert body["application_id"].startswith("single-")
    rule_ids = [f["rule_id"] for f in body["findings"]]
    assert rule_ids == [
        "DS-1", "DS-2", "DS-3", "DS-4", "DS-5a", "DS-5b",
        "DS-5c", "DS-5d", "DS-6", "DS-7", "DS-8",
    ]  # fmt: skip
    # Evidence is the interface (D-8): expected/actual on passes too.
    ds1 = body["findings"][0]
    assert ds1["expected"] == "OLD TOM DISTILLERY"
    assert ds1["actual"] == "OLD TOM DISTILLERY"


def test_extraction_error_is_visible_502(fake_extractor):
    fake_extractor.error = ExtractionError("the model had a bad day")
    response = client.post("/api/review", data=FORM, files=[png_upload()])
    assert response.status_code == 502
    assert response.json()["detail"] == "the model had a bad day"


def test_unsupported_image_type_is_415(fake_extractor):
    response = client.post(
        "/api/review",
        data=FORM,
        files=[("images", ("label.tiff", b"x", "image/tiff"))],
    )
    assert response.status_code == 415
    assert "label.tiff" in response.json()["detail"]


def test_oversized_image_is_413(fake_extractor):
    big = b"x" * (5 * 1024 * 1024 + 1)
    response = client.post("/api/review", data=FORM, files=[png_upload(data=big)])
    assert response.status_code == 413


def test_too_many_images_is_413(fake_extractor):
    files = [png_upload(f"label-{i}.png") for i in range(9)]
    response = client.post("/api/review", data=FORM, files=files)
    assert response.status_code == 413
    assert "at most 8" in response.json()["detail"]


def test_combined_image_size_over_cap_is_413(fake_extractor):
    # Five 4.2 MB images: each under the per-image cap, 21 MB combined.
    chunk = b"x" * (4_404_019)
    files = [png_upload(f"label-{i}.png", data=chunk) for i in range(5)]
    response = client.post("/api/review", data=FORM, files=files)
    assert response.status_code == 413
    assert "20 MB" in response.json()["detail"]


def test_missing_required_field_is_422(fake_extractor):
    form = {k: v for k, v in FORM.items() if k != "brand_name"}
    response = client.post("/api/review", data=form, files=[png_upload()])
    assert response.status_code == 422


def test_missing_images_is_422(fake_extractor):
    response = client.post("/api/review", data=FORM)
    assert response.status_code == 422


def test_unconfigured_api_key_is_503(monkeypatch):
    # No dependency override: the real get_extractor runs and must refuse
    # clearly when the key is absent — never a crash mid-request.
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post("/api/review", data=FORM, files=[png_upload()])
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.json()["detail"]
