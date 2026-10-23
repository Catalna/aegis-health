"""Rasterise the deterministic SVG chart strings to PNG images.

Uses headless Chromium through Playwright, which is already a development
dependency in this repository. No web page is produced or kept.
"""

from __future__ import annotations

import re
from pathlib import Path

_SIZE = re.compile(r'width="(\d+)" height="(\d+)"')


def svg_dimensions(svg: str) -> tuple[int, int]:
    match = _SIZE.search(svg)
    if not match:
        raise ValueError("SVG root must declare numeric width and height")
    return int(match.group(1)), int(match.group(2))


def render_svg_files(
    figures: dict[str, str],
    destinations: dict[str, Path],
    *,
    scale: int = 2,
) -> None:
    """Write each SVG string to a PNG at the matching destination."""
    if not figures:
        return
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover - environment guard
        raise RuntimeError(
            "Playwright is required to rasterise figures; install it with 'pip install playwright' "
            "and run 'playwright install chromium'."
        ) from exc

    width, height = svg_dimensions(next(iter(figures.values())))
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(device_scale_factor=scale, viewport={"width": width, "height": height})
        try:
            for key, svg in figures.items():
                width, height = svg_dimensions(svg)
                page.set_viewport_size({"width": width, "height": height})
                page.set_content(
                    "<!doctype html><html><head><meta charset='utf-8'>"
                    "<style>html,body{margin:0;padding:0;background:#fff}svg{display:block}</style>"
                    f"</head><body>{svg}</body></html>"
                )
                destination = destinations[key]
                destination.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(path=str(destination), type="png")
        finally:
            browser.close()
