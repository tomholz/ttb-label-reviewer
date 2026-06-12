#!/usr/bin/env python3
"""Illegibility-threshold probe: how does the model's per-field confidence
self-report respond to escalating image degradation — and when the image
becomes genuinely hard to read, does it keep reading or fall back to its
prior?

The golden-set eval showed confidence saturated at >=0.98 on every case,
including the (moderately) degraded one — so the eval alone cannot tune
EngineConfig.illegibility_threshold. This probe escalates blur/downscale
on a golden label and records (a) the reported confidences and (b)
whether the warning transcription still matches that label's faithful
raw text.

Run it on two cases for the full picture:

- `--case compliant`: confidence response to degradation. Verbatim "yes"
  here is ambiguous at high degradation — the canonical text is also the
  model's prior, so a correct answer may be autocomplete, not reading.
- `--case warning-fetal-harm`: the sharp version. The printed text
  deviates from the prior, so at each level the model either preserves
  the deviation (reading) or reverts to canonical (autocomplete) — and
  we see what confidence it reports when it does.

The threshold decision is documented in the README's eval-scoreboard
section.

Run:  uv run --env-file .env python golden/probe_illegibility.py \\
          [--model M] [--case CASE_ID]
Costs one API call per level; not part of the eval scoreboard.
"""

import argparse
import io
import json
from pathlib import Path

from PIL import Image, ImageFilter

from ttb_label_reviewer.engine.canonical import CANONICAL_WARNING
from ttb_label_reviewer.engine.normalize import normalize_warning
from ttb_label_reviewer.extraction import DEFAULT_MODEL, AnthropicExtractor, LabelImage

GOLDEN_DIR = Path(__file__).parent

# (label, blur radius, downscale factor, jpeg quality)
LEVELS = [
    ("no degradation", 0.0, 1.0, 90),
    ("blur 2", 2.0, 1.0, 35),
    ("blur 3 + 50% scale", 3.0, 0.5, 30),
    ("blur 4 + 35% scale", 4.0, 0.35, 30),
    ("blur 6 + 25% scale", 6.0, 0.25, 25),
    ("blur 8 + 18% scale", 8.0, 0.18, 25),
    ("blur 10 + 15% scale (unreadable)", 10.0, 0.15, 20),
]


def degrade(img: Image.Image, blur: float, scale: float, quality: int) -> bytes:
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(blur))
    if scale != 1.0:
        img = img.resize(
            (int(img.width * scale), int(img.height * scale)), Image.BICUBIC
        )
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--case", default="compliant", dest="case_id")
    args = parser.parse_args()

    faithful = json.loads((GOLDEN_DIR / "faithful_extractions.json").read_text())
    expected = normalize_warning(
        faithful[args.case_id]["government_warning"]["raw_text"]
    ).lower()
    canonical = normalize_warning(CANONICAL_WARNING).lower()
    extractor = AnthropicExtractor(model=args.model)
    base = Image.open(GOLDEN_DIR / f"{args.case_id}.png").convert("RGB")

    print(f"model: {args.model}   case: {args.case_id}\n")
    print(f"{'level':<36} {'warn_conf':>9} {'min_conf':>8}  faithful?")
    for label, blur, scale, quality in LEVELS:
        data = degrade(base, blur, scale, quality)
        image = LabelImage(filename="probe.jpg", media_type="image/jpeg", data=data)
        extraction = extractor.extract([image])
        confs = [field.confidence for _, field in extraction if field is not None]
        warning = extraction.government_warning
        if warning is None:
            verdict, warn_conf = "warning not found", "—"
        else:
            got = normalize_warning(warning.raw_text).lower()
            if got == expected:
                verdict = "yes"
            elif got == canonical:
                verdict = "NO — AUTOCOMPLETED TO CANONICAL"
            else:
                verdict = "NO — deviates (not canonical)"
            warn_conf = f"{warning.confidence:.2f}"
        min_conf = f"{min(confs):.2f}" if confs else "—"
        print(f"{label:<36} {warn_conf:>9} {min_conf:>8}  {verdict}")


if __name__ == "__main__":
    main()
