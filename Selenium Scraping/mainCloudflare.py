
"""
main.py — Step 2: Scrape product details (Cloudflare-resilient)
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
import undetected_chromedriver as uc


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
BASE_PRODUCT = {
    "category_slug":           "",
    "product_name":            "",
    "product_slug":            "",
    "seller_slug":             "",
    "current_price":           "",
    "seller_product_url":      "",
    "brand_slug":              "",
    "brand_name":              "",
    "product_description":     "",
    "model":                   "",
    "sku":                     "",
    "primary_image_url":       "",
    "image_urls":              "",
    "specifications":          "",
    "attributes":              "",
    "variation_type":          "",
    "parent_product_slug":     "",
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
    "is_active":               "",
}

CSV_COLUMNS = list(BASE_PRODUCT.keys())


# ── Driver Setup (Cloudflare bypass) ───────────────────────────────────────────
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


def is_driver_alive(driver):
    try:
        driver.current_url
        return True
    except:
        return False


def wait_for_cloudflare(driver):
    for _ in range(20):
        if "cf-challenge" not in driver.page_source.lower():
            return
        print("⏳ Waiting for Cloudflare challenge...")
        time.sleep(3)


def human_delay(a=2.0, b=4.0):
    time.sleep(random.uniform(a, b))


# ── Helpers ────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    return text.lower().strip().replace(" ", "-") if text else ""


def auto_derive(product: dict) -> dict:
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
    try:
        module = importlib.import_module(f"parsers.{seller_name}")
    except ModuleNotFoundError:
        sys.exit(f"❌ Parser not found: parsers/{seller_name}.py")

    if not hasattr(module, "parse"):
        sys.exit(f"❌ parsers/{seller_name}.py has no parse() function.")

    return module


def load_urls(filepath: Path) -> list[str]:
    if not filepath.exists():
        sys.exit(f"❌ URLs file not found: {filepath}")

    urls = []
    with open(filepath, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = (row.get("url") or "").strip()
            if url:
                urls.append(url)
    return urls


def load_already_scraped(output_file: Path) -> set[str]:
    scraped = set()
    if not output_file.exists():
        return scraped

    with open(output_file, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            url = row.get("seller_product_url", "").strip()
            if url:
                scraped.add(url)

    print(f"   ↳ Resume mode: {len(scraped)} already scraped")
    return scraped


def open_output_csv(output_file: Path):
    is_new = not output_file.exists() or output_file.stat().st_size == 0
    f      = open(output_file, "a", newline="", encoding="utf-8")
    writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)

    if is_new:
        writer.writeheader()

    return f, writer


def log_failure(url: str, reason: str):
    with open(FAILED_URLS_FILE, "a", encoding="utf-8") as f:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"[{ts}] {url} | {reason}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print(f"\n{'='*60}")
    print(f"Seller : {SELLER_NAME}")
    print(f"Domain : {TARGET_DOMAIN}")
    print(f"{'='*60}\n")

    parser_module = load_parser(SELLER_NAME)

    all_urls = load_urls(URLS_FILE)
    already_scraped = load_already_scraped(OUTPUT_FILE)
    pending = [u for u in all_urls if u not in already_scraped]

    print(f"📋 {len(pending)} URLs to scrape\n")

    if not pending:
        print("✅ Nothing to scrape")
        return

    csv_file, writer = open_output_csv(OUTPUT_FILE)

    driver = create_driver()

    try:
        for idx, url in enumerate(pending, start=1):
            print(f"[{idx}/{len(pending)}] {url}")

            if not is_driver_alive(driver):
                driver.quit()
                driver = create_driver()

            try:
                driver.get(url)
            except:
                driver = create_driver()
                driver.get(url)

            wait_for_cloudflare(driver)
            human_delay()

            try:
                product = parser_module.parse(driver, SELLER_NAME, BASE_URL)

                if product is None:
                    log_failure(url, "Parser returned None")
                    continue

                product = auto_derive(product)

                writer.writerow(product)
                csv_file.flush()

                print(f"   ✔ {product.get('product_name','—')}")

            except Exception as e:
                log_failure(url, str(e))
                print(f"   ❌ Failed: {e}")

            human_delay(2, 5)

    finally:
        driver.quit()
        csv_file.close()

    print("\n✅ Done!")


if __name__ == "__main__":
    main()

