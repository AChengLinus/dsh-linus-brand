"""Regenerate the pet sprite sheets that this bundle serves.

The skin drives the composer pet by translating a sprite strip one cell every
52 ms; it never animates the artwork itself. So the animation is entirely a
matter of *what sits in each cell*: this script paints one distinct pose per
cell, which turns the strip into a 19 fps loop.

Usage (from the repository root):

    python3 tools/build-sheets.py                # writes assets/*.svg
    python3 tools/build-sheets.py --out /tmp/out # somewhere else

Requirements: Pillow (``pip install pillow``). WebP support is part of Pillow's
standard build.

Geometry, in SVG user units (the skin multiplies one logical pixel by 5):

    strip width  = 8 columns * cell width
    strip height = rows * cell height
    one cell     = the sprite window the skin shows, e.g. 54x35 for "typing"

Frames are encoded as lossy WebP because 48-72 PNG frames per state would be
~30 MB per sheet; WebP keeps the alpha channel at a fraction of that.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import math
import os

from PIL import Image, ImageDraw

# state -> (strip width, strip height, rows)  -- copied from the skin's sheets
DIMS = {
    "idle": (1520, 780, 6),
    "idle-look": (1560, 1845, 9),
    "idle-spout": (1640, 1400, 8),
    "thinking": (1960, 1380, 6),
    "typing": (2160, 1050, 6),
    "music": (2000, 840, 4),
    "conducting": (2120, 1560, 6),
    "building": (2080, 1560, 6),
    "error": (1880, 1050, 6),
    "happy": (2160, 1645, 7),
    "notification": (1960, 900, 4),
    "compacting": (1920, 1330, 7),
    "sleeping": (1840, 2000, 8),
    "waking": (1840, 960, 4),
    "poke-left": (2080, 900, 5),
    "poke-right": (1840, 900, 5),
    "tickle": (1800, 1050, 6),
    "drag": (1720, 720, 3),
}

# state -> pose file (tools/poses/<pose>.png)
POSE = {
    "idle": "console",
    "idle-look": "console",
    "idle-spout": "brew",
    "thinking": "writing",
    "typing": "keyboard",
    "music": "gaming",
    "conducting": "easel",
    "building": "laptop",
    "error": "gaming",
    "happy": "coffee",
    "notification": "brew",
    "compacting": "writing",
    "sleeping": "console",
    "waking": "console",
    "poke-left": "coffee",
    "poke-right": "coffee",
    "tickle": "easel",
    "drag": "keyboard",
}

# state -> (bob in raster px, cycles per loop, sway in raster px, particle theme)
# 3 raster px = 1 logical px = 2 CSS px, so 7 raster px of bob is ~4.7 CSS px.
MOTION = {
    "idle": (7, 1, 3, "calm"),
    "idle-look": (6, 1, 4, "calm"),
    "idle-spout": (7, 1, 3, "calm"),
    "thinking": (6, 2, 2, "work"),
    "typing": (6, 2, 2, "work"),
    "music": (9, 1, 5, "play"),
    "conducting": (7, 1, 4, "work"),
    "building": (6, 2, 2, "work"),
    "error": (7, 1, 4, "alert"),
    "happy": (9, 1, 5, "play"),
    "notification": (7, 1, 3, "calm"),
    "compacting": (6, 2, 2, "work"),
    "sleeping": (4, 1, 2, "calm"),
    "waking": (8, 1, 3, "calm"),
    "poke-left": (8, 1, 6, "play"),
    "poke-right": (8, 1, 6, "play"),
    "tickle": (8, 1, 6, "play"),
    "drag": (6, 1, 4, "work"),
}

# theme -> (particle colour, highlight colour, particles per frame, (min size, max size))
THEMES = {
    "calm": ((255, 238, 197), (255, 255, 255), 5, (3, 6)),
    "work": ((168, 214, 255), (255, 255, 255), 5, (3, 6)),
    "play": ((255, 214, 150), (255, 244, 190), 6, (3, 7)),
    "alert": ((255, 168, 150), (255, 226, 210), 6, (3, 7)),
}

FRAME_MS = 52          # the skin steps one cell every 52 ms; keep this in step
DEVICE = 1.5           # bake at 1.5x so the browser downsamples instead of blurring
QUALITY = 82           # WebP quality, alpha preserved


def cell_pixels(cell_w: float, cell_h: float) -> tuple[int, int]:
    """Raster size of one cell: CSS pixels at DEVICE scale."""
    css_w = cell_w * 2 / 5
    width = round(css_w * DEVICE)
    return (width, max(48, round(width * cell_h / cell_w)))


def draw_art(canvas: Image.Image, art: Image.Image, bob: float, sway: float) -> None:
    x = (canvas.width - art.width) // 2 + round(sway)
    y = canvas.height - 3 - art.height + round(bob)
    canvas.alpha_composite(art, (max(0, x), max(0, y)))


def free_spot(art: Image.Image, px: int, py: int, size_px: int) -> bool:
    """True when the art has nothing behind this square, so a particle may sit there."""
    if px < 0 or py < 0 or px >= art.width or py >= art.height:
        return False
    x1 = min(art.width - 1, px + size_px)
    y1 = min(art.height - 1, py + size_px)
    box = art.crop((px, py, x1 + 1, y1 + 1)).getchannel("A")
    return box.getextrema()[1] < 32


def draw_particles(canvas, art, theme, index, frames, behind=False):
    colour, accent, count, (lo, hi) = THEMES[theme]
    width, height = canvas.size
    draw = ImageDraw.Draw(canvas)
    band_bottom = int(height * 0.5)
    drawn = 0
    for i in range(count * 4):
        if drawn >= count:
            break
        seed = (i * 47 + 13) % 97
        # gentle linear drift with a soft fade in and out at the ends of the loop
        cycle = ((index / frames) + seed / 97.0) % 1.0
        size_px = lo + (seed + i) % (hi - lo + 1)
        px = 4 + int((seed * 71) % max(1, width - size_px - 8))
        py = band_bottom - int(band_bottom * 0.8 * cycle)
        edge = min(cycle, 1 - cycle) * 4.0
        alpha = int(220 * min(1.0, edge) ** 0.8)
        if alpha <= 10 or py < 2 or not free_spot(art, px, py, size_px):
            continue
        drawn += 1
        tone = accent if i % 3 == 0 else colour
        a = alpha if not behind else max(40, alpha // 2)
        draw.rectangle((px, py, px + size_px, py + size_px), fill=tone + (a,))
        if size_px >= 5:
            tail = max(1, size_px // 3)
            draw.rectangle(
                (px + size_px // 2, py + size_px + 1, px + size_px // 2 + tail, py + size_px + 1 + tail),
                fill=tone + (max(28, a // 2),),
            )
        if i % 4 == 0:
            gx, gy, g = px + size_px // 2, py - 4, max(1, size_px // 3)
            if gy > 2:
                draw.rectangle((gx - g * 2, gy, gx + g * 2, gy + 1), fill=accent + (a // 2,))
                draw.rectangle((gx, gy - g * 2, gx + 1, gy + g * 2), fill=accent + (a // 2,))


def encode(frame: Image.Image) -> str:
    buffer = io.BytesIO()
    frame.convert("RGBA").save(buffer, "WEBP", quality=QUALITY, method=6)
    return base64.b64encode(buffer.getvalue()).decode()


def build(out_dir: str, pose_dir: str) -> dict:
    os.makedirs(out_dir, exist_ok=True)
    manifest = {}
    for name, (svg_w, svg_h, rows) in DIMS.items():
        cell_w, cell_h = svg_w / 8, svg_h / rows
        frames_n = 8 * rows  # one pose per cell: the strip never repeats a picture
        amp, mul, sway_amp, theme = MOTION[name]
        pose = Image.open(os.path.join(pose_dir, f"{POSE[name]}.png")).convert("RGBA")
        size = cell_pixels(cell_w, cell_h)

        # scale the artwork exactly once: every frame carries it at the same size
        headroom = amp + 6
        fit_h = size[1] - headroom - 3
        fit_w = int(size[0] * 0.94)
        scale = min(fit_w / pose.width, fit_h / pose.height)
        art_static = pose.resize(
            (max(1, int(pose.width * scale)), max(1, int(pose.height * scale))), Image.LANCZOS
        )

        frames = []
        for i in range(frames_n):
            phase = 2 * math.pi * (i / frames_n) * mul
            bob = -amp * (0.5 - 0.5 * math.cos(phase))
            sway = sway_amp * math.sin(phase)
            canvas = Image.new("RGBA", size, (0, 0, 0, 0))
            art = Image.new("RGBA", size, (0, 0, 0, 0))
            draw_art(art, art_static, bob, sway)
            draw_particles(canvas, art, theme, i, frames_n, behind=True)
            canvas.alpha_composite(art)
            draw_particles(canvas, art, theme, i, frames_n, behind=False)
            frames.append(encode(canvas))

        defs = "".join(
            f'<image id="f{i}" x="0" y="0" width="{cell_w:.3f}" height="{cell_h:.3f}" '
            f'preserveAspectRatio="xMidYMid meet" xlink:href="data:image/webp;base64,{b64}"/>'
            for i, b64 in enumerate(frames)
        )
        uses = "".join(
            f'<use xlink:href="#f{r * 8 + c}" x="{c * cell_w:.3f}" y="{r * cell_h:.3f}"/>'
            for r in range(rows)
            for c in range(8)
        )
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{svg_w}" height="{svg_h}" viewBox="0 0 {svg_w} {svg_h}">'
            f'<defs>{defs}</defs>{uses}</svg>'
        )
        with open(os.path.join(out_dir, name + ".svg"), "w", encoding="utf8") as handle:
            handle.write(svg)
        manifest[name] = {
            "w": svg_w,
            "h": svg_h,
            "rows": rows,
            "cell": [round(cell_w, 2), round(cell_h, 2)],
            "pose": POSE[name],
            "frames": frames_n,
            "frame_ms": FRAME_MS,
            "cycle_ms": frames_n * FRAME_MS,
            "raster": list(size),
            "codec": "webp",
            "quality": QUALITY,
            "bytes": len(svg),
        }
        print(
            f"{name:12s} rows={rows} frames={frames_n:2d} cycle={frames_n * FRAME_MS:4d}ms "
            f"raster={size} svg={len(svg) / 1024:.0f}KB"
        )

    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf8") as handle:
        json.dump(manifest, handle, indent=1)
    print("total svg bytes:", round(sum(m["bytes"] for m in manifest.values()) / 1024 / 1024, 2), "MB")
    return manifest


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser = argparse.ArgumentParser(description="Build the pet sprite sheets.")
    parser.add_argument("--out", default=os.path.join(root, "assets"), help="output directory for *.svg")
    parser.add_argument(
        "--poses", default=os.path.join(root, "tools", "poses"), help="directory holding the pose PNGs"
    )
    args = parser.parse_args()
    build(args.out, args.poses)


if __name__ == "__main__":
    main()
