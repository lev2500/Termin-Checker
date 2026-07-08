"""
Ulm Staatsangehoerigkeitsbehoerde slot checker - FINAL v4
Weiter is a submit button that opens a modal instead of navigating,
so we click it fire-and-forget and confirm success via the modal.
"""
import os
import urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

BASE = "https://ssc.wilkencloud.de/ulm/"
STEP2_URL = BASE + "select2?md=4"
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


def click_weiter(page):
    """Click Weiter without waiting for navigation (it may open a modal
    instead). no_wait_after avoids a false timeout on submit buttons."""
    for sel in ["#WeiterButton", "input[value='Weiter']",
                "button:has-text('Weiter')"]:
        try:
            page.click(sel, timeout=4000, no_wait_after=True)
            print(f"Clicked Weiter via {sel}")
            return True
        except PWTimeout:
            continue
    return False


def fail(page, browser, name: str, msg: str):
    snapshot(page, name)
    notify(f"Checker problem: {msg} Check the debug artifact.", "default")
    browser.close()


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()

        # 1. Start page -> session + cookies
        page.goto(BASE, wait_until="networkidle")
        try:
            page.click("#cookie_msg_btn_yes", timeout=3000)
        except PWTimeout:
            pass

        # 2. Step 2: Anliegen page
        page.goto(STEP2_URL, wait_until="networkidle")

        # 3. Tick the Einbuergerung checkbox (custom-styled span)
        try:
            page.click("#span-cnc-600", timeout=5000)
        except PWTimeout:
            try:
                page.check("#cnc-600", force=True)
            except Exception:
                fail(page, browser, "error_checkbox",
                     "Anliegen checkbox cnc-600 not found.")
                return
        page.wait_for_timeout(500)

        # 4. Weiter -> opens the Hinweis modal (fire-and-forget)
        click_weiter(page)

        # 5. Confirm the modal opened, then click OK -> navigates to step 3
        try:
            page.wait_for_selector("#TevisDialog.in", timeout=6000)
            page.click("#OKButton", timeout=5000, no_wait_after=True)
            print("Hinweis modal OK clicked -> going to Standort")
        except PWTimeout:
            fail(page, browser, "error_modal",
                 "Hinweis modal did not open after Weiter.")
            return

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)

        # 6. Standort page -> Weiter -> step 4.
        #    This Weiter DOES navigate, so allow the default wait.
        clicked = False
        for sel in ["#WeiterButton", "input[value='Weiter']",
                    "button:has-text('Weiter')"]:
            try:
                page.click(sel, timeout=5000)
                clicked = True
                print(f"Clicked Standort Weiter via {sel}")
                break
            except PWTimeout:
                continue
        if not clicked:
            fail(page, browser, "error_step3_weiter",
                 "Weiter button not found on Standort page.")
            return

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2500)

        # 7. Evaluate step 4
        content = page.content()
        snapshot(page, "last_check")

        if NO_SLOTS_TEXT in content:
            print("No slots available.")
        elif "Terminvorschläge" in content or "suggest" in page.url:
            notify("TERMIN VERFÜGBAR! Staatsangehörigkeitsbehörde Ulm "
                   "hat freie Termine. Jetzt buchen: " + BASE)
        else:
            notify("Checker unsure: unexpected page layout. "
                   "Possibly slots available - check manually. " + BASE,
                   "default")

        browser.close()


if __name__ == "__main__":
    main()
