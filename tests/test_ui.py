"""Single review UI tests (milestone 4) — API-free (D-5): the extractor
dependency is overridden with a fake, mirroring test_api.py. These tests
pin the UI contract: form present, results fragment carries verdict +
counts + evidence, DS-5a renders a character diff, and every error path
produces a visible fragment rather than silent JSON."""

import re

import pytest
from fastapi.testclient import TestClient
from helpers import WARNING_ON_LABEL, field, make_application, make_extraction, warning

from ttb_label_reviewer.engine import review
from ttb_label_reviewer.extraction import ExtractionError
from ttb_label_reviewer.main import app, get_extractor, templates

client = TestClient(app)

FORM = {
    "brand_name": "OLD TOM DISTILLERY",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": "45.0",
    "net_contents": "750 mL",
}

# htmx sends this on every request it makes; the error handlers key on it.
HTMX_HEADERS = {"HX-Request": "true"}


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


def test_index_serves_the_form():
    response = client.get("/")
    assert response.status_code == 200
    page = response.text
    # The form posts to the UI endpoint via htmx with multipart encoding.
    assert 'aria-label="Review workflow"' in page
    assert 'href="#single-workflow">Review one label</a>' in page
    assert 'href="#batch-workflow">Review a batch</a>' in page
    assert 'id="single-workflow"' in page
    assert 'id="batch-workflow"' in page
    assert 'hx-post="/review"' in page
    assert 'hx-encoding="multipart/form-data"' in page
    for field_name in (
        "beverage_type",
        "brand_name",
        "class_type",
        "abv_percent",
        "net_contents",
        "imported",
        "images",
    ):
        assert f'name="{field_name}"' in page
    for value in ("distilled_spirits", "wine", "malt_beverage"):
        assert f'value="{value}"' in page
    # Vendored assets only (D-10.3): no CDN URLs anywhere on the page.
    assert 'src="/static/htmx.min.js"' in page
    assert "http://" not in page and "https://" not in page
    # The upload limits enforced in main.py are stated in the form hint.
    assert "Up to 8 images" in page
    assert 'id="results"' in page
    assert "hx-on::htmx:after-settle" in page
    assert "firstElementChild" in page
    assert "scrollIntoView({ block: 'start' })" in page
    assert 'hx-post="/review/sample"' in page
    assert "Run this sample" in page
    assert "Try the batch sample" in page


def test_vendored_assets_are_served():
    for path, marker in [
        ("/static/htmx.min.js", "htmx"),
        ("/static/style.css", ".verdict"),
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert marker in response.text


def test_favicon_is_served():
    # The default browser request must not 404 (it was the only console
    # noise on the page); modern browsers get the SVG via the link tag.
    response = client.get("/favicon.ico")
    assert response.status_code == 200
    assert response.content[:4] == b"\x00\x00\x01\x00"  # ICO magic
    assert 'rel="icon" href="/static/favicon.svg"' in client.get("/").text
    assert client.get("/static/favicon.svg").status_code == 200


def test_review_renders_verdict_counts_and_evidence(fake_extractor):
    response = client.post(
        "/review",
        data=FORM,
        files=[png_upload(), png_upload("back.png")],
        headers=HTMX_HEADERS,
    )
    assert response.status_code == 200
    page = response.text
    assert 'class="card results-card" tabindex="-1"' in page
    assert '<h2 id="review-result-heading">Review result</h2>' in page
    assert "verdict-pass" in page
    assert "Distilled spirits coverage" in page
    # Counts line: 12 checks, 10 evaluated, DS-7 n/a, DS-SCOPE not evaluated.
    assert "12 checks: 10 evaluated" in page
    assert "1 not applicable" in page
    # Evidence is the interface (D-8): expected/actual visible on passes.
    assert page.count("OLD TOM DISTILLERY") >= 2
    assert "27 CFR 5.63, 5.64" in page
    # All eleven rules appear, in checklist order.
    for rule_id in (
        "DS-1",
        "DS-2",
        "DS-3",
        "DS-4",
        "DS-5a",
        "DS-5b",
        "DS-5c",
        "DS-5d",
        "DS-6",
        "DS-7",
        "DS-8",
        "DS-SCOPE",
    ):
        assert rule_id in page


def test_sample_review_renders_normal_results_fragment(fake_extractor):
    fake_extractor.extraction = make_extraction(brand_name=field("OLD TOM RESERVE"))

    response = client.post(
        "/review/sample",
        data={"sample": "compliant.png"},
        headers=HTMX_HEADERS,
    )

    assert response.status_code == 200
    page = response.text
    assert 'class="card results-card" tabindex="-1"' in page
    assert '<h2 id="review-result-heading">Review result</h2>' in page
    assert "verdict-pass" in page
    assert "Distilled spirits coverage" in page


def test_unknown_sample_review_is_visible_fragment(fake_extractor):
    response = client.post(
        "/review/sample",
        data={"sample": "../manifest.json"},
        headers=HTMX_HEADERS,
    )

    assert response.status_code == 404
    assert 'class="card error-card" role="alert" tabindex="-1"' in response.text
    assert "Sample not found" in response.text


def test_wine_review_renders_partial_coverage_language(fake_extractor):
    form = dict(
        FORM,
        beverage_type="wine",
        brand_name="SUNSET CELLARS",
        class_type="Table Wine",
        abv_percent="12.0",
    )
    fake_extractor.extraction = make_extraction(
        brand_name={"raw": "SUNSET CELLARS", "confidence": 0.97},
        class_type={"raw": "Table Wine", "confidence": 0.97},
        alcohol_content=None,
        proof=None,
    )

    response = client.post(
        "/review", data=form, files=[png_upload()], headers=HTMX_HEADERS
    )

    assert response.status_code == 200
    page = response.text
    assert "Partial coverage" in page
    assert "No issue found in checked rules" in page
    assert "Partial coverage &mdash; wine" in page
    assert "This is not a finding of full" in page
    assert "1 not evaluated" in page
    assert "Not evaluated" in page
    assert "WN-SCOPE" in page
    assert "12% alcohol by volume" not in page


def test_batch_row_renders_coverage_and_not_evaluated_count():
    result = review(
        make_application(
            application_id="wine-row",
            beverage_type="wine",
            brand_name="SUNSET CELLARS",
            class_type="Table Wine",
            abv_percent=12.0,
        ),
        make_extraction(
            brand_name=field("SUNSET CELLARS"),
            class_type=field("Table Wine"),
            alcohol_content=None,
            proof=None,
        ),
    )

    page = templates.env.get_template("partials/batch_row.html").render(result=result)

    assert "Partial coverage" in page
    assert "No issue found in checked rules" in page
    assert "1 not evaluated" in page
    assert "WN-SCOPE" in page


def test_ds5a_deviation_renders_character_diff(fake_extractor):
    deviant = WARNING_ON_LABEL.replace("birth defects", "fetal harm")
    fake_extractor.extraction = make_extraction(
        government_warning=warning(raw_text=deviant)
    )
    response = client.post(
        "/review", data=FORM, files=[png_upload()], headers=HTMX_HEADERS
    )
    assert response.status_code == 200
    page = response.text
    assert "verdict-fail" in page
    assert "<del>" in page and "<ins>" in page
    # The diff spans concatenate to the full strings: with markup stripped,
    # both the required wording and the deviant wording read out whole.
    text = re.sub(r"<[^>]+>", "", page)
    assert "birth defects" in text
    assert "fetal harm" in text


def test_extracted_text_is_html_escaped(fake_extractor):
    fake_extractor.extraction = make_extraction(
        brand_name={"raw": "<script>alert(1)</script>", "confidence": 0.97}
    )
    response = client.post(
        "/review", data=FORM, files=[png_upload()], headers=HTMX_HEADERS
    )
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_extraction_error_is_visible_fragment(fake_extractor):
    fake_extractor.error = ExtractionError("the model had a bad day")
    response = client.post(
        "/review", data=FORM, files=[png_upload()], headers=HTMX_HEADERS
    )
    assert response.status_code == 502
    assert 'class="card error-card" role="alert" tabindex="-1"' in response.text
    assert "Review could not be completed" in response.text
    assert "the model had a bad day" in response.text


def test_too_many_images_is_visible_fragment(fake_extractor):
    files = [png_upload(f"label-{i}.png") for i in range(9)]
    response = client.post("/review", data=FORM, files=files, headers=HTMX_HEADERS)
    assert response.status_code == 413
    assert "Review could not be completed" in response.text
    assert "at most 8" in response.text


def test_unsupported_image_type_is_visible_fragment(fake_extractor):
    response = client.post(
        "/review",
        data=FORM,
        files=[("images", ("label.tiff", b"x", "image/tiff"))],
        headers=HTMX_HEADERS,
    )
    assert response.status_code == 415
    assert "Review could not be completed" in response.text
    assert "label.tiff" in response.text


def test_validation_error_is_visible_fragment(fake_extractor):
    form = dict(FORM, abv_percent="not-a-number")
    response = client.post(
        "/review", data=form, files=[png_upload()], headers=HTMX_HEADERS
    )
    assert response.status_code == 422
    assert "Review could not be completed" in response.text
    assert "abv_percent" in response.text


def test_unconfigured_api_key_is_visible_fragment(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    response = client.post(
        "/review", data=FORM, files=[png_upload()], headers=HTMX_HEADERS
    )
    assert response.status_code == 503
    assert "Review could not be completed" in response.text
    assert "ANTHROPIC_API_KEY" in response.text


def test_api_errors_stay_json_without_htmx_header(fake_extractor):
    """Non-htmx callers (the JSON API) keep FastAPI's error shape."""
    fake_extractor.error = ExtractionError("boom")
    response = client.post("/api/review", data=FORM, files=[png_upload()])
    assert response.status_code == 502
    assert response.json()["detail"] == "boom"
