import os

from scrapling.fetchers import Fetcher, AsyncFetcher, StealthyFetcher, DynamicFetcher

file_dir = os.path.dirname(os.path.abspath(__file__))

try:
    page = StealthyFetcher.fetch("https://kireibd.com/shop?category=international-brands")
    print(page.body[:100])
    # Dump the page content to a file for inspection
    with open(os.path.join(file_dir, "stealthy_fetcher_output.html"), "wb") as f:
        f.write(page.body)
except Exception as e:
    print(f"Error occurred: {e}")

try:
    page = DynamicFetcher.fetch("https://kireibd.com/shop?category=international-brands")
    print(page.body[:100])
    # Dump the page content to a file for inspection
    with open(os.path.join(file_dir, "dynamic_fetcher_output.html"), "wb") as f:
        f.write(page.body)
except Exception as e:
    print(f"Error occurred: {e}")



