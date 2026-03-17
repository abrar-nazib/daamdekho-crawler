"""
main.py — Product scraper (Selenium + dynamic parser per seller)
================================================================
How it works:
  1. Reads SELLER_NAME and TARGET_DOMAIN from the .env file in the root folder.
  2. Loads product URLs from  data/{SELLER_NAME}_urls.csv
  3. Dynamically imports the matching parser from  parsers/{SELLER_NAME}.py
     → The parser exposes a single function:  parse(driver, seller_name, base_url)
     → It returns a filled BASE_PRODUCT dict (or None to skip the URL).
  4. Skips URLs that are already present in the output CSV (resume support).
  5. Failed URLs are appended to  failed_urls.txt  with a reason.
  6. Results are appended to  data/{SELLER_NAME}_products.csv

To add a new seller:
  • Add its credentials to .env  (SELLER_NAME, TARGET_DOMAIN)
  • Create  parsers/{SELLER_NAME}.py  following the template in parsers/Herlan.py
  • Run this file — no other edits needed.
"""

import csv
import importlib
import os
import sys
import time
import random

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By

# ── Load environment ──────────────────────────────────────────────────────────
load_dotenv()                                       # reads .env in the root folder

SELLER_NAME   = os.getenv("SELLER_NAME", "").strip()
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "").strip()

if not SELLER_NAME:
    sys.exit("❌  SELLER_NAME is not set in .env — please add it and retry.")
if not TARGET_DOMAIN:
    sys.exit("❌  TARGET_DOMAIN is not set in .env — please add it and retry.")

BASE_URL = f"https://{TARGET_DOMAIN}"

# ── File paths ────────────────────────────────────────────────────────────────
DATA_DIR          = Path("data")
DATA_DIR.mkdir(exist_ok=True)

URLS_FILE         = DATA_DIR / f"{SELLER_NAME}_urls.csv"
OUTPUT_FILE       = DATA_DIR / f"{SELLER_NAME}_products.csv"
FAILED_URLS_FILE  = Path("failed_urls.txt")

# ── BASE_PRODUCT template ─────────────────────────────────────────────────────
# Every parser receives a fresh copy of this dict via BASE_PRODUCT.copy().
# Fields left as "" will be written as empty cells in the CSV.
# Fields marked "auto" below are derived automatically in main.py after
# the parser returns — the parser does NOT need to fill them.
#
#   Auto-derived field          ← source field
#   ─────────────────────────────────────────────
#   product_slug                ← product_name
#   brand_slug                  ← brand_name
#   category_slug               ← category_name
#   seller_slug                 ← seller_name
#   parent_product_slug         ← product_slug  (only when variation_type is set)
#
BASE_PRODUCT = {
    "category_slug":          "",
    "product_name":           "",
    "product_slug":           "",   # auto
    "seller_slug":            "",   # auto
    "current_price":          "",
    "seller_product_url":     "",
    "brand_slug":             "",   # auto
    "brand_name":             "",
    "product_description":    "",
    "model":                  "",
    "sku":                    "",
    "primary_image_url":      "",
    "image_urls":             "",
    "specifications":         "",
    "attributes":             "",
    "variation_type":         "",
    "parent_product_slug":    "",   # auto (only when variation_type is filled)
    "original_price":         "",
    "currency":               "BDT",
    "in_stock":               "",
    "stock_quantity":         "",
    "seller_rating":          "",
    "review_count":           "",
    "shipping_cost":          "",
    "free_shipping":          "",
    "estimated_delivery_days":"",
    "seller_sku":             "",
    "seller_product_name":    "",
    "category_path":          "",
    "category_name":          "",
    "category_description":   "",
    "seller_name":            "",
    "base_url":               "",
    "seller_country_code":    "BD",
    "is_active":              "",
}

CSV_COLUMNS = list(BASE_PRODUCT.keys())


# ── Helpers ───────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a display name to a lowercase hyphenated slug."""
    return text.lower().strip().replace(" ", "-") if text else ""


def auto_derive(product: dict) -> dict:
    """
    Fill in slug/derived fields that can be inferred from other fields.
    Called in main.py after the parser returns — parsers can still override
    these manually if they prefer a custom value.
    """
    # product_slug ← product_name  (only if blank)
    if not product.get("product_slug") and product.get("product_name"):
        product["product_slug"] = slugify(product["product_name"])

    # brand_slug ← brand_name
    if not product.get("brand_slug") and product.get("brand_name"):
        product["brand_slug"] = slugify(product["brand_name"])

    # category_slug ← category_name
    if not product.get("category_slug") and product.get("category_name"):
        product["category_slug"] = slugify(product["category_name"])

    # seller_slug ← seller_name
    if not product.get("seller_slug") and product.get("seller_name"):
        product["seller_slug"] = slugify(product["seller_name"])

    # parent_product_slug ← product_slug  (only when variation_type is set)
    if product.get("variation_type") and not product.get("parent_product_slug"):
        product["parent_product_slug"] = product.get("product_slug", "")

    # is_active ← in_stock  (only if blank)
    if not product.get("is_active") and product.get("in_stock"):
        product["is_active"] = "1" if product["in_stock"].lower() == "yes" else "0"

    return product


def load_already_scraped(output_file: Path) -> set[str]:
    """
    Read the output CSV (if it exists) and return a set of already-scraped
    seller_product_url values so the scraper can skip them on resume.
    """
    scraped = set()
    if not output_file.exists():
        return scraped
    try:
        with open(output_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                url = row.get("seller_product_url", "").strip()
                if url:
                    scraped.add(url)
        print(f"   ↳ Resume mode: {len(scraped)} URL(s) already in output, will skip.")
    except Exception as e:
        print(f"   ⚠ Could not read existing output CSV: {e}")
    return scraped


def load_urls(urls_file: Path) -> list[str]:
    """Load product URLs from the urls CSV produced by the URL scraper."""
    urls = []
    try:
        with open(urls_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Support both 'url' header (our standard) and bare single-column files
                url = (row.get("url") or next(iter(row.values()), "")).strip()
                if url:
                    urls.append(url)
    except FileNotFoundError:
        sys.exit(f"❌  URLs file not found: {urls_file}")
    return urls


def log_failure(url: str, reason: str) -> None:
    """Append a failed URL with timestamp and reason to failed_urls.txt."""
    try:
        with open(FAILED_URLS_FILE, "a", encoding="utf-8") as f:
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{timestamp}] {url}  |  {reason}\n")
    except Exception as e:
        print(f"   ⚠ Could not write to failed_urls.txt: {e}")


def get_csv_writer(output_file: Path, mode: str):
    """
    Open the output CSV and return (file_handle, DictWriter).
    mode = "w"  → write from scratch (first run)
    mode = "a"  → append (resume)
    """
    file_exists = output_file.exists() and output_file.stat().st_size > 0
    f = open(output_file, mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    # Write header only when creating a new file
    if mode == "w" or not file_exists:
        writer.writeheader()
    return f, writer


def load_parser(seller_name: str):
    """
    Dynamically import parsers/{seller_name}.py and return the module.
    The module must expose:   parse(driver, seller_name, base_url) -> dict | None
    """
    module_path = f"parsers.{seller_name}"
    try:
        module = importlib.import_module(module_path)
        if not hasattr(module, "parse"):
            sys.exit(f"❌  parsers/{seller_name}.py exists but has no parse() function.")
        return module
    except ModuleNotFoundError:
        sys.exit(
            f"❌  Could not find parser: parsers/{seller_name}.py\n"
            f"    Create the file following the template in parsers/Herlan.py"
        )


# ── Selenium setup ────────────────────────────────────────────────────────────

# !! Selenium is NOT headless so you can watch it work !!
options = webdriver.ChromeOptions()
options.add_experimental_option("detach", True)        # keeps browser open after script ends
options.add_experimental_option("excludeSwitches", ["enable-logging"])

driver = webdriver.Chrome(options=options)
driver.implicitly_wait(5)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Seller   : {SELLER_NAME}")
    print(f"  Domain   : {TARGET_DOMAIN}")
    print(f"  URLs     : {URLS_FILE}")
    print(f"  Output   : {OUTPUT_FILE}")
    print(f"{'='*60}\n")

    # 1. Load parser module dynamically
    parser_module = load_parser(SELLER_NAME)
    print(f"✅  Parser loaded: parsers/{SELLER_NAME}.py\n")

    # 2. Load URLs to scrape
    all_urls = load_urls(URLS_FILE)
    print(f"📋  {len(all_urls)} product URL(s) found in {URLS_FILE}")

    # 3. Load already-scraped URLs for resume support
    already_scraped = load_already_scraped(OUTPUT_FILE)

    # 4. Filter out already-scraped URLs
    pending_urls = [u for u in all_urls if u not in already_scraped]
    print(f"   ↳ {len(pending_urls)} URL(s) pending scrape.\n")

    if not pending_urls:
        print("✅  Nothing to do — all URLs already scraped.")
        return

    # 5. Open output CSV in append mode (creates with header if new)
    csv_mode = "a" if OUTPUT_FILE.exists() and OUTPUT_FILE.stat().st_size > 0 else "w"
    csv_file, writer = get_csv_writer(OUTPUT_FILE, csv_mode)

    scraped_count = 0
    failed_count  = 0

    try:
        for idx, url in enumerate(pending_urls, start=1):
            print(f"[{idx}/{len(pending_urls)}] {url}")

            try:
                driver.get(url)
                # Brief pause to let JS render before the parser inspects the DOM
                time.sleep(random.uniform(1.5, 2.5))

                # ── Call the seller-specific parser ───────────────────────────
                product = parser_module.parse(driver, SELLER_NAME, BASE_URL)

                if product is None:
                    # Parser explicitly returned None → skip silently (e.g. non-product page)
                    print(f"   ↳ Skipped (parser returned None)")
                    log_failure(url, "Parser returned None")
                    failed_count += 1
                    continue

                # ── Auto-derive slug / status fields ──────────────────────────
                product = auto_derive(product)

                # ── Write one row to CSV ──────────────────────────────────────
                writer.writerow(product)
                csv_file.flush()        # write to disk immediately (safe on crash)

                scraped_count += 1
                print(f"   ✔ Scraped: {product.get('product_name', '—')}")

            except Exception as e:
                failed_count += 1
                reason = f"{type(e).__name__}: {e}"
                print(f"   ❌ Failed — {reason}")
                log_failure(url, reason)

            # Polite delay between requests
            time.sleep(random.uniform(1.0, 2.0))

    finally:
        csv_file.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ✅  Scraped : {scraped_count}")
    print(f"  ❌  Failed  : {failed_count}  (see failed_urls.txt)")
    print(f"  📄  Output  : {OUTPUT_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
