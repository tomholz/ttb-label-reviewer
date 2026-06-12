#!/usr/bin/env python3
"""Spike: render alcohol-label images with text that is exact by construction.

Why this exists: AI image generators cannot reliably render long exact text,
but the golden test set needs labels whose government warning is wrong by
precisely one word or one case change. Here every string drawn on the image
is a Python constant, and the ground-truth sidecar JSON is written from the
same constants — so image text and ground truth cannot diverge.

Run:  uv run --with pillow render_labels.py
Deps: Pillow only. Fonts: macOS system Arial/Georgia (regular + bold TTFs).
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT_DIR = Path(__file__).parent / "out"

FONT_DIR = "/System/Library/Fonts/Supplemental"
ARIAL = f"{FONT_DIR}/Arial.ttf"
ARIAL_BOLD = f"{FONT_DIR}/Arial Bold.ttf"
GEORGIA = f"{FONT_DIR}/Georgia.ttf"
GEORGIA_BOLD = f"{FONT_DIR}/Georgia Bold.ttf"

# ---------------------------------------------------------------------------
# Canvas / palette
# ---------------------------------------------------------------------------
W, H = 1000, 1400
CREAM = (247, 242, 230)
INK = (40, 32, 26)
MARGIN = 56  # outer border inset

# ---------------------------------------------------------------------------
# Label content — single source of truth for image AND ground truth
# ---------------------------------------------------------------------------
BASE_FIELDS = {
    "brand_name": "OLD TOM RESERVE",
    "class_type": "Kentucky Straight Bourbon Whiskey",
    "abv_statement": "45% Alc./Vol.",
    "proof_statement": "90 Proof",
    "net_contents": "750 mL",
    "name_address": "Bottled by Old Tom Distillery, Bardstown, KY",
}

# Canonical health warning per 27 CFR 16.21 (docs/ttb-requirements.md, DS-5).
CANONICAL_LEAD_IN = "GOVERNMENT WARNING:"
CANONICAL_REMAINDER = (
    "(1) According to the Surgeon General, women should not drink "
    "alcoholic beverages during pregnancy because of the risk of birth "
    "defects. (2) Consumption of alcoholic beverages impairs your ability "
    "to drive a car or operate machinery, and may cause health problems."
)

VARIANTS = [
    {
        "id": "a_compliant",
        "defect": None,
        "lead_in": CANONICAL_LEAD_IN,
        "remainder": CANONICAL_REMAINDER,
        "expected_outcomes": {"DS-5a": "pass", "DS-5b": "pass", "DS-5c": "pass"},
    },
    {
        "id": "b_title_case_lead_in",
        "defect": "lead-in rendered in title case instead of all caps",
        "lead_in": "Government Warning:",
        "remainder": CANONICAL_REMAINDER,
        "expected_outcomes": {"DS-5a": "pass", "DS-5b": "fail", "DS-5c": "pass"},
    },
    {
        "id": "c_word_substitution",
        "defect": "one-word substitution: 'birth defects' -> 'fetal harm'",
        "lead_in": CANONICAL_LEAD_IN,
        "remainder": CANONICAL_REMAINDER.replace("birth defects", "fetal harm"),
        "expected_outcomes": {"DS-5a": "fail", "DS-5b": "pass", "DS-5c": "pass"},
    },
    {
        "id": "d_missing_warning",
        "defect": "warning statement entirely absent",
        "lead_in": None,
        "remainder": None,
        "expected_outcomes": {"DS-5a": "fail (missing)", "DS-5b": "fail (missing)",
                              "DS-5c": "needs_review (missing)"},
    },
]


# ---------------------------------------------------------------------------
# Mixed-font word wrap (the part Pillow does not give you for free)
# ---------------------------------------------------------------------------
def wrap_segments(draw, segments, max_width):
    """Wrap a sequence of (text, font) runs into lines of (word, font) pairs.

    Greedy word wrap; each word keeps its own font, which is exactly what a
    bold lead-in followed by a regular remainder needs.
    """
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


def draw_wrapped(draw, lines, x, y, line_height, fill=INK):
    for line in lines:
        cx = x
        for i, (word, font) in enumerate(line):
            if i:
                cx += draw.textlength(" ", font=font)
            draw.text((cx, y), word, font=font, fill=fill)
            cx += draw.textlength(word, font=font)
        y += line_height
    return y


def centered(draw, text, font, y, fill=INK):
    w = draw.textlength(text, font=font)
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


# ---------------------------------------------------------------------------
# Render one label
# ---------------------------------------------------------------------------
def render_label(variant):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # Double border for a plausible label look
    d.rectangle([MARGIN, MARGIN, W - MARGIN, H - MARGIN], outline=INK, width=4)
    d.rectangle([MARGIN + 12, MARGIN + 12, W - MARGIN - 12, H - MARGIN - 12],
                outline=INK, width=2)

    brand_font = ImageFont.truetype(GEORGIA_BOLD, 76)
    class_font = ImageFont.truetype(GEORGIA, 42)
    stat_font = ImageFont.truetype(ARIAL, 36)
    small_font = ImageFont.truetype(ARIAL, 28)
    warn_bold = ImageFont.truetype(ARIAL_BOLD, 30)
    warn_reg = ImageFont.truetype(ARIAL, 30)

    y = 200
    centered(d, BASE_FIELDS["brand_name"], brand_font, y)
    y += 130

    # Decorative rule under the brand name
    d.line([(W / 2 - 220, y), (W / 2 + 220, y)], fill=INK, width=3)
    y += 50

    centered(d, BASE_FIELDS["class_type"], class_font, y)
    y += 110

    centered(d, BASE_FIELDS["abv_statement"], stat_font, y)
    y += 60
    centered(d, BASE_FIELDS["proof_statement"], stat_font, y)
    y += 60
    centered(d, BASE_FIELDS["net_contents"], stat_font, y)
    y += 110

    centered(d, BASE_FIELDS["name_address"], small_font, y)

    # Warning block: separate and apart near the bottom, lead-in bold,
    # remainder regular (DS-5c is exactly this bold/regular contrast).
    if variant["lead_in"] is not None:
        warn_x = MARGIN + 50
        warn_width = W - 2 * warn_x
        segments = [(variant["lead_in"], warn_bold),
                    (variant["remainder"], warn_reg)]
        lines = wrap_segments(d, segments, warn_width)
        line_height = 42
        warn_y = H - MARGIN - 60 - line_height * len(lines)
        draw_wrapped(d, lines, warn_x, warn_y, line_height)

    out_path = OUT_DIR / f"label_{variant['id']}.png"
    img.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main: render all variants + ground-truth sidecar from the same constants
# ---------------------------------------------------------------------------
def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ground_truth = {
        "canonical_warning": f"{CANONICAL_LEAD_IN} {CANONICAL_REMAINDER}",
        "fonts": {
            "warning_lead_in": "Arial Bold 30px (bold)",
            "warning_remainder": "Arial Regular 30px (not bold)",
        },
        "labels": [],
    }

    for variant in VARIANTS:
        path = render_label(variant)
        has_warning = variant["lead_in"] is not None
        entry = {
            "image": path.name,
            "defect": variant["defect"],
            "fields": dict(BASE_FIELDS),
            "warning": (
                {
                    "lead_in": variant["lead_in"],
                    "lead_in_bold": True,
                    "remainder": variant["remainder"],
                    "remainder_bold": False,
                    "full_text": f"{variant['lead_in']} {variant['remainder']}",
                }
                if has_warning
                else None
            ),
            "expected_rule_outcomes": variant["expected_outcomes"],
        }
        ground_truth["labels"].append(entry)
        print(f"rendered {path}")

    gt_path = OUT_DIR / "ground_truth.json"
    gt_path.write_text(json.dumps(ground_truth, indent=2) + "\n")
    print(f"wrote {gt_path}")


if __name__ == "__main__":
    main()
