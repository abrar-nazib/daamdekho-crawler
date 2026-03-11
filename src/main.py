import os
import csv
import asyncio
import logging
import sys
from scrapling.spiders import Spider, Response
import environs

# IMPORT THE NEW DYNAMIC LOADER
from parsers import load_parser

# Setup environment variables
env = environs.Env()
env.read_env()

# --- 1. Read Configurations ---
TARGET_DOMAIN = env("TARGET_DOMAIN", default="example.com")
SELLER_NAME = env("SELLER_NAME", default="Unknown")
CONCURRENCY = env.int("CONCURRENCY", default=1)
DELAY = env.float("DELAY", default=2.0)
MAX_ITEMS = env.int("MAX_ITEMS", default=1000000)
MAX_CONSECUTIVE_DUPLICATES = env.int("MAX_DUPLICATES", default=50)
RECURSE = env.bool("RECURSE", default=True)

# --- 2. Setup Logging ---
os.makedirs("/app/data/csvs", exist_ok=True)
os.makedirs("/app/data/checkpoints", exist_ok=True)
os.makedirs("/app/data/logs", exist_ok=True)

log_file_path = f"/app/data/logs/{SELLER_NAME.lower()}.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(log_file_path, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(SELLER_NAME)
logging.getLogger("scrapling").setLevel(logging.INFO)

# --- 3. Load the Correct Parser Dynamically ---
# This looks for src/parsers/{TARGET_DOMAIN}.py (e.g., startech.py)
PARSER_FUNC = load_parser(TARGET_DOMAIN)

if not PARSER_FUNC:
    logger.critical(f"🔥 FATAL: No parser found for {TARGET_DOMAIN}. Exiting.")
    sys.exit(1)


# --- 4. Define Spider ---
class UniversalSpider(Spider):
    name = f"spider_{SELLER_NAME.lower()}"
    allowed_domains = {TARGET_DOMAIN}
    
    # Load custom entrypoints
    entrypoints_file = f"/app/data/csvs/{SELLER_NAME}_entrypoints.csv"
    if os.path.exists(entrypoints_file):
        with open(entrypoints_file, mode="r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            start_urls = [row["url"] for row in reader if row.get("url")]
            if not start_urls:
                start_urls = [env("START_URL")]
    else:
        start_urls = [env("START_URL")]

    concurrent_requests = CONCURRENCY
    download_delay = DELAY

    async def parse(self, response: Response):
        # Use the dynamically loaded function
        for item_or_request in PARSER_FUNC(response, SELLER_NAME, TARGET_DOMAIN, recurse=RECURSE):
            yield item_or_request


def normalize_val(val):
    return str(val).strip() if val is not None else ""

async def run():
    csv_path = f"/app/data/csvs/{SELLER_NAME}_products.csv"
    checkpoint_dir = f"/app/data/checkpoints/{SELLER_NAME}_state"

    seen_products = {} 
    file_exists = os.path.isfile(csv_path)

    # Load Memory State
    if file_exists:
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    url = row.get("seller_product_url")
                    if url:
                        seen_products[url] = row
            logger.info(f"Loaded {len(seen_products)} unique products from existing CSV.")
        except Exception as e:
            logger.warning(f"Could not read existing CSV: {e}")

    # Open CSV
    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        # We need a reference to the keys. Since keys might differ per parser, 
        # normally we'd import a base_product from the specific parser, 
        # but for now we assume they share the standard schema.
        from parsers.startech import BASE_PRODUCT # You might want to make this dynamic too later
        fieldnames = list(BASE_PRODUCT.keys())
        
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        spider = UniversalSpider(crawldir=checkpoint_dir)
        logger.info(f"Starting scraper for {SELLER_NAME}...")

        items_scraped = 0
        consecutive_duplicates = 0

        try:
            async for item in spider.stream():
                item_url = item.get("seller_product_url")
                should_write = False
                is_update = False

                if item_url not in seen_products:
                    should_write = True
                    consecutive_duplicates = 0
                else:
                    existing_item = seen_products[item_url]
                    data_changed = False
                    for key in fieldnames:
                        new_val = normalize_val(item.get(key))
                        old_val = normalize_val(existing_item.get(key))
                        if new_val != old_val:
                            data_changed = True
                            break
                    
                    if data_changed:
                        should_write = True
                        is_update = True
                        consecutive_duplicates = 0
                        logger.info(f"♻️ Update: {item.get('product_name', 'Unknown')}")
                    else:
                        consecutive_duplicates += 1
                        if consecutive_duplicates >= MAX_CONSECUTIVE_DUPLICATES:
                            logger.warning(f"⛔ Limit Reached ({consecutive_duplicates} duplicates). Stopping.")
                            return

                if should_write:
                    seen_products[item_url] = item
                    writer.writerow(item)
                    f.flush()
                    items_scraped += 1

                    if not is_update:
                        logger.info(f"[{items_scraped} New] Saved: {item.get('product_name', 'Unknown')}")

                    if MAX_ITEMS > 0 and items_scraped >= MAX_ITEMS:
                        logger.info(f"Max item limit reached ({MAX_ITEMS}). Stopping.")
                        return

        except (RuntimeError, ValueError, asyncio.CancelledError):
            pass
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)

if __name__ == "__main__":
    try:
        asyncio.run(run())
        logger.info("Scraper finished successfully.")
        sys.exit(0)
    except KeyboardInterrupt:
        logger.info("Paused via KeyboardInterrupt.")
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error!", exc_info=True)
        sys.exit(1)