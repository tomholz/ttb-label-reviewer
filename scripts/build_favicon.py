"""Draw static/favicon.ico (16+32 px) to match static/favicon.svg —
the same label-shape-plus-checkmark in the site's federal blue. The
SVG is the design's source of truth and serves modern browsers; the
ICO answers the default /favicon.ico request from everything else.

Rerun if the design changes:

    uv run python scripts/build_favicon.py
"""

from pathlib import Path

from PIL import Image, ImageDraw

STATIC_DIR = Path(__file__).parent.parent / "src" / "ttb_label_reviewer" / "static"
FEDERAL_BLUE = (26, 68, 128, 255)  # --accent in style.css
WHITE = (255, 255, 255, 255)

# Drawn at 4x the SVG's 32-unit canvas and downscaled, for smooth edges.
SCALE = 4


def main() -> None:
    size = 32 * SCALE
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (1 * SCALE, 1 * SCALE, 31 * SCALE, 31 * SCALE),
        radius=7 * SCALE,
        fill=FEDERAL_BLUE,
    )
    check = [(8.5, 17), (14, 22.5), (23.5, 10.5)]
    points = [(x * SCALE, y * SCALE) for x, y in check]
    draw.line(points, fill=WHITE, width=4 * SCALE, joint="curve")
    # Round the stroke's ends, as the SVG's stroke-linecap does.
    radius = 2 * SCALE
    for x, y in (points[0], points[-1]):
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=WHITE)

    target = STATIC_DIR / "favicon.ico"
    image.save(target, format="ICO", sizes=[(16, 16), (32, 32)])
    print(f"wrote {target} ({target.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
