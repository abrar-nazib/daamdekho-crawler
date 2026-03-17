import time
from dotenv import load_dotenv
import os
from selenium.webdriver.common.by import By
from selenium import webdriver
# from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import random
from lxml import html
import csv
import re
load_dotenv()
from urllib.parse import urlparse

# ─────────────────────────────────────────────
#  USER CONFIGURATION  ← edit these
# ─────────────────────────────────────────────
SELLER_NAME = os.getenv("SELLER_NAME")       # used to build file-paths

# XPath expression that matches every product <a> element on a listing page.
# Examples:
#   "//a[@class='product-card']"            – anchor with class "product-card"
#   "//div[@class='product-item']/a"        – first anchor inside a product div
#   "//a[contains(@href, '/products/')]"    – any anchor whose href contains /products/
#   "//a[contains(@class, 'item-link')]"    – anchor whose class contains "item-link"
PRODUCT_LINK_XPATH = '//div[@class="woocommerce-loop-product__title"]/a/@href'

# Optional: only keep URLs that match this regex (set to None to keep all).
# Example: r"/product/\d+"  keeps only URLs like /product/123
PRODUCT_URL_REGEX = None                # e.g. r"/product/\d+"

# Seconds to wait after each scroll step before checking for new content.
SCROLL_PAUSE = 2.0

# Maximum number of consecutive scrolls that yield no new height change
# before the scraper decides the page is fully loaded.
MAX_STALE_SCROLLS = 3
# ─────────────────────────────────────────────

options = webdriver.ChromeOptions()
options.add_experimental_option("detach", True)   # keeps browser open after script ends
options.add_experimental_option("excludeSwitches", ["enable-logging"])
driver = webdriver.Chrome(options=options)
driver.implicitly_wait(5)
# wait = WebDriverWait(driver, 15)
input_file = "basic_output.csv"

# ── file paths ────────────────────────────────
ENTRYPOINTS_FILE = os.path.join("data", f"{SELLER_NAME}_entrypoints.csv")
OUTPUT_FILE      = f"{SELLER_NAME}_urls.csv"



def load_entrypoints(filepath: str) -> list[str]:
    """Read entry-point URLs from a single-column CSV (header optional)."""
    entrypoints = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        for row in reader:
            if not row:
                continue
            url = row[0].strip()
            # skip header rows / empty values
            if url.lower() in ("url", "link", "entrypoint", ""):
                continue
            entrypoints.append(url)
    return entrypoints
 
 
def scroll_to_bottom(pause: float = SCROLL_PAUSE,
                     max_stale: int = MAX_STALE_SCROLLS) -> None:
    """
    Scroll to the page bottom repeatedly until the document height stops
    growing for `max_stale` consecutive attempts (handles infinite scroll).
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    stale_count = 0
    scroll_num  = 0
 
    while stale_count < max_stale:
        scroll_num += 1
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        # Random jitter keeps timing less predictable
        time.sleep(pause + random.uniform(0.2, 0.8))
 
        new_height = driver.execute_script("return document.body.scrollHeight")
 
        if new_height == last_height:
            stale_count += 1
            print(f"    scroll #{scroll_num} – no new content "
                  f"({stale_count}/{max_stale} stale)")
        else:
            stale_count = 0
            print(f"    scroll #{scroll_num} – height {last_height} → {new_height}px")
            last_height = new_height
 
    print(f"    ↳ Page fully loaded (final height={last_height}px)\n")
 
 
def make_absolute(href: str, base_url: str) -> str | None:
    """
    Convert a relative href to an absolute URL.
    Returns None for non-HTTP schemes (mailto:, javascript:, #, etc.).
    """
    href = href.strip()
    if not href or href.startswith("#"):
        return None
    if href.startswith("//"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}:{href}"
    if href.startswith("/"):
        parsed = urlparse(base_url)
        return f"{parsed.scheme}://{parsed.netloc}{href}"
    if href.startswith("http"):
        return href
    return None   # mailto:, javascript:, etc.
 
 
def extract_product_urls(xpath: str) -> set[str]:
    """
    Parse the rendered page with lxml and return a set of absolute product URLs.
 
    The XPath may return:
      • <a> element nodes  → href attribute is read with .get("href")
      • string / attribute values (e.g. xpath ending in /@href)
                           → used directly as the href string
    """
    tree    = html.fromstring(driver.page_source)
    base    = driver.current_url
    results = tree.xpath(xpath)
 
    if not results:
        print("    ⚠ XPath returned 0 results — check PRODUCT_LINK_XPATH")
        return set()
 
    urls = set()
    for item in results:
        # lxml returns a str-subclass (_ElementUnicodeResult) for attribute XPaths
        if isinstance(item, str):
            href = item
        else:
            # It's an element node — read its href attribute
            href = item.get("href", "")
 
        absolute = make_absolute(href, base)
        if absolute:
            urls.add(absolute)
 
    return urls
 
 
def save_urls(urls: set[str], filepath: str) -> None:
    """Write the deduplicated URL set to a CSV file (overwrites if exists)."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(urls):
            writer.writerow([url])
    print(f"\n✅  Saved {len(urls)} unique URL(s) → {filepath}")
 
 
def main() -> None:
    print(f"📂 Loading entry points from: {ENTRYPOINTS_FILE}")
    entrypoints = load_entrypoints(ENTRYPOINTS_FILE)
    print(f"   {len(entrypoints)} entry point(s) found.\n")
 
    all_urls: set[str] = set()          # global deduplication across all pages
 
    for idx, ep_url in enumerate(entrypoints, start=1):
        print(f"[{idx}/{len(entrypoints)}] Visiting: {ep_url}")
        driver.get(ep_url)
 
        # Let the initial JS render settle before scrolling
        time.sleep(random.uniform(2.0, 3.0))
 
        # Scroll until the entire infinite-scroll page is loaded
        scroll_to_bottom()
 
        # Extract and deduplicate product URLs
        found   = extract_product_urls(PRODUCT_LINK_XPATH)
        new     = found - all_urls
        all_urls |= found
 
        print(f"    ✔ {len(found)} URL(s) found — "
              f"{len(new)} new, {len(found) - len(new)} duplicate(s) skipped\n")
 
    save_urls(all_urls, OUTPUT_FILE)
    # Browser stays open (detach=True)
 
 
if __name__ == "__main__":
    main()