"""
Ulm Staatsangehörigkeitsbehörde slot checker.
Phase A2: DEBUG mode — goes straight to the Staatsangehörigkeitsbehörde
(step 2), snapshots the Anliegen list, then tries to reach the calendar
(step 3) and snapshots that too.
"""
import os
import urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

STEP2_URL = "https://ssc.wilkencloud.de/ulm/select2?md=4"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
DEBUG = os.environ.get("DEBUG", "1") == "1"


def notify(message: str):
    if not NTFY_TOPIC:
        print("No NTFY_TOPIC set, skipping notification")
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": "Ulm Termin-Checker", "Priority": "high"},
    )
    urllib.request.urlopen(req)


def snapshot(page, name: str):
    page.screenshot(path=f"{name}.png", full_page=True)
    with open(f"{name}.html", "w", encoding="utf-8") as f:
        f.write(page.content())
    print(f"Snapshot saved: {name}")


def accept_cookies(page):
    try:
        page.click("#cookie_msg_btn_yes", timeout=3000)
        print("Cookie banner accepted")
    except PWTimeout:
        print("No cookie banner shown")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # --- Step 2: Anliegen list for Staatsangehoerigkeitsbehoerde ---
        page.goto(STEP2_URL, wait_until="networkidle")
        accept_cookies(page)
        snapshot(page, "step2_anliegen")

        # --- Try to reach Step 3 (calendar) generically ---
        # TEVIS portals usually have a "+" per Anliegen and a Weiter button.
        try:
            plus_buttons = page.locator(
                "input[id^='button-plus'], button[id^='button-plus']"
            )
            count = plus_buttons.count()
            print(f"Found {count} plus-buttons")
            if count > 0:
                plus_buttons.first.click()
                page.wait_for_timeout(1000)

            # Common ids/labels for the continue button on TEVIS:
            for sel in ["#WeiterButton", "input[value='Weiter']",
                        "button:has-text('Weiter')"]:
                try:
                    page.click(sel, timeout=3000)
                    print(f"Clicked continue via {sel}")
                    break
                except PWTimeout:
                    continue

            # Some portals show an info modal with an OK/Weiter confirm:
            for sel in ["#OKNewWindow", "button:has-text('OK')",
                        "#dialog_weiter", "button:has-text('Weiter')"]:
                try:
                    page.click(sel, timeout=2000)
                    print(f"Clicked modal confirm via {sel}")
                    break
                except PWTimeout:
                    continue

            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
            snapshot(page, "step3_calendar")
        except Exception as e:
            print(f"Could not reach step 3 automatically: {e}")
            snapshot(page, "step3_attempt")

        browser.close()


if __name__ == "__main__":
    main()
