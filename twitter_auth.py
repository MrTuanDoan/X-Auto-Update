import os
from pathlib import Path
from playwright.sync_api import sync_playwright

WORKSPACE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(WORKSPACE_DIR, "twitter_state.json")

def login_and_save_state():
    print("Starting Twitter login process...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()

        page.goto("https://twitter.com/login")
        print("Please log in to your Twitter account in the browser window.")
        print("Waiting for the home timeline to load (timeout 5 minutes)...")
        
        try:
            # We wait for the timeline block to be present
            page.wait_for_selector('[aria-label="Timeline: Your Home Timeline"]', timeout=300000)
            print("Login successful! Saving session state...")
            context.storage_state(path=STATE_FILE)
            print(f"✅ Session state saved to {STATE_FILE}. You can now run the Telegram bot.")
        except Exception as e:
            print(f"Error during login: {e}")
            print("Timed out waiting for login. Please try again.")
        finally:
            browser.close()

if __name__ == "__main__":
    login_and_save_state()
