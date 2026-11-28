"""Grafana panosunun ekran görüntüsünü alır (CI'da ölçüm sonrası artefakt olarak saklanır).

Kullanım: python deploy/grafana/screenshot.py http://localhost:3000 grafana.png
"""

import sys

from playwright.sync_api import sync_playwright


def main(base_url: str, out: str) -> None:
    url = f"{base_url}/d/voice-latency?orgId=1&from=now-30m&to=now&kiosk"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(5000)  # paneller sorgularını tamamlasın
        page.screenshot(path=out, full_page=True)
        browser.close()


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
