import os
import csv
import asyncio
import logging
import sys  # Import sys for clean exits
from scrapling.spiders import Spider, Response
from parsers import PARSERS, BASE_PRODUCT

# --- 1. Read Configurations ---
TARGET_DOMAIN = os.getenv("TARGET_DOMAIN", "example.com")
START_URLS = os.getenv("START_URL", "https://example.com/")
SELLER_NAME = os.getenv("SELLER_NAME", "Unknown")
CONCURRENCY = int(os.getenv("CONCURRENCY", "1"))
DELAY = float(os.getenv("DELAY", "2.0"))
MAX_ITEMS = int(os.getenv("MAX_ITEMS", "100"))
MAX_CONSECUTIVE_DUPLICATES = int(os.getenv("MAX_DUPLICATES", "50"))

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


# --- 3. Define Spider ---
class UniversalSpider(Spider):
    name = f"spider_{SELLER_NAME.lower()}"
    allowed_domains = {TARGET_DOMAIN}
    start_urls = [
        "https://www.startech.com.bd/gaming",
        "https://www.startech.com.bd/television-shop",
        "https://www.startech.com.bd/appliance",
    ]
    concurrent_requests = CONCURRENCY
    download_delay = DELAY

    async def parse(self, response: Response):
        parser_func = PARSERS.get(TARGET_DOMAIN)
        if parser_func:
            for item_or_request in parser_func(response, SELLER_NAME, START_URLS):
                yield item_or_request


async def run():
    csv_path = f"/app/data/csvs/{SELLER_NAME}_products.csv"
    checkpoint_dir = f"/app/data/checkpoints/{SELLER_NAME}_state"

    seen_urls = set()
    file_exists = os.path.isfile(csv_path)

    # Load existing URLs to memory
    if file_exists:
        try:
            with open(csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if row.get("seller_product_url"):
                        seen_urls.add(row["seller_product_url"])
            logger.info(f"Loaded {len(seen_urls)} existing items from CSV.")
        except Exception as e:
            logger.warning(f"Could not read existing CSV (might be empty): {e}")

    # Open CSV in Append Mode
    with open(csv_path, mode="a", newline="", encoding="utf-8") as f:
        fieldnames = list(BASE_PRODUCT.keys())
        writer = csv.DictWriter(f, fieldnames=fieldnames)

        if not file_exists:
            writer.writeheader()

        spider = UniversalSpider(crawldir=checkpoint_dir)
        logger.info(
            f"Starting scraper. Stopping after {MAX_CONSECUTIVE_DUPLICATES} duplicates."
        )

        items_scraped = 0
        consecutive_duplicates = 0

        try:
            async for item in spider.stream():
                item_url = item.get("seller_product_url")

                # --- DUPLICATE CHECK ---
                if item_url in seen_urls:
                    consecutive_duplicates += 1
                    if consecutive_duplicates >= MAX_CONSECUTIVE_DUPLICATES:
                        logger.warning(
                            f"⛔ Limit Reached: Found {consecutive_duplicates} duplicates in a row. Stopping."
                        )
                        return  # Clean return triggers cleanup
                    continue

                # --- NEW ITEM ---
                consecutive_duplicates = 0
                seen_urls.add(item_url)
                writer.writerow(item)
                f.flush()
                items_scraped += 1

                logger.info(
                    f"[{items_scraped} New] Saved: {item.get('product_name', 'Unknown')}"
                )

                if MAX_ITEMS > 0 and items_scraped >= MAX_ITEMS:
                    logger.info(f"Max item limit reached ({MAX_ITEMS}). Stopping.")

                    # Create a beep sound using pygame

                    return

        except (RuntimeError, ValueError, asyncio.CancelledError):
            # This block swallows the "Attempted to exit cancel scope" error
            # caused by stopping the generator early.
            pass
        except Exception as e:
            logger.error(f"Unexpected error: {e}", exc_info=True)


if __name__ == "__main__":
    try:
        asyncio.run(run())
        logger.info("Scraper finished successfully.")
        sys.exit(0)  # Explicit success code so Docker 'on-failure' knows to stop
    except KeyboardInterrupt:
        logger.info("Paused via KeyboardInterrupt.")
        sys.exit(0)
    except Exception as e:
        logger.error("Fatal error!", exc_info=True)
        sys.exit(1)  # Crash code so Docker 'on-failure' knows to restart
