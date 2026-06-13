"""Build the demo data served by the index page's "Try it with sample
data" card, derived entirely from golden/manifest.json — never typed by
hand, so the demo can't drift from the labels (tests/test_demo.py
asserts it hasn't).

Outputs, committed under src/ttb_label_reviewer/static/demo/:

- demo-batch.zip — a curated batch (contracts.md §2): nine reviewable
  golden cases covering every verdict group plus two deliberately
  broken rows, so one upload exercises the whole results UI
- the single-review sample images, copied from golden/
- demo.json — the form values and what-to-expect copy the index page
  renders

Rerun after regenerating the golden set:

    uv run python golden/build_demo.py
"""

import csv
import io
import json
import shutil
import zipfile
from pathlib import Path

GOLDEN_DIR = Path(__file__).parent
DEMO_DIR = GOLDEN_DIR.parent / "src" / "ttb_label_reviewer" / "static" / "demo"

# Reviewable rows: golden case ids, in manifest order below. Chosen to
# light up every group on one upload — pass with visible evidence,
# both marquee warning fails (title case, fetal harm), both judgment
# routes (brand variance, ABV band), the banded fail, a multi-image
# set, an imported case, and a degraded photo.
BATCH_CASE_IDS = [
    "compliant",
    "warning-title-case",
    "warning-fetal-harm",
    "brand-case-variance",
    "abv-within-band",
    "abv-beyond-band",
    "warning-back-label",
    "imported-with-origin",
    "degraded",
]

# Broken rows (contracts.md §2): reported inline, never abort the batch.
BROKEN_ROWS = [
    {
        "application_id": "demo-broken-image",
        "beverage_type": "distilled_spirits",
        "brand_name": "OLD TOM RESERVE",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv_percent": "45.0",
        "net_contents": "750 mL",
        "imported": "false",
        "image_filenames": "ghost.png",  # not in the zip
    },
    {
        "application_id": "demo-broken-abv",
        "beverage_type": "distilled_spirits",
        "brand_name": "OLD TOM RESERVE",
        "class_type": "Kentucky Straight Bourbon Whiskey",
        "abv_percent": "45% Alc./Vol.",  # the number only, per §1
        "net_contents": "750 mL",
        "imported": "false",
        "image_filenames": "compliant.png",
    },
]

# Single-review samples: case id -> what the reviewer should see.
SINGLE_SAMPLES = {
    "compliant": "passes every check, evidence shown on each",
    "warning-title-case": (
        'fails the capitalization check — "Government Warning" in title '
        "case, the classic catch"
    ),
    "warning-fetal-harm": (
        "fails the warning text check with a character-level diff "
        '("birth defects" reads "fetal harm")'
    ),
}

MANIFEST_COLUMNS = [
    "application_id",
    "beverage_type",
    "brand_name",
    "class_type",
    "abv_percent",
    "net_contents",
    "imported",
    "image_filenames",
]

# Fixed timestamp so rebuilding an unchanged demo produces an
# byte-identical zip (zips embed file mtimes).
ZIP_DATE = (2026, 1, 1, 0, 0, 0)

_WORST = {"fail": 0, "needs_review": 1, "pass": 2}


def case_verdict(case: dict) -> str:
    """Worst expected outcome, fail > needs_review > pass;
    not_applicable is excluded from aggregation (contracts.md §4)."""
    outcomes = [
        e["outcome"]
        for e in case["expected"].values()
        if e["outcome"] != "not_applicable"
    ]
    return min(outcomes, key=_WORST.__getitem__, default="pass")


def csv_row(application: dict) -> dict:
    return {
        "application_id": application["application_id"],
        "beverage_type": application["beverage_type"],
        "brand_name": application["brand_name"],
        "class_type": application["class_type"],
        "abv_percent": repr(application["abv_percent"]),
        "net_contents": application["net_contents"],
        "imported": "true" if application["imported"] else "false",
        "image_filenames": ";".join(application["image_filenames"]),
    }


def main() -> None:
    manifest = json.loads((GOLDEN_DIR / "manifest.json").read_text())
    cases = {case["case_id"]: case for case in manifest["cases"]}
    chosen = [cases[case_id] for case_id in BATCH_CASE_IDS]

    rows = [csv_row(case["application"]) for case in chosen] + BROKEN_ROWS
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=MANIFEST_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)

    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = DEMO_DIR / "demo-batch.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:

        def add(name: str, data: bytes) -> None:
            zf.writestr(zipfile.ZipInfo(name, date_time=ZIP_DATE), data)

        add("manifest.csv", buffer.getvalue().encode())
        for case in chosen:
            for filename in case["application"]["image_filenames"]:
                add(filename, (GOLDEN_DIR / filename).read_bytes())

    counts = {"fail": 0, "needs_review": 0, "pass": 0}
    for case in chosen:
        counts[case_verdict(case)] += 1
    counts["error"] = len(BROKEN_ROWS)

    singles = []
    for case_id, note in SINGLE_SAMPLES.items():
        application = cases[case_id]["application"]
        (filename,) = application["image_filenames"]
        shutil.copyfile(GOLDEN_DIR / filename, DEMO_DIR / filename)
        singles.append(
            {
                "filename": filename,
                "brand_name": application["brand_name"],
                "class_type": application["class_type"],
                "abv_percent": application["abv_percent"],
                "net_contents": application["net_contents"],
                "note": note,
            }
        )

    demo = {
        "golden_manifest_version": manifest["version"],
        "singles": singles,
        "batch": {"rows": len(rows), "expected": counts},
    }
    (DEMO_DIR / "demo.json").write_text(json.dumps(demo, indent=2) + "\n")

    print(f"wrote {zip_path} ({zip_path.stat().st_size} bytes)")
    print(f"rows: {len(rows)}, expected: {counts}")
    print(f"singles: {[s['filename'] for s in singles]}")


if __name__ == "__main__":
    main()
