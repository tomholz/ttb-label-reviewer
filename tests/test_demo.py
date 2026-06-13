"""Demo-data drift tests: the committed sample assets under
static/demo/ are generated from the golden set (golden/build_demo.py);
these tests fail loudly if the goldens are regenerated without
rebuilding the demo, so the index page can never offer stale labels or
wrong what-to-expect numbers."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ttb_label_reviewer.batch import parse_batch_zip
from ttb_label_reviewer.main import app

REPO = Path(__file__).parent.parent
GOLDEN_DIR = REPO / "golden"
DEMO_DIR = REPO / "src" / "ttb_label_reviewer" / "static" / "demo"

client = TestClient(app)


@pytest.fixture(scope="module")
def golden_cases() -> dict[str, dict]:
    manifest = json.loads((GOLDEN_DIR / "manifest.json").read_text())
    return {case["case_id"]: case for case in manifest["cases"]}


@pytest.fixture(scope="module")
def demo() -> dict:
    return json.loads((DEMO_DIR / "demo.json").read_text())


@pytest.fixture(scope="module")
def parsed_zip():
    return parse_batch_zip((DEMO_DIR / "demo-batch.zip").read_bytes())


def test_demo_zip_parses_with_exactly_the_advertised_rows(parsed_zip, demo):
    assert parsed_zip.total == demo["batch"]["rows"]
    assert len(parsed_zip.errors) == demo["batch"]["expected"]["error"]
    # The two broken rows fail for the reasons they were built to show.
    by_id = {error.application_id: error.message for error in parsed_zip.errors}
    assert "'ghost.png' is not in the zip" in by_id["demo-broken-image"]
    assert "is not a number" in by_id["demo-broken-abv"]


def test_demo_zip_rows_match_the_golden_set(parsed_zip, golden_cases):
    for row in parsed_zip.rows:
        application = golden_cases[row.application.application_id]["application"]
        assert row.application.model_dump(mode="json") == application
        for image in row.images:
            assert image.data == (GOLDEN_DIR / image.filename).read_bytes()


def test_advertised_counts_follow_from_golden_expectations(
    parsed_zip, golden_cases, demo
):
    """Recompute fail > needs_review > pass per case from the golden
    manifest's expected outcomes — independently of the build script —
    and compare with what the card advertises."""
    counts = {"fail": 0, "needs_review": 0, "pass": 0}
    for row in parsed_zip.rows:
        expected = golden_cases[row.application.application_id]["expected"]
        outcomes = {
            entry["outcome"]
            for entry in expected.values()
            if entry["outcome"] != "not_applicable"
        }
        if "fail" in outcomes:
            counts["fail"] += 1
        elif "needs_review" in outcomes:
            counts["needs_review"] += 1
        else:
            counts["pass"] += 1
    expected_counts = dict(demo["batch"]["expected"])
    assert counts == {k: v for k, v in expected_counts.items() if k != "error"}


def test_single_samples_match_the_golden_set(demo, golden_cases):
    by_filename = {
        case["application"]["image_filenames"][0]: case["application"]
        for case in golden_cases.values()
        if len(case["application"]["image_filenames"]) == 1
    }
    assert len(demo["singles"]) >= 2
    for sample in demo["singles"]:
        application = by_filename[sample["filename"]]
        for field in ("brand_name", "class_type", "abv_percent", "net_contents"):
            assert sample[field] == application[field], sample["filename"]
        # The downloadable copy is byte-identical to the golden image.
        assert (DEMO_DIR / sample["filename"]).read_bytes() == (
            GOLDEN_DIR / sample["filename"]
        ).read_bytes()


def test_index_offers_the_sample_data(demo):
    page = client.get("/").text
    assert "Try it with sample data" in page
    assert 'href="/static/demo/demo-batch.zip"' in page
    for sample in demo["singles"]:
        assert f'href="/static/demo/{sample["filename"]}"' in page
        assert sample["brand_name"] in page
    # The what-to-expect line carries the generated counts.
    expected = demo["batch"]["expected"]
    assert f"{expected['fail']} fail" in page
    assert f"{expected['error']} row errors" in page
    # And the assets actually serve.
    for path in ["/static/demo/demo-batch.zip", "/static/demo/demo.json"]:
        assert client.get(path).status_code == 200
