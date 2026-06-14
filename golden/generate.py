#!/usr/bin/env python3
"""Golden-set generator: renders the golden label images and writes the
manifest (contracts.md §5). Promoted from spikes/label-renderer/ per the
spike's GO recommendation.

Every string drawn on an image is a Python constant in the case table
below, and the manifest plus the faithful-extraction fixture are written
from those same constants — image text and ground truth cannot diverge.

Outputs, all into this directory (committed; regeneration is a deliberate
act that bumps MANIFEST_VERSION):

- one PNG/JPEG per label image
- manifest.json — contracts.md §5: application record + expected per-rule
  outcomes per case (omitted rule = expected pass)
- faithful_extractions.json — what a perfectly faithful extraction of
  each label set would return (§3 shape). Not part of the §5 contract; a
  test fixture that lets CI prove expected outcomes follow from the
  engine alone, and lets the eval runner attribute mismatches to
  extraction infidelity rather than manifest error.

Run:  uv run python golden/generate.py
Deps: Pillow (dev group). Fonts: macOS system Arial/Georgia TTFs — this
is a dev-machine tool; CI consumes the committed images and never runs it.

Importing engine.canonical here is allowed: D-2 forbids the canonical
warning in model prompts, and nothing here ever reaches a prompt.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from ttb_label_reviewer.engine.canonical import CANONICAL_WARNING
from ttb_label_reviewer.engine.normalize import normalize_warning

OUT_DIR = Path(__file__).parent
MANIFEST_VERSION = "3"

FONT_DIR = "/System/Library/Fonts/Supplemental"
ARIAL = f"{FONT_DIR}/Arial.ttf"
ARIAL_BOLD = f"{FONT_DIR}/Arial Bold.ttf"
GEORGIA = f"{FONT_DIR}/Georgia.ttf"
GEORGIA_BOLD = f"{FONT_DIR}/Georgia Bold.ttf"

W, H = 1000, 1400
CREAM = (247, 242, 230)
INK = (40, 32, 26)
MARGIN = 56

CANONICAL_LEAD_IN_COLON = "GOVERNMENT WARNING:"
CANONICAL_REMAINDER = CANONICAL_WARNING.removeprefix(CANONICAL_LEAD_IN_COLON + " ")
assert CANONICAL_REMAINDER != CANONICAL_WARNING

# ---------------------------------------------------------------------------
# Base label content (printed text). Cases override per field; None omits
# the line from the rendered label entirely.
# ---------------------------------------------------------------------------
BASE = {
    "brand": "OLD TOM RESERVE",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv": "45% Alc./Vol.",
    "proof": "90 Proof",
    "net": "750 mL",
    "address": "Bottled by Old Tom Distillery, Bardstown, KY",
    "origin": None,
}

BASE_APPLICATION = {
    "beverage_type": "distilled_spirits",
    "brand_name": "OLD TOM RESERVE",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_percent": 45.0,
    "net_contents": "750 mL",
    "imported": False,
}

CANONICAL_WARN = {"lead_in": CANONICAL_LEAD_IN_COLON, "remainder": CANONICAL_REMAINDER}

# Hand-authored line breaks with end-of-line hyphenation (bever-/ages,
# im-/pairs, machin-/ery): the DS-5a rejoin-hyphenation probe the spike
# flagged as unexercised. Joined with \n these must normalize back to the
# canonical text — asserted in main().
HYPHENATED_LINES = [
    [("GOVERNMENT WARNING:", "b"), ("(1) According to the Surgeon", "r")],
    [("General, women should not drink alcoholic bever-", "r")],
    [("ages during pregnancy because of the risk of birth", "r")],
    [("defects. (2) Consumption of alcoholic beverages im-", "r")],
    [("pairs your ability to drive a car or operate machin-", "r")],
    [("ery, and may cause health problems.", "r")],
]

NA = {"outcome": "not_applicable"}
DS7_NA = {"DS-7": NA}
COUNTRY_ORIGIN_NA = {
    "distilled_spirits": {"DS-7": NA},
    "wine": {"WN-7": NA},
    "malt_beverage": {"MB-7": NA},
}
SCOPE_MARKERS = {
    "distilled_spirits": {"DS-SCOPE": {"outcome": "not_evaluated"}},
    "wine": {"WN-SCOPE": {"outcome": "not_evaluated"}},
    "malt_beverage": {"MB-SCOPE": {"outcome": "not_evaluated"}},
}

# ---------------------------------------------------------------------------
# Case table — the single source of truth for pixels, manifest, and the
# faithful-extraction fixture. Schema per case:
#   labels: list of per-image content dicts (BASE + overrides); "warn" is
#     None, {"lead_in", "remainder"} (auto-wrapped), or {"lines": [...]}
#   application: §1 record overrides (application_id/image_filenames added)
#   expected: §5 expected map — non-pass, not_applicable, and not_evaluated only
#   degrade: post-process the render into a skewed/blurred/noisy JPEG
# ---------------------------------------------------------------------------
CASES = [
    {
        "case_id": "compliant",
        "purpose": "Fully compliant baseline; every rule should pass.",
        "labels": [{**BASE, "warn": CANONICAL_WARN}],
        "application": {},
        "expected": {**DS7_NA},
    },
    {
        "case_id": "warning-title-case",
        "purpose": (
            "Extraction-fidelity probe: title-case lead-in is exactly what "
            "the model's all-caps prior will silently 'correct' (highest-"
            "value probe). DS-5b must fail on format; DS-5a still passes."
        ),
        "labels": [
            {
                **BASE,
                "warn": {
                    "lead_in": "Government Warning:",
                    "remainder": CANONICAL_REMAINDER,
                },
            }
        ],
        "application": {},
        "expected": {
            "DS-5b": {"outcome": "fail", "reason": "format"},
            **DS7_NA,
        },
    },
    {
        "case_id": "warning-fetal-harm",
        "purpose": (
            "Near-miss warning: one-phrase substitution 'birth defects' -> "
            "'fetal harm'. Measures autocomplete-toward-canonical on DS-5a."
        ),
        "labels": [
            {
                **BASE,
                "warn": {
                    "lead_in": CANONICAL_LEAD_IN_COLON,
                    "remainder": CANONICAL_REMAINDER.replace(
                        "birth defects", "fetal harm"
                    ),
                },
            }
        ],
        "application": {},
        "expected": {
            "DS-5a": {"outcome": "fail", "reason": "mismatch"},
            **DS7_NA,
        },
    },
    {
        "case_id": "warning-dropped-2",
        "purpose": (
            "Near-miss warning: the '(2)' clause marker is dropped. A "
            "single-token omission the model's prior wants to restore."
        ),
        "labels": [
            {
                **BASE,
                "warn": {
                    "lead_in": CANONICAL_LEAD_IN_COLON,
                    "remainder": CANONICAL_REMAINDER.replace("(2) ", ""),
                },
            }
        ],
        "application": {},
        "expected": {
            "DS-5a": {"outcome": "fail", "reason": "mismatch"},
            **DS7_NA,
        },
    },
    {
        "case_id": "warning-hyphenated",
        "purpose": (
            "Canonical warning printed with end-of-line hyphenation "
            "(bever-/ages, im-/pairs, machin-/ery). Extraction must "
            "preserve the hyphen+break; DS-5a normalization rejoins it. "
            "All rules pass."
        ),
        "labels": [{**BASE, "warn": {"lines": HYPHENATED_LINES, "size": 28}}],
        "application": {},
        "expected": {**DS7_NA},
    },
    {
        "case_id": "warning-back-label",
        "purpose": (
            "Multi-image label set: warning appears only on a separate "
            "back label (27 CFR 16.21 expressly permits this). A field "
            "satisfied on any image satisfies the rule."
        ),
        "labels": [
            {**BASE, "warn": None},
            {
                "brand": None,
                "class_type": None,
                "abv": None,
                "proof": None,
                "net": None,
                "address": None,
                "origin": None,
                "warn": CANONICAL_WARN,
            },
        ],
        "application": {},
        "expected": {**DS7_NA},
    },
    {
        "case_id": "warning-missing",
        "purpose": "Warning entirely absent: missing (not illegible) routing.",
        "labels": [{**BASE, "warn": None}],
        "application": {},
        "expected": {
            "DS-5a": {"outcome": "fail", "reason": "missing"},
            "DS-5b": {"outcome": "fail", "reason": "missing"},
            "DS-5c": {"outcome": "needs_review", "reason": "missing"},
            "DS-5d": {"outcome": "needs_review", "reason": "missing"},
            **DS7_NA,
        },
    },
    {
        "case_id": "brand-case-variance",
        "purpose": (
            "STONE'S THROW on the label vs Stone's Throw in the "
            "application: fuzzy-equal, so needs_review, never fail "
            "(Dave's judgment case)."
        ),
        "labels": [{**BASE, "brand": "STONE'S THROW", "warn": CANONICAL_WARN}],
        "application": {"brand_name": "Stone's Throw"},
        "expected": {
            "DS-1": {"outcome": "needs_review", "reason": "mismatch"},
            **DS7_NA,
        },
    },
    {
        "case_id": "abv-within-band",
        "purpose": (
            "Label 45.2% vs application 45.0%: inside the 0.3 pp band, so "
            "needs_review. Proof omitted so DS-8 stays out of the way."
        ),
        "labels": [
            {**BASE, "abv": "45.2% Alc./Vol.", "proof": None, "warn": CANONICAL_WARN}
        ],
        "application": {},
        "expected": {
            "DS-3": {"outcome": "needs_review", "reason": "mismatch"},
            "DS-8": NA,
            **DS7_NA,
        },
    },
    {
        "case_id": "abv-beyond-band",
        "purpose": "Label 45.4% vs application 45.0%: beyond 0.3 pp, clear fail.",
        "labels": [
            {**BASE, "abv": "45.4% Alc./Vol.", "proof": None, "warn": CANONICAL_WARN}
        ],
        "application": {},
        "expected": {
            "DS-3": {"outcome": "fail", "reason": "mismatch"},
            "DS-8": NA,
            **DS7_NA,
        },
    },
    {
        "case_id": "abv-bare-format",
        "purpose": (
            "Label says '45% ABV' — right number, but ABV is not a "
            "permitted abbreviation (5.65(a)): needs_review on format. "
            "Also probes that extraction returns the bare string rather "
            "than expanding it."
        ),
        "labels": [{**BASE, "abv": "45% ABV", "warn": CANONICAL_WARN}],
        "application": {},
        "expected": {
            "DS-3": {"outcome": "needs_review", "reason": "format"},
            **DS7_NA,
        },
    },
    {
        "case_id": "proof-mismatch",
        "purpose": (
            "86 Proof printed beside 45% Alc./Vol.: DS-8 internal cross-"
            "check flags it for a human; doubles as an extraction-quality "
            "canary."
        ),
        "labels": [{**BASE, "proof": "86 Proof", "warn": CANONICAL_WARN}],
        "application": {},
        "expected": {
            "DS-8": {"outcome": "needs_review", "reason": "mismatch"},
            **DS7_NA,
        },
    },
    {
        "case_id": "missing-fields",
        "purpose": (
            "Net contents and name/address absent: DS-4 routes to "
            "needs_review (contents may be blown into the glass); DS-6 "
            "fails on missing."
        ),
        "labels": [{**BASE, "net": None, "address": None, "warn": CANONICAL_WARN}],
        "application": {},
        "expected": {
            "DS-4": {"outcome": "needs_review", "reason": "missing"},
            "DS-6": {"outcome": "fail", "reason": "missing"},
            **DS7_NA,
        },
    },
    {
        "case_id": "imported-with-origin",
        "purpose": (
            "Imported case: country-of-origin present, DS-7 evaluated and passes."
        ),
        "labels": [
            {
                "brand": "NORTH HARBOUR",
                "class_type": "Canadian Whisky",
                "abv": "40% Alc./Vol.",
                "proof": "80 Proof",
                "net": "750 mL",
                "address": "Imported by Harbour Imports Co., Buffalo, NY",
                "origin": "Product of Canada",
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "brand_name": "NORTH HARBOUR",
            "class_type": "Canadian Whisky",
            "abv_percent": 40.0,
            "imported": True,
        },
        "expected": {},
    },
    {
        "case_id": "imported-missing-origin",
        "purpose": (
            "Imported but no country-of-origin statement: DS-7 fails on missing."
        ),
        "labels": [
            {
                "brand": "NORTH HARBOUR",
                "class_type": "Canadian Whisky",
                "abv": "40% Alc./Vol.",
                "proof": "80 Proof",
                "net": "750 mL",
                "address": "Imported by Harbour Imports Co., Buffalo, NY",
                "origin": None,
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "brand_name": "NORTH HARBOUR",
            "class_type": "Canadian Whisky",
            "abv_percent": 40.0,
            "imported": True,
        },
        "expected": {"DS-7": {"outcome": "fail", "reason": "missing"}},
    },
    {
        "case_id": "degraded",
        "purpose": (
            "Compliant content through rotation, blur, noise, and heavy "
            "JPEG compression — still human-readable, so the tool must "
            "read it (pass) or honestly route to review; used to tune the "
            "illegibility threshold."
        ),
        "labels": [{**BASE, "warn": CANONICAL_WARN}],
        "application": {},
        "expected": {**DS7_NA},
        "degrade": True,
    },
    {
        "case_id": "wine-compliant-table",
        "purpose": (
            "Wine baseline: shared rules pass, <=14% table-wine alcohol omission "
            "is lawful, and WN-SCOPE emits visible not_evaluated rows."
        ),
        "labels": [
            {
                **BASE,
                "brand": "VALLEY CREST",
                "class_type": "California Table Wine",
                "abv": None,
                "proof": None,
                "net": "750 mL",
                "address": "Produced and bottled by Valley Crest Winery, Sonoma, CA",
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "beverage_type": "wine",
            "brand_name": "VALLEY CREST",
            "class_type": "California Table Wine",
            "abv_percent": 12.5,
            "net_contents": "750 mL",
            "imported": False,
        },
        "expected": {},
    },
    {
        "case_id": "wine-high-abv-missing-statement",
        "purpose": (
            "Wine above 14% ABV with no alcohol-content statement: WN-3 must "
            "fail missing while shared rules pass."
        ),
        "labels": [
            {
                **BASE,
                "brand": "VALLEY CREST",
                "class_type": "Napa Valley Cabernet Sauvignon",
                "abv": None,
                "proof": None,
                "net": "750 mL",
                "address": "Produced and bottled by Valley Crest Winery, Sonoma, CA",
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "beverage_type": "wine",
            "brand_name": "VALLEY CREST",
            "class_type": "Napa Valley Cabernet Sauvignon",
            "abv_percent": 15.5,
            "net_contents": "750 mL",
            "imported": False,
        },
        "expected": {"WN-3": {"outcome": "fail", "reason": "missing"}},
    },
    {
        "case_id": "malt-compliant",
        "purpose": (
            "Malt baseline: shared rules pass and MB-3 passes a present optional "
            "ABV statement."
        ),
        "labels": [
            {
                **BASE,
                "brand": "NORTHGATE",
                "class_type": "India Pale Ale",
                "abv": "6.8% ALC/VOL",
                "proof": None,
                "net": "12 FL OZ",
                "address": "Brewed and canned by Northgate Brewing Co., Milwaukee, WI",
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "beverage_type": "malt_beverage",
            "brand_name": "NORTHGATE",
            "class_type": "India Pale Ale",
            "abv_percent": 6.8,
            "net_contents": "12 FL OZ",
            "imported": False,
        },
        "expected": {},
    },
    {
        "case_id": "malt-abv-mismatch",
        "purpose": (
            "Malt ABV beyond the +-0.3 pp consistency band: MB-3 must fail "
            "mismatch while shared rules pass."
        ),
        "labels": [
            {
                **BASE,
                "brand": "NORTHGATE",
                "class_type": "Lager",
                "abv": "7.5% ALC/VOL",
                "proof": None,
                "net": "12 FL OZ",
                "address": "Brewed and canned by Northgate Brewing Co., Milwaukee, WI",
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "beverage_type": "malt_beverage",
            "brand_name": "NORTHGATE",
            "class_type": "Lager",
            "abv_percent": 5.0,
            "net_contents": "12 FL OZ",
            "imported": False,
        },
        "expected": {"MB-3": {"outcome": "fail", "reason": "mismatch"}},
    },
    {
        "case_id": "malt-abv-omitted",
        "purpose": (
            "Missing malt ABV routes to needs_review, not fail, because malt "
            "alcohol content is optional except for triggers outside this "
            "label-only review."
        ),
        "labels": [
            {
                **BASE,
                "brand": "NORTHGATE",
                "class_type": "Lager",
                "abv": None,
                "proof": None,
                "net": "12 FL OZ",
                "address": "Brewed and canned by Northgate Brewing Co., Milwaukee, WI",
                "warn": CANONICAL_WARN,
            }
        ],
        "application": {
            "beverage_type": "malt_beverage",
            "brand_name": "NORTHGATE",
            "class_type": "Lager",
            "abv_percent": 4.5,
            "net_contents": "12 FL OZ",
            "imported": False,
        },
        "expected": {"MB-3": {"outcome": "needs_review", "reason": "missing"}},
    },
]


# ---------------------------------------------------------------------------
# Mixed-font word wrap (from the spike: the one thing Pillow doesn't give
# you — a bold lead-in flowing inline into a regular remainder).
# ---------------------------------------------------------------------------
def wrap_segments(draw, segments, max_width):
    words = [(w, font) for text, font in segments for w in text.split()]
    lines, line, line_w = [], [], 0.0
    for word, font in words:
        word_w = draw.textlength(word, font=font)
        space_w = draw.textlength(" ", font=font) if line else 0.0
        if line and line_w + space_w + word_w > max_width:
            lines.append(line)
            line, line_w = [(word, font)], word_w
        else:
            line.append((word, font))
            line_w += space_w + word_w
    if line:
        lines.append(line)
    return lines


def draw_lines(draw, lines, x, y, line_height):
    for line in lines:
        cx = x
        for i, (word, font) in enumerate(line):
            if i:
                cx += draw.textlength(" ", font=font)
            draw.text((cx, y), word, font=font, fill=INK)
            cx += draw.textlength(word, font=font)
        y += line_height


def centered(draw, text, font, y):
    w = draw.textlength(text, font=font)
    draw.text(((W - w) / 2, y), text, font=font, fill=INK)


def render_label(content, out_path: Path) -> list[str] | None:
    """Render one label image; return the warning's printed lines (None if
    the label has no warning) so the faithful-extraction fixture records
    the exact line breaks as printed."""
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    d.rectangle([MARGIN, MARGIN, W - MARGIN, H - MARGIN], outline=INK, width=4)
    d.rectangle(
        [MARGIN + 12, MARGIN + 12, W - MARGIN - 12, H - MARGIN - 12],
        outline=INK,
        width=2,
    )

    brand_font = ImageFont.truetype(GEORGIA_BOLD, 76)
    class_font = ImageFont.truetype(GEORGIA, 42)
    stat_font = ImageFont.truetype(ARIAL, 36)
    small_font = ImageFont.truetype(ARIAL, 28)

    y = 200
    if content["brand"]:
        centered(d, content["brand"], brand_font, y)
        y += 130
        d.line([(W / 2 - 220, y), (W / 2 + 220, y)], fill=INK, width=3)
        y += 50
    if content["class_type"]:
        centered(d, content["class_type"], class_font, y)
        y += 110
    for key in ("abv", "proof", "net"):
        if content[key]:
            centered(d, content[key], stat_font, y)
            y += 60
    y += 50
    if content["address"]:
        centered(d, content["address"], small_font, y)
        y += 44
    if content["origin"]:
        centered(d, content["origin"], small_font, y)

    warn_lines = draw_warning(d, content["warn"]) if content["warn"] else None
    img.save(out_path)
    return warn_lines


def draw_warning(d, spec) -> list[str]:
    """Draw the warning block near the bottom (separate and apart; bold
    lead-in, regular remainder) and return its lines as printed strings."""
    size = spec.get("size", 30)
    bold = ImageFont.truetype(ARIAL_BOLD, size)
    reg = ImageFont.truetype(ARIAL, size)
    warn_x = MARGIN + 50
    warn_width = W - 2 * warn_x

    if "lines" in spec:
        lines = [
            [
                (word, bold if style == "b" else reg)
                for text, style in line
                for word in text.split()
            ]
            for line in spec["lines"]
        ]
        for line in lines:
            width = sum(d.textlength(w, font=f) for w, f in line)
            width += sum(d.textlength(" ", font=f) for _, f in line[1:])
            if width > warn_width:
                raise ValueError(f"authored warning line overflows: {line}")
    else:
        segments = [(spec["lead_in"], bold), (spec["remainder"], reg)]
        lines = wrap_segments(d, segments, warn_width)

    line_height = size + 12
    warn_y = H - MARGIN - 60 - line_height * len(lines)
    draw_lines(d, lines, warn_x, warn_y, line_height)
    return [" ".join(word for word, _ in line) for line in lines]


def degrade(png_path: Path, jpg_path: Path) -> None:
    """Rotation + blur + noise + heavy JPEG compression, applied after
    exact-text rendering so the ground truth is unchanged (spike's
    recommended approach for an OCR-robustness case)."""
    img = Image.open(png_path).convert("RGB")
    img = img.rotate(2.5, resample=Image.BICUBIC, expand=True, fillcolor=CREAM)
    noise = Image.effect_noise(img.size, 24).convert("RGB")
    img = Image.blend(img, noise, 0.08)
    img = img.filter(ImageFilter.GaussianBlur(1.0))
    img.save(jpg_path, quality=40)
    png_path.unlink()


# ---------------------------------------------------------------------------
# Faithful extraction (§3 shape) from the same constants as the pixels.
# ---------------------------------------------------------------------------
def faithful_extraction(labels, warn_lines_per_label) -> dict:
    def field(raw):
        return None if raw is None else {"raw": raw, "confidence": 0.97}

    merged = {}
    for key in ("brand", "class_type", "abv", "proof", "net", "address", "origin"):
        for content in labels:
            if content[key]:
                merged[key] = content[key]
                break
        else:
            merged[key] = None

    warning = None
    for lines in warn_lines_per_label:
        if lines:
            warning = {
                "raw_text": "\n".join(lines),
                "lead_in_bold": "yes",
                "remainder_bold": "no",
                "separate_and_apart": "yes",
                "confidence": 0.93,
            }
            break

    return {
        "brand_name": field(merged["brand"]),
        "class_type": field(merged["class_type"]),
        "alcohol_content": field(merged["abv"]),
        "proof": field(merged["proof"]),
        "net_contents": field(merged["net"]),
        "name_address": field(merged["address"]),
        "country_of_origin": field(merged["origin"]),
        "government_warning": warning,
    }


def image_filenames(case) -> list[str]:
    ext = "jpg" if case.get("degrade") else "png"
    if len(case["labels"]) == 1:
        return [f"{case['case_id']}.{ext}"]
    suffixes = ["front", "back", "side", "neck"]
    return [
        f"{case['case_id']}-{suffixes[i]}.{ext}" for i in range(len(case["labels"]))
    ]


def automatic_expected(beverage_type: str, application: dict) -> dict:
    expected = dict(SCOPE_MARKERS[beverage_type])
    if not application.get("imported", False):
        expected.update(COUNTRY_ORIGIN_NA[beverage_type])
    return expected


def main():
    hyphenated_text = "\n".join(
        " ".join(text for text, _ in line) for line in HYPHENATED_LINES
    )
    assert normalize_warning(hyphenated_text) == normalize_warning(CANONICAL_WARNING)

    manifest_cases = []
    faithful = {}
    for case in CASES:
        application = {**BASE_APPLICATION, **case["application"]}
        beverage_type = application["beverage_type"]
        filenames = image_filenames(case)
        warn_lines_per_label = []
        for content, filename in zip(case["labels"], filenames, strict=True):
            render_path = OUT_DIR / (
                filename.removesuffix(".jpg") + ".png"
                if case.get("degrade")
                else filename
            )
            warn_lines_per_label.append(render_label(content, render_path))
            if case.get("degrade"):
                degrade(render_path, OUT_DIR / filename)
            print(f"rendered {OUT_DIR / filename}")

        manifest_cases.append(
            {
                "case_id": case["case_id"],
                "purpose": case["purpose"],
                "application": {
                    "application_id": case["case_id"],
                    **application,
                    "image_filenames": filenames,
                },
                "expected": {
                    **case["expected"],
                    **automatic_expected(beverage_type, application),
                },
            }
        )
        faithful[case["case_id"]] = faithful_extraction(
            case["labels"], warn_lines_per_label
        )

    manifest = {"version": MANIFEST_VERSION, "cases": manifest_cases}
    (OUT_DIR / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (OUT_DIR / "faithful_extractions.json").write_text(
        json.dumps(faithful, indent=2) + "\n"
    )
    print(f"wrote manifest.json ({len(manifest_cases)} cases)")


if __name__ == "__main__":
    main()
