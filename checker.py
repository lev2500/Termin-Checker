"""
Ulm Staatsangehoerigkeitsbehoerde slot checker - FINAL v6
Correct two-modal flow (confirmed by user):
  tick cnc-600 -> OK (modal 1, enables Weiter) -> Weiter
  -> OK (modal 2) -> step 3 Standort -> Weiter -> step 4 -> evaluate.
Verifies the Schritt (step) via page title before each transition.
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


def fail(page, browser, name: str, msg: str):
    snapshot(page, name)
    notify(f"Checker problem: {msg} Check the debug artifact.", "default")
    browser.close()


def dismiss_modal_if_open(page, label: str):
    """If the TevisDialog modal is open, click its OK and wait for it
    to close. Returns True if a modal was handled."""
    try:
        page.wait_for_selector("#TevisDialog.in", timeout=5000)
    except PWTimeout:
        print(f"[{label}] no modal appeared")
        return False
    page.click("#OKButton", no_wait_after=True)
    try:
        page.wait_for_selector("#TevisDialog.in", state="hidden",
                               timeout=5000)
    except PWTimeout:
        pass
    print(f"[{label}] modal OK clicked")
    return True


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

        # 3. Tick the Einbuergerung checkbox -> MODAL 1 opens
        try:
            page.click("#span-cnc-600", timeout=5000)
        except PWTimeout:
            try:
                page.check("#cnc-600", force=True)
            except Exception:
                fail(page, browser, "error_checkbox",
                     "Anliegen checkbox cnc-600 not found.")
                return

        # 3b. Handle MODAL 1 ("...kein weiteres Anliegen mehr zu")
        dismiss_modal_if_open(page, "modal1")

        # 4. Weiter should now be enabled -> click it -> MODAL 2 opens
        try:
            page.wait_for_selector(
                "#WeiterButton:not(.disabledButton)", timeout=5000)
        except PWTimeout:
            fail(page, browser, "error_weiter_disabled",
                 "Weiter did not become enabled after modal 1.")
            return
        page.click("#WeiterButton", no_wait_after=True)

        # 4b. Handle MODAL 2 ("Bitte buchen Sie einen Termin pro Person")
        dismiss_modal_if_open(page, "modal2")

        # 5. After modal 2 OK we must advance past step 2
        try:
            page.wait_for_function(
                "() => !document.title.includes('Schritt 2')",
                timeout=10000,
            )
        except PWTimeout:
            fail(page, browser, "error_stuck_step2",
                 "Did not advance past step 2 after modal 2.")
            return
        page.wait_for_load_state("networkidle")
        print(f"Advanced to: {page.title()}")

        # 6. Step 3 Standort -> Weiter (navigates normally) -> step 4
        if "Schritt 3" not in page.title():
            fail(page, browser, "error_not_step3",
                 f"Expected step 3, got: {page.title()}")
            return
        page.click("#WeiterButton")
        try:
            page.wait_for_function(
                "() => document.title.includes('Schritt 4')",
                timeout=10000,
            )
        except PWTimeout:
            fail(page, browser, "error_not_step4",
                 f"Did not reach step 4. Title: {page.title()}")
            return
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        print(f"Reached: {page.title()}")

        # 7. Evaluate step 4
        content = page.content()
        snapshot(page, "last_check")

        if NO_SLOTS_TEXT in content:
            print("No slots available.")
        elif "verfügbar" not in page.title() and \
                "Terminvorschläge" in content:
            notify("TERMIN VERFÜGBAR! Staatsangehörigkeitsbehörde Ulm "
                   "hat freie Termine. Jetzt buchen: " + BASE)
        else:
            notify("Checker unsure on step 4: unexpected layout. "
                   "Check manually. " + BASE, "default")

        browser.close()


if __name__ == "__main__":
    main()
