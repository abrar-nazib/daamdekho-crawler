import os
import csv
import asyncio
import logging
import sys
from scrapling.spiders import Spider, Response
import environs

from parsers import load_parser
from database import ProductDB  # Import our new DB class

# Setup environment variables
env = environs.Env()
env.read_env()

# --- 1. Read Configurations ---
TARGET_DOMAIN = env("TARGET_DOMAIN", default="example.com")
SELLER_NAME = env("SELLER_NAME", default="Unknown")
CONCURRENCY = env.int("CONCURRENCY", default=1)
DELAY = env.float("DELAY", default=2.0)
MAX_ITEMS = env.int("MAX_ITEMS", default=100)
MAX_CONSECUTIVE_DUPLICATES = env.int("MAX_DUPLICATES", default=50)
RECURSE = env.bool("RECURSE", default=True)

# --- 2. Setup Logging ---
os.makedirs("/app/data/csvs", exist_ok=True)
os.makedirs("/app/data/databases", exist_ok=True) # New folder for DBs
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

# --- 3. Load Parser ---
PARSER_FUNC = load_parser(TARGET_DOMAIN)
if not PARSER_FUNC:
    logger.critical(f"🔥 FATAL: No parser found for {TARGET_DOMAIN}. Exiting.")
    sys.exit(1)

# --- 4. Define Spider ---
class UniversalSpider(Spider):
    name = f"spider_{SELLER_NAME.lower()}"
    allowed_domains = {TARGET_DOMAIN}
    
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
        for item_or_request in PARSER_FUNC(response, SELLER_NAME, TARGET_DOMAIN, recurse=RECURSE):
            yield item_or_request

def normalize_val(val):
    """Helper to ensure clean string comparison"""
    return str(val).strip() if val is not None else ""

async def run():
    checkpoint_dir = f"/app/data/checkpoints/{SELLER_NAME}_state"
    
    # Initialize SQLite Database
    db_path = f"/app/data/databases/{SELLER_NAME}.db"
    db = ProductDB(db_path)
    logger.info(f"Connected to database: {db_path}")

    spider = UniversalSpider(crawldir=checkpoint_dir)
    logger.info(f"Starting scraper. Stop limit: {MAX_CONSECUTIVE_DUPLICATES} identical items.")

    items_scraped = 0
    consecutive_duplicates = 0

    try:
        async for item in spider.stream():
            item_url = item.get("seller_product_url")
            
            # --- DATABASE CHECK ---
            existing_item = db.get_product(item_url)
            
            should_save = False
            is_update = False

            if not existing_item:
                # Case 1: New Product
                should_save = True
                consecutive_duplicates = 0 # Reset counter
            else:
                # Case 2: Product Exists, check for changes
                data_changed = False
                # Compare fields (excluding last_updated)
                for key, new_val in item.items():
                    old_val = existing_item.get(key)
                    if normalize_val(new_val) != normalize_val(old_val):
                        data_changed = True
                        break
                
                if data_changed:
                    should_save = True
                    is_update = True
                    consecutive_duplicates = 0 # Reset counter because we found useful update
                    logger.info(f"♻️ Update detected for: {item.get('product_name', 'Unknown')}")
                else:
                    # Case 3: Exact Duplicate
                    consecutive_duplicates += 1
                    if consecutive_duplicates >= MAX_CONSECUTIVE_DUPLICATES:
                        logger.warning(f"⛔ Limit Reached ({consecutive_duplicates} identical items). Stopping.")
                        return

            # --- SAVE TO DB ---
            if should_save:
                db.upsert_product(item)
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
    finally:
        db.close()

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