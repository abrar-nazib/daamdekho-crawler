"""
link_extraction.py — Step 1: Collect product URLs
===================================================
WHAT IT DOES:
  1. Reads SELLER_NAME and TARGET_DOMAIN from .env
  2. Loads entry-point category/listing URLs from  data/{SELLER_NAME}_entrypoints.csv
  3. Visits each entry point with Selenium (visible browser — not headless)
  4. Scrolls to the bottom repeatedly until the full infinite-scroll page is loaded
  5. Extracts all product URLs using an XPath expression you define below
  6. Deduplicates across all entry points (global set — no URL appears twice)
  7. Saves results to  data/{SELLER_NAME}_urls.csv

USAGE:
  1. Fill in .env:
         SELLER_NAME  = Herlan
         TARGET_DOMAIN = herlan.com
  2. Add entry-point URLs to  data/{SELLER_NAME}_entrypoints.csv  (one URL per row)
  3. Set PRODUCT_LINK_XPATH below to match the site's product anchor elements
  4. Run:  python link_extraction.py
  5. Then run main.py to scrape product details from the collected URLs

ENTRYPOINTS CSV FORMAT:
  - Single column, header row is optional
  - Accepted header names (skipped automatically): url, link, entrypoint
  - One absolute URL per row, e.g.:
        https://www.herlan.com/product-category/makeup/
        https://www.herlan.com/product-category/skincare/
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
from selenium import webdriver


# ── Load environment ───────────────────────────────────────────────────────────
load_dotenv()

SELLER_NAME   = os.getenv("SELLER_NAME",   "").strip()
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "").strip()

if not SELLER_NAME:
    sys.exit("❌  SELLER_NAME is not set in .env")
if not TARGET_DOMAIN:
    sys.exit("❌  TARGET_DOMAIN is not set in .env")


# ── USER CONFIGURATION ─────────────────────────────────────────────────────────
# XPath that matches every product <a> element on a listing/category page.
#
# Tips:
#   Return element nodes → "//a[contains(@class,'product-card')]"
#   Return href strings  → "//a[contains(@class,'product-card')]/@href"
#   Match by href        → "//a[contains(@href,'/product/')]"
#   Nested anchor        → "//div[contains(@class,'product-item')]//a"
#
# The scraper handles BOTH element nodes and string results automatically.
PRODUCT_LINK_XPATH = '//div[@class="woocommerce-loop-product__title"]/a/@href'

# Seconds to wait after each scroll before re-checking page height.
# Increase for slow-loading sites.
SCROLL_PAUSE = 3.0

# Consecutive scrolls with NO height change before the page is declared fully loaded.
# Raise for sites that load content in delayed batches.
MAX_STALE_SCROLLS = 5
# ──────────────────────────────────────────────────────────────────────────────


# ── File paths ─────────────────────────────────────────────────────────────────
DATA_DIR         = Path("data")
DATA_DIR.mkdir(exist_ok=True)

ENTRYPOINTS_FILE = DATA_DIR / f"{SELLER_NAME}_entrypoints.csv"
OUTPUT_FILE      = DATA_DIR / f"{SELLER_NAME}_urls.csv"


# ── Selenium setup ─────────────────────────────────────────────────────────────
# NOT headless — browser stays visible so you can watch it work.
options = webdriver.ChromeOptions()
options.add_experimental_option("detach", True)          # keeps browser open after script ends
options.add_experimental_option("excludeSwitches", ["enable-logging"])

driver = webdriver.Chrome(options=options)
driver.implicitly_wait(5)


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_entrypoints(filepath: Path) -> list[str]:
    """
    Read entry-point URLs from a single-column CSV.
    Header rows with common names (url, link, entrypoint) are skipped automatically.
    """
    if not filepath.exists():
        sys.exit(f"❌  Entrypoints file not found: {filepath}")

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


def scroll_to_bottom(pause: float = SCROLL_PAUSE,
                     max_stale: int = MAX_STALE_SCROLLS) -> None:
    """
    Scroll to the bottom of the page repeatedly until the document height
    stops growing for `max_stale` consecutive attempts.
    Handles infinite-scroll pages by waiting for lazy-loaded content.
    """
    last_height = driver.execute_script("return document.body.scrollHeight")
    stale_count = 0
    scroll_num  = 0

    while stale_count < max_stale:
        scroll_num += 1
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(pause + random.uniform(0.2, 0.8))   # jitter avoids robotic timing

        new_height = driver.execute_script("return document.body.scrollHeight")

        if new_height == last_height:
            stale_count += 1
            print(f"    scroll #{scroll_num} — no new content "
                  f"({stale_count}/{max_stale} stale)")
        else:
            stale_count = 0
            print(f"    scroll #{scroll_num} — height {last_height} → {new_height}px")
            last_height = new_height

    print(f"    ↳ Page fully loaded (final height={last_height}px)\n")


def make_absolute(href: str, base_url: str) -> str | None:
    """
    Normalise a raw href to a full absolute URL.
    Returns None for non-HTTP schemes (javascript:, mailto:, #, etc.).
    """
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
    """
    Parse the fully-rendered page with lxml and return a set of absolute URLs.

    The XPath may return:
      • Element nodes  (e.g. //a[...])       → href read via .get("href")
      • String results (e.g. //a[...]/@href) → used directly
    Both forms are handled transparently.
    """
    tree    = html.fromstring(driver.page_source)
    base    = driver.current_url
    results = tree.xpath(xpath)

    if not results:
        print("    ⚠  XPath returned 0 results — check PRODUCT_LINK_XPATH")
        return set()

    urls = set()
    for item in results:
        # lxml returns _ElementUnicodeResult (str subclass) for /@attr XPaths
        href     = item if isinstance(item, str) else item.get("href", "")
        absolute = make_absolute(href, base)
        if absolute:
            urls.add(absolute)

    return urls


def save_urls(urls: set[str], filepath: Path) -> None:
    """Write deduplicated URLs to a CSV file, overwriting any previous run."""
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["url"])
        for url in sorted(urls):
            writer.writerow([url])
    print(f"\n✅  Saved {len(urls)} unique URL(s) → {filepath}")


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Seller      : {SELLER_NAME}")
    print(f"  Domain      : {TARGET_DOMAIN}")
    print(f"  Entrypoints : {ENTRYPOINTS_FILE}")
    print(f"  Output      : {OUTPUT_FILE}")
    print(f"{'='*60}\n")

    entrypoints = load_entrypoints(ENTRYPOINTS_FILE)
    print(f"📋  {len(entrypoints)} entry point(s) found.\n")

    all_urls: set[str] = set()   # global deduplication across all entry points

    for idx, ep_url in enumerate(entrypoints, start=1):
        print(f"[{idx}/{len(entrypoints)}] Visiting: {ep_url}")
        driver.get(ep_url)

        # Wait for the initial JS render before scrolling
        time.sleep(random.uniform(2.0, 3.0))

        # Scroll until the full infinite-scroll page is loaded
        scroll_to_bottom()

        # Extract product URLs from the fully-rendered DOM
        found   = extract_product_urls(PRODUCT_LINK_XPATH)
        new     = found - all_urls
        all_urls |= found

        print(f"    ✔  {len(found)} URL(s) found — "
              f"{len(new)} new, {len(found) - len(new)} duplicate(s) skipped\n")

    save_urls(all_urls, OUTPUT_FILE)
    print(f"\n👉  Next step: run  python main.py  to scrape product details.\n")
    # Browser stays open (detach=True)


if __name__ == "__main__":
    main()
