"""
Ulm Staatsangehörigkeitsbehörde slot checker.
Phase A: DEBUG mode — navigates to the portal, takes a screenshot
and saves the HTML so we can identify the right buttons/selectors.
"""
import os
import urllib.request
from playwright.sync_api import sync_playwright

PORTAL_URL = "https://ssc.wilkencloud.de/ulm/"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
DEBUG = os.environ.get("DEBUG", "1") == "1"   # Phase A: leave at 1

def notify(message: str):
    """Send a push notification to your phone via ntfy.sh."""
    if not NTFY_TOPIC:
        print("No NTFY_TOPIC set, skipping notification")
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": "Ulm Termin-Checker", "Priority": "high"},
    )
    urllib.request.urlopen(req)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.goto(PORTAL_URL, wait_until="networkidle")

        # ---- PHASE B LOGIC GOES HERE ----
        # After we see the debug screenshot, this section will contain
        # the clicks: select Behörde -> select Anliegen -> open calendar,
        # then check whether any bookable day/time exists.
        # ----------------------------------

        if DEBUG:
            page.screenshot(path="debug.png", full_page=True)
            with open("debug.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("Debug snapshot saved.")
        browser.close()

if __name__ == "__main__":
    main()
