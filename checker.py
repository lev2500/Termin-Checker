"""
Ulm Staatsangehoerigkeitsbehoerde slot checker - FINAL
Anliegen: "Anliegen rund um die Einbuergerung" (cnc-600)
Flow: start page (session) -> location page via direct URL -> Weiter
      -> suggest page -> check for "Kein freier Termin verfuegbar"
"""
import os
import urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://ssc.wilkencloud.de/ulm/"
STEP3_URL = BASE + "location?mdt=19&select_cnc=1&cnc-600=1"
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")

NO_SLOTS_TEXT = "Kein freier Termin verfügbar"


def notify(message: str, priority: str = "high"):
    if not NTFY_TOPIC:
        print("No NTFY_TOPIC set, skipping notification")
        return
    req = urllib.request.Request(
        f"https://ntfy.sh/{NTFY_TOPIC}",
        data=message.encode("utf-8"),
        headers={"Title": "Ulm Termin-Checker", "Priority": priority,
                 "Click": BASE},
    )
    urllib.request.urlopen(req)
    print(f"Notification sent: {message}")


def snapshot(page, name: str):
    page.screenshot(path=f"{name}.png", full_page=True)
    with open(f"{name}.html", "w", encoding="utf-8") as f:
        f.write(page.content())


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 1. Start page: establishes the session cookie
        page.goto(BASE, wait_until="networkidle")
        try:
            page.click("#cookie_msg_btn_yes", timeout=3000)
        except PWTimeout:
            pass

        # 2. Jump directly to the Standort page with Anliegen preselected
        page.goto(STEP3_URL, wait_until="networkidle")

        # 3. Click Weiter on the Standort page (single location in Ulm).
        #    Try the known TEVIS selectors in order.
        clicked = False
        for sel in ["#WeiterButton", "input[value='Weiter']",
                    "button:has-text('Weiter')"]:
            try:
                page.click(sel, timeout=4000)
                clicked = True
                print(f"Clicked Weiter via {sel}")
                break
            except PWTimeout:
                continue
        if not clicked:
            snapshot(page, "error_no_weiter")
            notify("Checker problem: Weiter button not found on "
                   "Standort page. Check the debug artifact.", "default")
            browser.close()
            return

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        content = page.content()
        snapshot(page, "last_check")

        # 4. Decide
        if NO_SLOTS_TEXT in content:
            print("No slots available.")
        elif "Terminvorschläge" in content or "suggest" in page.url:
            notify("TERMIN VERFÜGBAR! Staatsangehörigkeitsbehörde Ulm "
                   "hat freie Termine. Jetzt buchen: " + BASE)
        else:
            # Page looks different than expected - portal may have changed
            notify("Checker unsure: unexpected page layout. "
                   "Possibly slots available - check manually. " + BASE,
                   "default")

        browser.close()


if __name__ == "__main__":
    main()
