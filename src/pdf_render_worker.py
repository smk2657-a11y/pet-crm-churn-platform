from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


def main() -> int:
    if len(sys.argv) < 2:
        print("payload path required", file=sys.stderr)
        return 1

    payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    html_path = Path(payload["html_path"]).resolve()
    pdf_path = Path(payload["pdf_path"]).resolve()
    css_path = Path(payload["css_path"]).resolve()

    html = html_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2200})
        page.emulate_media(media="print")
        page.set_content(html, wait_until="networkidle")
        page.add_style_tag(content=css)
        page.pdf(
            path=str(pdf_path),
            format="A4",
            print_background=True,
            margin={"top": "0mm", "right": "0mm", "bottom": "0mm", "left": "0mm"},
            prefer_css_page_size=True,
        )
        browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())