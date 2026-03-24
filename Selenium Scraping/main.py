"""
main.py — Step 2: Scrape product details
=========================================
WHAT IT DOES:
  1. Reads SELLER_NAME and TARGET_DOMAIN from .env
  2. Dynamically imports the matching parser from  parsers/{SELLER_NAME}.py
  3. Loads product URLs from  data/{SELLER_NAME}_urls.csv
     (produced by link_extraction.py)
  4. Skips URLs already present in the output CSV  → safe to re-run / resume
  5. Visits each URL with Selenium, calls parser.parse(), auto-derives slug fields
  6. Appends results to  data/{SELLER_NAME}_products.csv
  7. Logs failed URLs (with reason) to  failed_urls.txt

USAGE:
  1. Run link_extraction.py first to populate  data/{SELLER_NAME}_urls.csv
  2. Run:  python main.py

TO ADD A NEW SELLER:
  • Create  parsers/{SELLER_NAME}.py  (copy parsers/Herlan.py as a template)
  • Update SELLER_NAME in .env
  • Run link_extraction.py then main.py — nothing else needs changing

AUTO-DERIVED FIELDS (main.py fills these — parsers do not need to):
  product_slug        ← product_name
  brand_slug          ← brand_name
  category_slug       ← category_name
  seller_slug         ← seller_name
  parent_product_slug ← product_slug  (only when variation_type is set)
  is_active           ← in_stock
"""

import csv
import importlib
import os
import random
import sys
import time

from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from selenium import webdriver


# ── Load environment ───────────────────────────────────────────────────────────
load_dotenv()

SELLER_NAME   = os.getenv("SELLER_NAME",   "").strip()
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "").strip()

if not SELLER_NAME:
    sys.exit("❌  SELLER_NAME is not set in .env")
if not TARGET_DOMAIN:
    sys.exit("❌  TARGET_DOMAIN is not set in .env")

BASE_URL = f"https://{TARGET_DOMAIN}"


# ── File paths ─────────────────────────────────────────────────────────────────
DATA_DIR         = Path("data")
DATA_DIR.mkdir(exist_ok=True)

URLS_FILE        = DATA_DIR / f"{SELLER_NAME}_urls.csv"
OUTPUT_FILE      = DATA_DIR / f"{SELLER_NAME}_products.csv"
FAILED_URLS_FILE = Path("failed_urls.txt")


# ── BASE_PRODUCT template ──────────────────────────────────────────────────────
# This is the single source of truth for the output CSV schema.
# Every parser receives a fresh .copy() of this dict.
# Fields left as "" will be written as empty cells in the CSV.
#
# Fields marked "auto" are derived in auto_derive() — parsers may override them.
BASE_PRODUCT = {
    "category_slug":           "",   # auto ← category_name
    "product_name":            "",
    "product_slug":            "",   # auto ← product_name
    "seller_slug":             "",   # auto ← seller_name
    "current_price":           "",
    "seller_product_url":      "",
    "brand_slug":              "",   # auto ← brand_name
    "brand_name":              "",
    "product_description":     "",
    "model":                   "",
    "sku":                     "",
    "primary_image_url":       "",
    "image_urls":              "",
    "specifications":          "",
    "attributes":              "",
    "variation_type":          "",
    "parent_product_slug":     "",   # auto ← product_slug (when variation_type set)
    "original_price":          "",
    "currency":                "BDT",
    "in_stock":                "",
    "stock_quantity":          "",
    "seller_rating":           "",
    "review_count":            "",
    "shipping_cost":           "",
    "free_shipping":           "",
    "estimated_delivery_days": "",
    "seller_sku":              "",
    "seller_product_name":     "",
    "category_path":           "",
    "category_name":           "",
    "category_description":    "",
    "seller_name":             "",
    "base_url":                "",
    "seller_country_code":     "BD",
    "is_active":               "",   # auto ← in_stock
}

CSV_COLUMNS = list(BASE_PRODUCT.keys())


# ── Selenium setup ─────────────────────────────────────────────────────────────
# NOT headless — browser stays visible so you can watch it work.
options = webdriver.ChromeOptions()
options.add_experimental_option("detach", True)          # keeps browser open after script ends
options.add_experimental_option("excludeSwitches", ["enable-logging"])

driver = webdriver.Chrome(options=options)
driver.implicitly_wait(5)


# ── Helpers ────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a display name to a lowercase hyphenated slug."""
    return text.lower().strip().replace(" ", "-") if text else ""


def auto_derive(product: dict) -> dict:
    """
    Fill in slug / status fields that can be inferred from other fields.
    Called after the parser returns. Parsers can still override these manually.

    Derived field           Source field
    ─────────────────────────────────────────────────────
    product_slug          ← product_name       (if blank)
    brand_slug            ← brand_name         (if blank)
    category_slug         ← category_name      (if blank)
    seller_slug           ← seller_name        (if blank)
    parent_product_slug   ← product_slug       (only when variation_type is set)
    is_active             ← in_stock           (if blank)
    """
    if not product.get("product_slug") and product.get("product_name"):
        product["product_slug"] = slugify(product["product_name"])

    if not product.get("brand_slug") and product.get("brand_name"):
        product["brand_slug"] = slugify(product["brand_name"])

    if not product.get("category_slug") and product.get("category_name"):
        product["category_slug"] = slugify(product["category_name"])

    if not product.get("seller_slug") and product.get("seller_name"):
        product["seller_slug"] = slugify(product["seller_name"])

    if product.get("variation_type") and not product.get("parent_product_slug"):
        product["parent_product_slug"] = product.get("product_slug", "")

    if not product.get("is_active") and product.get("in_stock"):
        product["is_active"] = "1" if product["in_stock"].lower() == "yes" else "0"

    return product


def load_parser(seller_name: str):
    """
    Dynamically import parsers/{seller_name}.py and return the module.

    The module must expose:
        parse(driver, seller_name: str, base_url: str) -> dict | None
    """
    try:
        module = importlib.import_module(f"parsers.{seller_name}")
    except ModuleNotFoundError:
        sys.exit(
            f"❌  Parser not found: parsers/{seller_name}.py\n"
            f"    Create it by copying parsers/Herlan.py and updating the XPaths."
        )
    if not hasattr(module, "parse"):
        sys.exit(f"❌  parsers/{seller_name}.py has no parse() function.")
    return module


def load_urls(filepath: Path) -> list[str]:
    """Load product URLs from the CSV produced by link_extraction.py."""
    if not filepath.exists():
        sys.exit(
            f"❌  URLs file not found: {filepath}\n"
            f"    Run link_extraction.py first to generate it."
        )
    urls = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or next(iter(row.values()), "")).strip()
            if url:
                urls.append(url)
    return urls


def load_already_scraped(output_file: Path) -> set[str]:
    """
    Return the set of seller_product_url values already written to the output
    CSV so the scraper can skip them when resuming an interrupted run.
    """
    scraped = set()
    if not output_file.exists():
        return scraped
    try:
        with open(output_file, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                url = row.get("seller_product_url", "").strip()
                if url:
                    scraped.add(url)
        print(f"   ↳ Resume mode: {len(scraped)} URL(s) already scraped, will skip.")
    except Exception as e:
        print(f"   ⚠  Could not read existing output CSV: {e}")
    return scraped


def open_output_csv(output_file: Path):
    """
    Open the output CSV for appending (or create it with a header if new).
    Returns (file_handle, DictWriter).
    """
    is_new = not output_file.exists() or output_file.stat().st_size == 0
    f      = open(output_file, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS, extrasaction="ignore")
    if is_new:
        writer.writeheader()
    return f, writer


def log_failure(url: str, reason: str) -> None:
    """Append a failed URL with timestamp and reason to failed_urls.txt."""
    try:
        with open(FAILED_URLS_FILE, "a", encoding="utf-8") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}]  {url}  |  {reason}\n")
    except Exception:
        pass   # never let logging crash the main loop


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{'='*60}")
    print(f"  Seller  : {SELLER_NAME}")
    print(f"  Domain  : {TARGET_DOMAIN}")
    print(f"  URLs    : {URLS_FILE}")
    print(f"  Output  : {OUTPUT_FILE}")
    print(f"{'='*60}\n")

    # 1. Load the seller-specific parser
    parser_module = load_parser(SELLER_NAME)
    print(f"✅  Parser loaded: parsers/{SELLER_NAME}.py\n")

    # 2. Load all product URLs
    all_urls = load_urls(URLS_FILE)
    print(f"📋  {len(all_urls)} product URL(s) in {URLS_FILE}")

    # 3. Filter out already-scraped URLs (resume support)
    already_scraped = load_already_scraped(OUTPUT_FILE)
    pending         = [u for u in all_urls if u not in already_scraped]
    print(f"   ↳ {len(pending)} URL(s) pending.\n")

    if not pending:
        print("✅  Nothing to do — all URLs already scraped.")
        return

    # 4. Open output CSV (append mode)
    csv_file, writer = open_output_csv(OUTPUT_FILE)

    scraped_count = 0
    failed_count  = 0

    try:
        for idx, url in enumerate(pending, start=1):
            print(f"[{idx}/{len(pending)}] {url}")

            try:
                driver.get(url)
                # Let JS render before the parser inspects the DOM
                # time.sleep(random.uniform(1.5, 2.5))

                # ── Call the seller-specific parser ───────────────────────────
                # parse() receives the live driver, seller name, and base URL.
                # It returns a filled BASE_PRODUCT dict, or None to skip.
                product = parser_module.parse(driver, SELLER_NAME, BASE_URL)

                if product is None:
                    print(f"   ↳ Skipped (parser returned None — not a product page)")
                    log_failure(url, "Parser returned None")
                    failed_count += 1
                    continue

                # ── Auto-derive slug / status fields ──────────────────────────
                product = auto_derive(product)

                # ── Write one row and flush immediately ───────────────────────
                # flush() ensures the row is on disk even if the script crashes
                writer.writerow(product)
                csv_file.flush()

                scraped_count += 1
                print(f"   ✔  {product.get('product_name', '—')}")

            except Exception as e:
                failed_count += 1
                reason = f"{type(e).__name__}: {e}"
                print(f"   ❌  Failed — {reason}")
                log_failure(url, reason)

            # Polite delay between requests
            

    finally:
        csv_file.close()

    # ── Summary ────────────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"  ✅  Scraped : {scraped_count}")
    print(f"  ❌  Failed  : {failed_count}  (see failed_urls.txt)")
    print(f"  📄  Output  : {OUTPUT_FILE}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
