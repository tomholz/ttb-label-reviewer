"""Batch input parsing (contracts.md §2): one zip = manifest.csv + images.

Pure and deterministic — no model, no I/O beyond the bytes handed in —
so every manifest rule is CI-testable. The contract's error split is
load-bearing: a malformed *batch* (not a zip, no manifest, bad header)
raises BatchError and aborts the upload; a malformed *row* (missing
field, unparseable ABV, filename not in the zip) becomes a RowError that
fails that row visibly and never aborts the batch.
"""

import csv
import io
import zipfile
from dataclasses import dataclass

from . import limits
from .engine import ApplicationRecord, BeverageType
from .extraction.base import LabelImage

MANIFEST_NAME = "manifest.csv"

# contracts.md §1/§2: columns are the application-record fields;
# `imported` is the only optional one (blank = false).
REQUIRED_COLUMNS = (
    "application_id",
    "beverage_type",
    "brand_name",
    "class_type",
    "abv_percent",
    "net_contents",
    "image_filenames",
)
MANIFEST_COLUMNS = REQUIRED_COLUMNS[:-1] + ("imported", "image_filenames")

ACCEPTED_BEVERAGE_TYPES = tuple(beverage_type.value for beverage_type in BeverageType)

# Offered for download by the UI (contracts.md §2): header plus one
# example row per commodity, exactly the shape parse_batch_zip() accepts.
TEMPLATE_CSV = (
    ",".join(MANIFEST_COLUMNS) + "\r\n"
    "app-001,distilled_spirits,OLD TOM DISTILLERY,"
    "Kentucky Straight Bourbon Whiskey,45.0,750 mL,false,"
    "front.png;back.png\r\n"
    "app-002,wine,VALLEY VIEW CELLARS,Table Wine,12.5,750 mL,false,"
    "wine-front.png\r\n"
    "app-003,malt_beverage,HARBOR MALT CO.,Lager,5.0,12 fl oz,false,"
    "malt-front.png\r\n"
)


class BatchError(Exception):
    """The batch as a whole is unusable (not a zip, no manifest, bad
    header...). The message is written to be shown to the user."""


@dataclass
class RowError:
    """One manifest row that cannot be reviewed; shown inline in the
    results table, alongside reviewed rows."""

    row_number: int  # 1-based line in manifest.csv; the header is row 1
    application_id: str  # "" when the row didn't even carry one
    message: str


@dataclass
class BatchRow:
    """One manifest row ready for the pipeline."""

    row_number: int
    application: ApplicationRecord
    images: list[LabelImage]


@dataclass
class ParsedBatch:
    rows: list[BatchRow]
    errors: list[RowError]

    @property
    def total(self) -> int:
        return len(self.rows) + len(self.errors)


def _sniff_media_type(data: bytes) -> str | None:
    """Zip entries carry no content type, so the format is sniffed from
    magic bytes; an unrecognized format is a row error here, not an
    opaque vision-API failure later."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def _find_manifest(zf: zipfile.ZipFile) -> zipfile.ZipInfo:
    """Locate manifest.csv anywhere in the zip (macOS "compress folder"
    wraps everything in a directory; __MACOSX metadata is ignored)."""
    candidates = [
        info
        for info in zf.infolist()
        if not info.is_dir()
        and not info.filename.startswith("__MACOSX/")
        and info.filename.rsplit("/", 1)[-1] == MANIFEST_NAME
    ]
    if not candidates:
        raise BatchError(
            f"The zip does not contain a {MANIFEST_NAME}. Download the "
            "CSV template, fill in one row per application, and include "
            "it in the zip next to the label images."
        )
    if len(candidates) > 1:
        names = ", ".join(info.filename for info in candidates)
        raise BatchError(
            f"The zip contains more than one {MANIFEST_NAME} ({names}); "
            "include exactly one."
        )
    return candidates[0]


def _read_manifest_rows(
    zf: zipfile.ZipFile, manifest: zipfile.ZipInfo
) -> list[dict[str, str]]:
    try:
        # utf-8-sig: the contract says UTF-8, and Excel's idea of UTF-8
        # includes a BOM; tolerating it costs nothing.
        text = zf.read(manifest).decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BatchError(f"{MANIFEST_NAME} is not valid UTF-8.") from exc

    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [name.strip().lower() for name in reader.fieldnames or []]
    reader.fieldnames = header
    missing = [column for column in REQUIRED_COLUMNS if column not in header]
    if missing:
        raise BatchError(
            f"{MANIFEST_NAME} is missing required column(s): "
            f"{', '.join(missing)}. Download the CSV template for the "
            "expected header."
        )
    rows = list(reader)
    if not rows:
        raise BatchError(f"{MANIFEST_NAME} has a header but no application rows.")
    if len(rows) > limits.MAX_BATCH_ROWS:
        raise BatchError(
            f"{MANIFEST_NAME} has {len(rows)} rows; a batch accepts at "
            f"most {limits.MAX_BATCH_ROWS}. Split it into smaller zips."
        )
    return rows


def _row_images(
    raw: str,
    zf: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    prefix: str,
    problems: list[str],
) -> list[LabelImage]:
    filenames = [name.strip() for name in raw.split(";") if name.strip()]
    if not filenames:
        problems.append(
            "image_filenames is blank (one or more filenames, semicolon-separated)"
        )
        return []
    if len(filenames) > limits.MAX_IMAGES_PER_SET:
        problems.append(
            f"{len(filenames)} images listed; a label set accepts at "
            f"most {limits.MAX_IMAGES_PER_SET}"
        )
        return []
    images: list[LabelImage] = []
    total_bytes = 0
    for name in filenames:
        # Resolved relative to the manifest's own directory first, so a
        # zipped folder works; a full path from the zip root also works.
        info = entries.get(prefix + name) or entries.get(name)
        if info is None:
            problems.append(f"image {name!r} is not in the zip")
            continue
        data = zf.read(info)
        if len(data) > limits.MAX_IMAGE_BYTES:
            problems.append(f"image {name!r} exceeds the 5 MB limit")
            continue
        total_bytes += len(data)
        if total_bytes > limits.MAX_TOTAL_IMAGE_BYTES:
            problems.append("combined image size exceeds the 20 MB limit")
            break
        media_type = _sniff_media_type(data)
        if media_type is None:
            problems.append(
                f"image {name!r} is not a supported format (JPEG, PNG, WebP, or GIF)"
            )
            continue
        images.append(LabelImage(filename=name, media_type=media_type, data=data))
    return images


def _parse_row(
    row_number: int,
    raw_row: dict[str, str],
    zf: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    prefix: str,
) -> BatchRow | RowError:
    def value(column: str) -> str:
        return (raw_row.get(column) or "").strip()

    # Every problem in the row is collected and reported at once, so one
    # round of fixes suffices instead of error whack-a-mole.
    problems: list[str] = []

    for column in ("application_id", "brand_name", "class_type", "net_contents"):
        if not value(column):
            problems.append(f"{column} is blank")

    beverage_type = value("beverage_type").lower()
    if beverage_type not in ACCEPTED_BEVERAGE_TYPES:
        problems.append(
            f"beverage_type {value('beverage_type')!r} is not supported "
            f"(accepted values: {', '.join(ACCEPTED_BEVERAGE_TYPES)})"
        )

    abv_percent = 0.0
    try:
        abv_percent = float(value("abv_percent"))
        if not 0 <= abv_percent <= 100:
            raise ValueError
    except ValueError:
        problems.append(
            f"abv_percent {value('abv_percent')!r} is not a number "
            "between 0 and 100 (the number only, e.g. 45.0)"
        )

    # contracts.md §2: true/false case-insensitive, blank = false.
    imported_raw = value("imported").lower()
    if imported_raw not in ("", "true", "false"):
        problems.append(
            f"imported {value('imported')!r} is not true/false (blank means false)"
        )
    imported = imported_raw == "true"

    images = _row_images(value("image_filenames"), zf, entries, prefix, problems)

    if problems:
        return RowError(
            row_number=row_number,
            application_id=value("application_id"),
            message="; ".join(problems) + ".",
        )
    return BatchRow(
        row_number=row_number,
        application=ApplicationRecord(
            application_id=value("application_id"),
            beverage_type=BeverageType(beverage_type),
            brand_name=value("brand_name"),
            class_type=value("class_type"),
            abv_percent=abv_percent,
            net_contents=value("net_contents"),
            imported=imported,
            image_filenames=[image.filename for image in images],
        ),
        images=images,
    )


def parse_batch_zip(data: bytes) -> ParsedBatch:
    """Parse one uploaded zip into reviewable rows plus row-level errors.

    Raises BatchError only for batch-level problems; everything
    row-shaped degrades to a RowError in the result.
    """
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise BatchError(
            "The upload is not a readable zip file. Zip the manifest.csv "
            "and label images together and try again."
        ) from exc

    with zf:
        uncompressed = sum(info.file_size for info in zf.infolist())
        if uncompressed > limits.MAX_BATCH_UNCOMPRESSED_BYTES:
            raise BatchError(
                "The zip expands to more than "
                f"{limits.MAX_BATCH_UNCOMPRESSED_BYTES // (1024 * 1024)} MB; "
                "split the batch into smaller zips."
            )

        manifest = _find_manifest(zf)
        prefix = manifest.filename[: -len(MANIFEST_NAME)]
        entries = {
            info.filename: info
            for info in zf.infolist()
            if not info.is_dir() and not info.filename.startswith("__MACOSX/")
        }

        rows: list[BatchRow] = []
        errors: list[RowError] = []
        # Header is line 1 of the CSV, so data rows are numbered from 2 —
        # matching what the user sees in a spreadsheet.
        for row_number, raw_row in enumerate(
            _read_manifest_rows(zf, manifest), start=2
        ):
            parsed = _parse_row(row_number, raw_row, zf, entries, prefix)
            if isinstance(parsed, RowError):
                errors.append(parsed)
            else:
                rows.append(parsed)
    return ParsedBatch(rows=rows, errors=errors)
