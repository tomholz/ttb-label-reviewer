"""Batch flow tests (milestone 6) — API-free (D-5), in two layers:
the pure zip/CSV parser (contracts.md §2 rule by rule), then the
endpoints with a fake extractor, streaming real SSE events end to end."""

import csv
import io
import re
import zipfile

import pytest
from fastapi.testclient import TestClient
from helpers import WARNING_ON_LABEL, field, make_extraction, warning

from ttb_label_reviewer import limits
from ttb_label_reviewer.batch import (
    MANIFEST_COLUMNS,
    TEMPLATE_CSV,
    BatchError,
    BatchRow,
    RowError,
    parse_batch_zip,
)
from ttb_label_reviewer.main import app, get_extractor

# Real magic bytes, fake payloads: the parser sniffs formats, it never
# decodes pixels.
PNG = b"\x89PNG\r\n\x1a\nnot-real-pixels"
JPEG = b"\xff\xd8\xffnot-real-pixels"

HEADER = ",".join(MANIFEST_COLUMNS)

# A manifest row matching helpers.make_extraction()'s compliant label.
OLD_TOM = (
    "{app_id},distilled_spirits,OLD TOM DISTILLERY,"
    "Kentucky Straight Bourbon Whiskey,45.0,750 mL,{imported},{images}"
)


def old_tom_row(app_id="app-001", imported="false", images="front.png"):
    return OLD_TOM.format(app_id=app_id, imported=imported, images=images)


def make_zip(files: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, data in files.items():
            zf.writestr(name, data)
    return buffer.getvalue()


def make_batch(rows: list[str], images: dict[str, bytes], header=HEADER) -> bytes:
    manifest = "\n".join([header, *rows]) + "\n"
    return make_zip({"manifest.csv": manifest.encode(), **images})


# --- Parser: happy path ---


def test_parses_rows_with_multi_image_and_defaults():
    data = make_batch(
        [
            old_tom_row("app-001", images="front.png;back.png"),
            old_tom_row("app-002", imported="TRUE", images="other.jpg"),
        ],
        {"front.png": PNG, "back.png": PNG, "other.jpg": JPEG},
    )
    parsed = parse_batch_zip(data)
    assert parsed.errors == []
    assert parsed.total == 2
    first, second = parsed.rows
    assert isinstance(first, BatchRow)
    assert first.application.application_id == "app-001"
    assert first.application.brand_name == "OLD TOM DISTILLERY"
    assert first.application.abv_percent == 45.0
    assert first.application.imported is False
    assert [i.filename for i in first.images] == ["front.png", "back.png"]
    assert first.images[0].media_type == "image/png"
    # imported is case-insensitive (contracts.md §2); formats are sniffed.
    assert second.application.imported is True
    assert second.images[0].media_type == "image/jpeg"


def test_column_order_is_irrelevant_and_bom_tolerated():
    manifest = (
        "\ufeff"  # Excel's idea of UTF-8 starts with a BOM
        "image_filenames,brand_name,abv_percent,application_id,"
        "net_contents,class_type,beverage_type\n"
        "front.png,OLD TOM DISTILLERY,45.0,app-001,750 mL,"
        "Kentucky Straight Bourbon Whiskey,distilled_spirits\n"
    )
    data = make_zip({"manifest.csv": manifest.encode(), "front.png": PNG})
    parsed = parse_batch_zip(data)
    assert parsed.errors == []
    # `imported` column absent entirely: optional, defaults to false.
    assert parsed.rows[0].application.imported is False


def test_zipped_folder_resolves_images_next_to_manifest():
    """macOS 'compress folder' shape: everything under one directory,
    plus __MACOSX metadata, which must not count as a second manifest."""
    manifest = HEADER + "\n" + old_tom_row() + "\n"
    data = make_zip(
        {
            "batch/manifest.csv": manifest.encode(),
            "batch/front.png": PNG,
            "__MACOSX/manifest.csv": b"resource-fork-noise",
        }
    )
    parsed = parse_batch_zip(data)
    assert parsed.errors == []
    assert parsed.rows[0].images[0].filename == "front.png"


def test_template_round_trips_through_the_parser_contract():
    rows = list(csv.DictReader(io.StringIO(TEMPLATE_CSV)))
    assert list(rows[0].keys()) == list(MANIFEST_COLUMNS)
    assert len(rows) == 1
    data = make_zip(
        {"manifest.csv": TEMPLATE_CSV.encode(), "front.png": PNG, "back.png": PNG}
    )
    parsed = parse_batch_zip(data)
    assert parsed.errors == []
    assert parsed.rows[0].application.application_id == "app-001"


# --- Parser: row-level errors (fail the row, never the batch) ---


def row_error_of(data: bytes) -> RowError:
    parsed = parse_batch_zip(data)
    assert parsed.rows == []
    assert len(parsed.errors) == 1
    return parsed.errors[0]


def test_image_missing_from_zip_is_row_error():
    error = row_error_of(make_batch([old_tom_row(images="ghost.png")], {}))
    assert error.row_number == 2
    assert error.application_id == "app-001"
    assert "'ghost.png' is not in the zip" in error.message


def test_row_problems_are_collected_into_one_message():
    row = (
        ",distilled_spirits,,Kentucky Straight Bourbon Whiskey,"
        "45% Alc./Vol.,750 mL,maybe,front.png"
    )
    error = row_error_of(make_batch([row], {"front.png": PNG}))
    for fragment in (
        "application_id is blank",
        "brand_name is blank",
        "abv_percent '45% Alc./Vol.' is not a number",
        "imported 'maybe' is not true/false",
    ):
        assert fragment in error.message


def test_unsupported_beverage_type_is_row_error():
    row = old_tom_row().replace("distilled_spirits", "wine")
    error = row_error_of(make_batch([row], {"front.png": PNG}))
    assert "beverage_type 'wine' is not supported" in error.message


def test_unrecognized_image_bytes_is_row_error():
    error = row_error_of(make_batch([old_tom_row()], {"front.png": b"plain text"}))
    assert "not a supported format" in error.message


def test_too_many_images_is_row_error():
    names = ";".join(f"i{n}.png" for n in range(limits.MAX_IMAGES_PER_SET + 1))
    images = {f"i{n}.png": PNG for n in range(limits.MAX_IMAGES_PER_SET + 1)}
    error = row_error_of(make_batch([old_tom_row(images=names)], images))
    assert f"at most {limits.MAX_IMAGES_PER_SET}" in error.message


def test_oversized_image_is_row_error(monkeypatch):
    monkeypatch.setattr(limits, "MAX_IMAGE_BYTES", 10)
    error = row_error_of(make_batch([old_tom_row()], {"front.png": PNG}))
    assert "exceeds the 5 MB limit" in error.message


def test_bad_row_never_aborts_the_batch():
    data = make_batch(
        [old_tom_row("app-001"), old_tom_row("app-002", images="ghost.png")],
        {"front.png": PNG},
    )
    parsed = parse_batch_zip(data)
    assert len(parsed.rows) == 1
    assert len(parsed.errors) == 1
    assert parsed.errors[0].row_number == 3
    assert parsed.total == 2


# --- Parser: batch-level errors (abort the upload, tell the user) ---


def test_not_a_zip_is_batch_error():
    with pytest.raises(BatchError, match="not a readable zip"):
        parse_batch_zip(b"definitely not a zip")


def test_missing_manifest_is_batch_error():
    with pytest.raises(BatchError, match="does not contain a manifest.csv"):
        parse_batch_zip(make_zip({"front.png": PNG}))


def test_two_manifests_is_batch_error():
    files = {
        "manifest.csv": b"application_id\n",
        "extra/manifest.csv": b"application_id\n",
    }
    with pytest.raises(BatchError, match="more than one manifest.csv"):
        parse_batch_zip(make_zip(files))


def test_missing_required_columns_is_batch_error():
    data = make_zip({"manifest.csv": b"application_id,brand_name\napp-1,X\n"})
    with pytest.raises(BatchError, match="missing required column"):
        parse_batch_zip(data)


def test_header_only_manifest_is_batch_error():
    with pytest.raises(BatchError, match="no application rows"):
        parse_batch_zip(make_zip({"manifest.csv": (HEADER + "\n").encode()}))


def test_non_utf8_manifest_is_batch_error():
    manifest = (HEADER + "\n" + old_tom_row()).encode("utf-16")
    with pytest.raises(BatchError, match="not valid UTF-8"):
        parse_batch_zip(make_zip({"manifest.csv": manifest, "front.png": PNG}))


def test_too_many_rows_is_batch_error(monkeypatch):
    monkeypatch.setattr(limits, "MAX_BATCH_ROWS", 2)
    rows = [old_tom_row(f"app-{n}") for n in range(3)]
    with pytest.raises(BatchError, match="at most 2"):
        parse_batch_zip(make_batch(rows, {"front.png": PNG}))


def test_uncompressed_size_guard_is_batch_error(monkeypatch):
    monkeypatch.setattr(limits, "MAX_BATCH_UNCOMPRESSED_BYTES", 10)
    with pytest.raises(BatchError, match="expands to more than"):
        parse_batch_zip(make_batch([old_tom_row()], {"front.png": PNG}))


# --- Endpoints + SSE stream ---

HTMX_HEADERS = {"HX-Request": "true"}


class KeyedExtractor:
    """Returns a canned extraction selected by the row's first image
    filename, so one batch can exercise every verdict group."""

    def __init__(self, by_filename):
        self.by_filename = by_filename

    def extract(self, images):
        return self.by_filename[images[0].filename]


@pytest.fixture
def client():
    # Context-managed so every request in a test shares one event loop:
    # the POST /batch runner task must still be alive when the test
    # connects to the SSE stream.
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_extractor(extractor):
    app.dependency_overrides[get_extractor] = lambda: extractor


def sse_events(text: str) -> list[tuple[int, str, str]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.split("\n")
        events.append(
            (
                int(lines[0].removeprefix("id: ")),
                lines[1].removeprefix("event: "),
                "\n".join(line.removeprefix("data: ") for line in lines[2:]),
            )
        )
    return events


def post_mixed_batch(client) -> str:
    """Three reviewable rows (pass / needs_review / fail) plus one row
    error; returns the started job's id."""
    use_extractor(
        KeyedExtractor(
            {
                "pass.png": make_extraction(),
                "review.png": make_extraction(brand_name=field("Old Tom Distillery")),
                "fail.png": make_extraction(
                    government_warning=warning(
                        raw_text=WARNING_ON_LABEL.replace("birth defects", "fetal harm")
                    )
                ),
            }
        )
    )
    data = make_batch(
        [
            old_tom_row("app-pass", images="pass.png"),
            old_tom_row("app-review", images="review.png"),
            old_tom_row("app-fail", images="fail.png"),
            old_tom_row("app-broken", images="ghost.png"),
        ],
        {"pass.png": PNG, "review.png": PNG, "fail.png": PNG},
    )
    response = client.post(
        "/batch",
        files={"batch_zip": ("batch.zip", data, "application/zip")},
        headers=HTMX_HEADERS,
    )
    assert response.status_code == 200
    match = re.search(r'sse-connect="/batch/([^/"]+)/events"', response.text)
    assert match, response.text
    # The fragment carries the grouped skeleton, worst-first.
    assert response.text.index('sse-swap="row-error"') < response.text.index(
        'sse-swap="row-fail"'
    )
    assert response.text.index('sse-swap="row-fail"') < response.text.index(
        'sse-swap="row-needs_review"'
    )
    assert response.text.index('sse-swap="row-needs_review"') < response.text.index(
        'sse-swap="row-pass"'
    )
    return match.group(1)


def test_template_download(client):
    response = client.get("/batch/template")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert 'filename="manifest.csv"' in response.headers["content-disposition"]
    assert response.text == TEMPLATE_CSV


def test_batch_streams_rows_into_verdict_groups(client):
    job_id = post_mixed_batch(client)
    with client.stream("GET", f"/batch/{job_id}/events") as response:
        assert response.headers["content-type"].startswith("text/event-stream")
        events = sse_events("".join(response.iter_text()))

    names = [name for _, name, _ in events]
    assert names.count("row-pass") == 1
    assert names.count("row-needs_review") == 1
    assert names.count("row-fail") == 1
    assert names.count("row-error") == 1
    assert names[-1] == "done"
    # Event ids are the replay cursor: contiguous from 0.
    assert [event_id for event_id, _, _ in events] == list(range(len(events)))

    by_name = {name: data for _, name, data in events}
    assert "app-pass" in by_name["row-pass"]
    assert "app-fail" in by_name["row-fail"]
    # Evidence travels with the row (D-8): the DS-5a diff is in the
    # fragment. The diff interleaves <ins>/equal spans, so strip markup
    # before asserting the deviant wording reads out whole.
    assert "fetal harm" in re.sub(r"<[^>]+>", "", by_name["row-fail"])
    assert "app-broken" in by_name["row-error"]
    assert "ghost.png" in by_name["row-error"]
    # The last counts event is the terminal summary.
    final_counts = [data for _, name, data in events if name == "counts"][-1]
    assert "Batch complete" in final_counts
    assert "1 fail" in final_counts
    assert "1 needs review" in final_counts
    assert "1 pass" in final_counts
    assert "1 row error" in final_counts


def test_stream_replays_from_last_event_id(client):
    job_id = post_mixed_batch(client)
    with client.stream("GET", f"/batch/{job_id}/events") as response:
        first_run = sse_events("".join(response.iter_text()))
    # Reconnect claiming everything up to the third event was received.
    with client.stream(
        "GET", f"/batch/{job_id}/events", headers={"Last-Event-ID": "2"}
    ) as response:
        replayed = sse_events("".join(response.iter_text()))
    assert replayed == first_run[3:]


def test_unknown_job_stream_terminates(client):
    with client.stream("GET", "/batch/unknown-job/events") as response:
        events = sse_events("".join(response.iter_text()))
    assert events[-1][1] == "done"
    assert "no longer available" in events[0][2]


def test_bad_zip_is_visible_fragment(client):
    use_extractor(KeyedExtractor({}))
    response = client.post(
        "/batch",
        files={"batch_zip": ("batch.zip", b"not a zip", "application/zip")},
        headers=HTMX_HEADERS,
    )
    assert response.status_code == 400
    assert "Review could not be completed" in response.text
    assert "not a readable zip" in response.text


def test_oversized_zip_is_rejected(client, monkeypatch):
    use_extractor(KeyedExtractor({}))
    monkeypatch.setattr(limits, "MAX_BATCH_ZIP_BYTES", 10)
    data = make_batch([old_tom_row()], {"front.png": PNG})
    response = client.post(
        "/batch",
        files={"batch_zip": ("batch.zip", data, "application/zip")},
        headers=HTMX_HEADERS,
    )
    assert response.status_code == 413
    assert "split the batch" in response.text


def test_unconfigured_api_key_is_visible_fragment(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    data = make_batch([old_tom_row()], {"front.png": PNG})
    response = client.post(
        "/batch",
        files={"batch_zip": ("batch.zip", data, "application/zip")},
        headers=HTMX_HEADERS,
    )
    assert response.status_code == 503
    assert "ANTHROPIC_API_KEY" in response.text


def test_index_offers_batch_form_and_template(client):
    page = client.get("/").text
    assert 'hx-post="/batch"' in page
    assert 'href="/batch/template"' in page
    assert 'name="batch_zip"' in page
    # Vendored SSE extension, same constraint as htmx itself (D-10.3).
    assert 'src="/static/sse.min.js"' in page
    assert "http://" not in page and "https://" not in page
