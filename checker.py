"""
Ulm Staatsangehoerigkeitsbehoerde slot checker - FINAL v3
Correct wizard order:
  start -> select2?md=4 -> tick cnc-600 -> Weiter (opens Hinweis modal)
  -> OK in modal (navigates to step 3 Standort) -> Weiter on Standort
  -> step 4 suggestions -> evaluate.
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


def click_weiter(page) -> bool:
    for sel in ["#WeiterButton", "input[value='Weiter']",
                "button:has-text('Weiter')"]:
        try:
            page.click(sel, timeout=4000)
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

        # 4. Weiter -> this OPENS the Hinweis modal (#TevisDialog)
        if not click_weiter(page):
            fail(page, browser, "error_step2_weiter",
                 "Weiter button not clickable on Anliegen page.")
            return

        # 5. Wait for the modal, then click its OK -> navigates to step 3
        try:
            page.wait_for_selector("#TevisDialog", state="visible",
                                   timeout=5000)
            page.click("#OKButton", timeout=5000)
            print("Hinweis modal OK clicked -> going to Standort")
        except PWTimeout:
            fail(page, browser, "error_modal",
                 "Hinweis modal / OKButton did not appear after Weiter.")
            return

        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

        # 6. Standort page -> Weiter -> step 4
        if not click_weiter(page):
            fail(page, browser, "error_step3_weiter",
                 "Weiter button not found on Standort page.")
            return
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)

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
