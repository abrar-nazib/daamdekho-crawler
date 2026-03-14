import csv
import time
import sys
from urllib.parse import urljoin, urlparse, parse_qs, urlencode
import os

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    StaleElementReferenceException,
    NoSuchElementException,
    TimeoutException,
)

current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(current_dir)
csv_dir = os.path.join(root_dir, "data", "csvs")
os.makedirs(csv_dir, exist_ok=True)

SELLER = "KireiBD"
INPUT_CSV = os.path.join(csv_dir, f"{SELLER}_entrypoints.csv")
OUTPUT_CSV = os.path.join(csv_dir, f"{SELLER}_product_links.csv")
PAGE_LOAD_WAIT = 15     # seconds to wait for page elements
RENDER_SETTLE_DELAY = 2 # seconds to let JS framework finish rendering
BETWEEN_PAGE_DELAY = 1  # seconds to wait between page navigations


def build_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1920,1080")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


def wait_for_products(driver: webdriver.Chrome):
    """
    Wait until the page has at least one product link OR a known
    'no results' indicator.  Falls back to a plain <a> presence check.
    """
    try:
        # Primary: wait for a product link to appear
        WebDriverWait(driver, PAGE_LOAD_WAIT).until(
            lambda d: len(d.find_elements(By.XPATH, "//a[contains(@href,'/product/')]")) > 0
            or len(d.find_elements(By.CSS_SELECTOR, "li.next, li.previous")) > 0
        )
    except TimeoutException:
        # Fallback: at least some <a> tags exist
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.TAG_NAME, "a"))
        )
    # Give the JS framework a moment to finish any final DOM patches
    time.sleep(RENDER_SETTLE_DELAY)


def get_product_links(driver: webdriver.Chrome, base_url: str) -> set[str]:
    """
    Collect all href values that contain '/product/' using a single
    JavaScript call so we never hold live WebElement references across
    a DOM mutation (avoids StaleElementReferenceException entirely).
    """
    hrefs: list[str] = driver.execute_script(
        """
        return Array.from(document.querySelectorAll('a[href]'))
            .map(a => a.getAttribute('href'))
            .filter(h => h && h.includes('/product/'));
        """
    )
    links = set()
    for href in hrefs:
        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)
        clean = parsed._replace(query="", fragment="").geturl()
        links.add(clean)
    return links


def get_next_page_url(driver: webdriver.Chrome, current_url: str) -> str | None:
    """
    Determine the next-page URL from the pagination widget.

    Strategy (in order):
    1. li.next must exist and must NOT have class 'disabled'.
    2. The inner <a> must NOT have aria-disabled="true".
    3. Use the href on that <a> if present.
    4. Otherwise read li.selected's text, increment, and inject ?page=N.
    """
    try:
        # Use JS to read pagination state atomically
        result: dict = driver.execute_script(
            """
            var nextLi = document.querySelector('li.next');
            if (!nextLi) return {found: false, reason: 'no li.next'};
            if (nextLi.classList.contains('disabled'))
                return {found: false, reason: 'li.next disabled'};

            var a = nextLi.querySelector('a');
            if (!a) return {found: false, reason: 'no a in li.next'};
            if (a.getAttribute('aria-disabled') === 'true')
                return {found: false, reason: 'a aria-disabled'};

            var href = a.getAttribute('href') || '';

            var selectedLi = document.querySelector('li.selected a');
            var currentPage = selectedLi ? parseInt(selectedLi.textContent.trim(), 10) : null;

            return {found: true, href: href, currentPage: currentPage};
            """
        )

        if not result.get("found"):
            print(f"    Pagination end: {result.get('reason', 'unknown')}")
            return None

        href = result.get("href", "")
        if href:
            return urljoin(current_url, href)

        # Fallback: build URL from page number
        current_page = result.get("currentPage")
        if current_page is None:
            return None

        next_page = current_page + 1
        parsed = urlparse(current_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        qs["page"] = [str(next_page)]
        new_query = urlencode(qs, doseq=True)
        return parsed._replace(query=new_query).geturl()

    except Exception as e:
        print(f"    [WARN] get_next_page_url error: {e}")
        return None


def scrape_url(driver: webdriver.Chrome, start_url: str) -> list[str]:
    """Crawl all paginated pages for start_url and return unique product links."""
    all_links: set[str] = set()
    current_url = start_url
    page_num = 1

    print(f"\n  ↳ Starting URL: {start_url}")

    while current_url:
        print(f"    Page {page_num}: {current_url}")
        driver.get(current_url)

        try:
            wait_for_products(driver)
        except TimeoutException:
            print("    [WARN] Timed out waiting for page to load. Skipping.")
            break

        new_links = get_product_links(driver, current_url)
        added = new_links - all_links

        if not added and page_num > 1:
            print(f"    No new product links on page {page_num}. Stopping.")
            break

        all_links |= new_links
        print(
            f"    Found {len(new_links)} product links "
            f"({len(added)} new). Total: {len(all_links)}"
        )

        next_url = get_next_page_url(driver, current_url)
        if not next_url or next_url == current_url:
            print("    No further pages.")
            break

        current_url = next_url
        page_num += 1
        time.sleep(BETWEEN_PAGE_DELAY)

    return sorted(all_links)


def read_input_urls(path: str) -> list[str]:
    urls = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get("url", "").strip()
            if url:
                urls.append(url)
    return urls


def write_output(path: str, rows: list[dict]):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["source_url", "product_url"])
        writer.writeheader()
        writer.writerows(rows)


def main():
    input_file = sys.argv[1] if len(sys.argv) > 1 else INPUT_CSV
    output_file = sys.argv[2] if len(sys.argv) > 2 else OUTPUT_CSV

    print(f"Reading URLs from: {input_file}")
    urls = read_input_urls(input_file)
    if not urls:
        print("No URLs found in input CSV. Exiting.")
        sys.exit(1)

    print(f"Found {len(urls)} URL(s) to process.")

    driver = build_driver()
    all_rows: list[dict] = []

    try:
        for source_url in urls:
            product_links = scrape_url(driver, source_url)
            for link in product_links:
                all_rows.append({"source_url": source_url, "product_url": link})
    finally:
        driver.quit()

    write_output(output_file, all_rows)
    print(f"\n✓ Done. {len(all_rows)} product link(s) written to: {output_file}")


if __name__ == "__main__":
    main()