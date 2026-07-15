#!/usr/bin/env python3
"""
Regenerate RAL CRM's workspace logo files from the real RAL brand mark.

Source: brand/source/ral_wordmark.png — the RAL wordmark, copied verbatim
from the main RAL workspace repo (assets/branding/logo_main.png). Do not
hand-edit; if the master wordmark changes, re-copy it from there.

Brand colors (source of truth: every proposal/deck generator in the main
RAL workspace repo, e.g. execution/generate_proposal.py):
  Plum  #2B1B3D
  Lilac #D1C4E9

Twenty CRM's workspace logo requirement (Settings -> General -> Workspace):
square PNG, transparent background preferred, minimum 512x512.
https://twenty.com/user-guide/section/getting-started/configure-your-workspace

Usage:
    python brand/generate-logos.py
"""
from pathlib import Path
from PIL import Image

BRAND_DIR = Path(__file__).parent
SOURCE = BRAND_DIR / "source" / "ral_wordmark.png"
OUT = BRAND_DIR / "out"

PLUM = (0x2B, 0x1B, 0x3D, 255)
LILAC = (0xD1, 0xC4, 0xE9, 255)

# (filename, canvas size, background, wordmark tint, margin fraction)
TARGETS = [
    ("ral-crm-icon-512.png", 512, PLUM, LILAC, 0.16),
    ("ral-crm-icon-1024.png", 1024, PLUM, LILAC, 0.16),
    ("ral-crm-icon-transparent-512.png", 512, None, PLUM, 0.16),
]


def tinted(mark: Image.Image, color: tuple) -> Image.Image:
    """Recolor the wordmark's alpha shape to a flat brand color."""
    solid = Image.new("RGBA", mark.size, color)
    solid.putalpha(mark.split()[-1])
    return solid


def render(mark: Image.Image, size: int, bg, tint, margin: float) -> Image.Image:
    canvas = Image.new("RGBA", (size, size), bg if bg else (0, 0, 0, 0))
    usable = int(size * (1 - 2 * margin))
    mark_tinted = tinted(mark, tint)
    scale = min(usable / mark_tinted.width, usable / mark_tinted.height)
    new_size = (max(1, int(mark_tinted.width * scale)), max(1, int(mark_tinted.height * scale)))
    resized = mark_tinted.resize(new_size, Image.LANCZOS)
    pos = ((size - new_size[0]) // 2, (size - new_size[1]) // 2)
    canvas.paste(resized, pos, resized)
    return canvas


def main():
    if not SOURCE.exists():
        raise SystemExit(
            f"Missing {SOURCE}. Copy the master wordmark from the RAL "
            "workspace repo's assets/branding/logo_main.png first."
        )
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.open(SOURCE).convert("RGBA")
    bbox = src.getbbox()
    mark = src.crop(bbox)

    for filename, size, bg, tint, margin in TARGETS:
        out_path = OUT / filename
        render(mark, size, bg, tint, margin).save(out_path)
        print(f"wrote {out_path.relative_to(BRAND_DIR.parent)}")


if __name__ == "__main__":
    main()
