"""
link_extraction.py — Step 1: Collect product URLs (Cloudflare-resilient)
"""

import csv
import os
import random
import sys
import time

from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
from lxml import html

# 🔥 Use undetected chromedriver instead of selenium default
import undetected_chromedriver as uc


# ── Load environment ───────────────────────────────────────────────────────────
load_dotenv()

SELLER_NAME   = os.getenv("SELLER_NAME", "").strip()
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "").strip()

if not SELLER_NAME:
    sys.exit("❌ SELLER_NAME is not set in .env")
if not TARGET_DOMAIN:
    sys.exit("❌ TARGET_DOMAIN is not set in .env")


# ── USER CONFIG ────────────────────────────────────────────────────────────────
PRODUCT_LINK_XPATH = '//div[@class="image-container text-center"]/../@href'
SCROLL_PAUSE = 3.0
MAX_STALE_SCROLLS = 5


# ── File paths ─────────────────────────────────────────────────────────────────
DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

ENTRYPOINTS_FILE = DATA_DIR / f"{SELLER_NAME}_entrypoints.csv"
OUTPUT_FILE      = DATA_DIR / f"{SELLER_NAME}_urls.csv"


# ── Driver Setup (Cloudflare resistant) ────────────────────────────────────────
# def create_driver():
#     options = uc.ChromeOptions()

#     options.add_argument("--start-maximized")
#     options.add_argument("--disable-blink-features=AutomationControlled")

#     user_agents = [
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#         "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
#         "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
#     ]
#     options.add_argument(f"user-agent={random.choice(user_agents)}")

#     options.add_argument("--disable-infobars")
#     options.add_argument("--no-sandbox")
#     options.add_argument("--disable-dev-shm-usage")

#     driver = uc.Chrome(options=options)

#     # Remove webdriver flag
#     # driver.execute_script("""
#     #     Object.defineProperty(navigator, 'webdriver', {
#     #         get: () => undefined
#     #     })
#     # """)

#     return driver

def create_driver():
    for attempt in range(3):
        try:
            options = uc.ChromeOptions()

            options.add_argument("--start-maximized")
            options.add_argument("--disable-blink-features=AutomationControlled")

            user_agents = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
            ]
            options.add_argument(f"user-agent={random.choice(user_agents)}")

            options.add_argument("--disable-infobars")
            options.add_argument("--no-sandbox")
            options.add_argument("--disable-dev-shm-usage")

            driver = uc.Chrome(options=options)
            driver.implicitly_wait(5)

            return driver

        except Exception as e:
            print(f"⚠ Driver init failed (attempt {attempt+1}): {e}")
            time.sleep(2)

    raise Exception("❌ Failed to initialize driver")
driver = create_driver()
driver.implicitly_wait(5)

def is_driver_alive(driver):
    try:
        driver.current_url
        return True
    except:
        return False
if not is_driver_alive(driver):
    print("❌ Driver died. Recreating...")
    driver = create_driver()
# ── Helpers ────────────────────────────────────────────────────────────────────

def human_delay(a=2.0, b=4.0):
    time.sleep(random.uniform(a, b))


def wait_for_cloudflare():
    """Wait until Cloudflare challenge disappears"""
    for _ in range(20):
        if "cf-challenge" not in driver.page_source.lower():
            return
        print("⏳ Waiting for Cloudflare challenge...")
        time.sleep(3)


def load_entrypoints(filepath: Path) -> list[str]:
    if not filepath.exists():
        sys.exit(f"❌ Entrypoints file not found: {filepath}")

    entrypoints = []
    with open(filepath, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row:
                continue
            url = row[0].strip()
            if url.lower() in ("url", "link", "entrypoint", ""):
                continue
            entrypoints.append(url)
    return entrypoints


def scroll_to_bottom(pause=SCROLL_PAUSE, max_stale=MAX_STALE_SCROLLS):
    last_height = driver.execute_script("return document.body.scrollHeight")
    stale_count = 0

    while stale_count < max_stale:
        # Human-like chunk scrolling
        for _ in range(random.randint(2, 5)):
            driver.execute_script("window.scrollBy(0, window.innerHeight/2);")
            time.sleep(random.uniform(0.5, 1.2))

        time.sleep(pause)

        new_height = driver.execute_script("return document.body.scrollHeight")

        if new_height == last_height:
            stale_count += 1
            print(f"    ⚠ No new content ({stale_count}/{max_stale})")
        else:
            stale_count = 0
            print(f"    ✔ Loaded more content")
            last_height = new_height

    print("    ↳ Page fully loaded\n")


def make_absolute(href: str, base_url: str) -> str | None:
    href = href.strip()

    if not href or href.startswith("#"):
        return None

    if href.startswith("//"):
        scheme = urlparse(base_url).scheme
        return f"{scheme}:{href}"

    if href.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"

    if href.startswith("http"):
        return href

    return None


def extract_product_urls(xpath: str) -> set[str]:
    tree = html.fromstring(driver.page_source)
    base = driver.current_url
    results = tree.xpath(xpath)

    if not results:
        print("    ⚠ XPath returned 0 results")
        return set()

    urls = set()

    for item in results:
        href = item if isinstance(item, str) else item.get("href", "")
        absolute = make_absolute(href, base)

        if absolute:
            urls.add(absolute)

    return urls


def save_urls(urls: set[str], filepath: Path):
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])

        for url in sorted(urls):
            writer.writerow([url])

    print(f"\n✅ Saved {len(urls)} URLs → {filepath}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"Seller      : {SELLER_NAME}")
    print(f"Domain      : {TARGET_DOMAIN}")
    print(f"{'='*60}\n")

    entrypoints = load_entrypoints(ENTRYPOINTS_FILE)
    print(f"📋 {len(entrypoints)} entry point(s)\n")

    all_urls = set()

    # for idx, ep_url in enumerate(entrypoints, start=1):
    #     print(f"[{idx}/{len(entrypoints)}] Visiting: {ep_url}")

    #     driver.get(ep_url)

    #     wait_for_cloudflare()
    #     human_delay()

    #     scroll_to_bottom()

    #     found = extract_product_urls(PRODUCT_LINK_XPATH)
    #     new   = found - all_urls
    #     all_urls |= found

    #     print(f"    ✔ {len(found)} found — {len(new)} new\n")
    driver = create_driver()

    for idx, ep_url in enumerate(entrypoints, start=1):

        if not is_driver_alive(driver):
            print("❌ Driver died. Recreating...")
            try:
                driver.quit()
            except:
                pass
            driver = create_driver()

        print(f"[{idx}/{len(entrypoints)}] Visiting: {ep_url}")

        # Safe page load
        try:
            driver.get(ep_url)
        except Exception as e:
            print(f"⚠ get() failed: {e}")
            driver = create_driver()
            driver.get(ep_url)

        wait_for_cloudflare(driver)
        human_delay()

        # Safe scrolling
        try:
            scroll_to_bottom(driver)
        except Exception as e:
            print(f"⚠ Scroll failed: {e}")

        # Extract
        found = extract_product_urls(driver, PRODUCT_LINK_XPATH)
        new   = found - all_urls
        all_urls |= found

        print(f"    ✔ {len(found)} found — {len(new)} new\n")

    save_urls(all_urls, OUTPUT_FILE)

    print("\n👉 Next: run main.py\n")


if __name__ == "__main__":
    main()
    try:
        driver.quit()
    except:
        pass