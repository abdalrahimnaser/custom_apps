"""Tray icon assets."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

_ICON_PATH = Path(__file__).resolve().parent / "icon.ico"


def create_icon_image(size: int = 64) -> Image.Image:
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    margin = size // 8
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=size // 6,
        fill=(37, 99, 235, 255),
    )
    inner = size // 4
    draw.rounded_rectangle(
        (inner, inner, size - inner, size - inner),
        radius=size // 10,
        fill=(255, 255, 255, 255),
    )
    dot = size // 2 - size // 16
    draw.ellipse(
        (dot, dot, size - dot, size - dot),
        fill=(37, 99, 235, 255),
    )
    return image


def ensure_icon_file() -> Path:
    if not _ICON_PATH.exists():
        image = create_icon_image(256)
        image.save(_ICON_PATH, format="ICO", sizes=[(256, 256), (64, 64), (32, 32), (16, 16)])
    return _ICON_PATH


def tray_icon() -> Image.Image:
    if _ICON_PATH.exists():
        return Image.open(_ICON_PATH).convert("RGBA")
    return create_icon_image(64)


if __name__ == "__main__":
    ensure_icon_file()
    print(f"Wrote {_ICON_PATH}")
