"""
parsers/Herlan.py — Product parser for herlan.com
===================================================
CONTRACT (must be followed by every parser):
  • Expose exactly one public function:
        parse(driver, seller_name: str, base_url: str) -> dict | None

  • Return a filled BASE_PRODUCT dict  — OR —  None to skip the URL.

  • Do NOT wrap individual fields in try/except — the helpers do it for you.

  • Do NOT fill these fields — main.py derives them automatically:
        product_slug, brand_slug, category_slug, seller_slug,
        parent_product_slug, is_active
    Override them here only if the site provides a better canonical value.

HOW TO CREATE A NEW PARSER:
  1. Copy this file to  parsers/{SELLER_NAME}.py
  2. Update PRODUCT_PAGE_GUARD and all XPath / CSS expressions in parse()
  3. Set SELLER_NAME in .env — the dynamic importer finds it automatically

─────────────────────────────────────────────────────────────────────────────
SELECTOR HELPERS — full reference
─────────────────────────────────────────────────────────────────────────────
Every helper accepts  selector_type = "xpath"  or  "css"  as its first arg.
All helpers have built-in try/except — they never raise, they just return ""/[].

  _get_text(selector_type, selector, driver)
      → str   — .text of the FIRST matching element
      Example: _get_text("xpath", '//h1[@class="product_title"]', driver)
      Example: _get_text("css",   "h1.product_title",             driver)

  _get_attr(selector_type, selector, attr, driver)
      → str   — attribute value of the FIRST matching element
      Example: _get_attr("xpath", '(//img[@class="wp-post-image"])[1]', "src", driver)
      Example: _get_attr("css",   "img.wp-post-image",                  "src", driver)

  _get_all_texts(selector_type, selector, driver)
      → list[str]  — .text of ALL matching elements
      Example: _get_all_texts("xpath", '//li[@class="breadcrumb"]/a', driver)
      Example: _get_all_texts("css",   "li.breadcrumb a",             driver)

  _get_all_attrs(selector_type, selector, attr, driver)
      → list[str]  — attribute value of ALL matching elements
      Example: _get_all_attrs("xpath", '//li[@itemprop="associatedMedia"]/img', "src", driver)
      Example: _get_all_attrs("css",   "li[itemprop='associatedMedia'] img",    "src", driver)

NOTE: Selenium's find_element does NOT support /text() or /@attr suffixes in
      XPath. Use _get_text() for text content and _get_attr() for attributes.
─────────────────────────────────────────────────────────────────────────────
"""

import importlib
from selenium.webdriver.common.by import By


# ── Lazy BASE_PRODUCT import (avoids circular import with main.py) ─────────────
def _get_base_product() -> dict:
    return importlib.import_module("main").BASE_PRODUCT.copy()


# ── Selector type resolver ─────────────────────────────────────────────────────

def _by(selector_type: str):
    """
    Map a human-friendly selector type to a Selenium By constant.
      "xpath"  →  By.XPATH
      "css"    →  By.CSS_SELECTOR
    """
    t = selector_type.strip().lower()
    if t == "xpath":
        return By.XPATH
    if t in ("css", "css_selector"):
        return By.CSS_SELECTOR
    raise ValueError(f"Unknown selector_type '{selector_type}'. Use 'xpath' or 'css'.")


# ── Helpers ────────────────────────────────────────────────────────────────────
# All helpers absorb exceptions silently — no try/except needed in parse().

def _get_text(selector_type: str, selector: str,
              driver, default: str = "") -> str:
    """Return stripped .text of the FIRST matching element, or `default`."""
    try:
        return driver.find_element(_by(selector_type), selector).text.strip()
    except Exception:
        return default


def _get_attr(selector_type: str, selector: str,
              attr: str, driver, default: str = "") -> str:
    """Return the `attr` value of the FIRST matching element, or `default`."""
    try:
        val = driver.find_element(_by(selector_type), selector).get_attribute(attr)
        return val.strip() if val else default
    except Exception:
        return default


def _get_all_texts(selector_type: str, selector: str, driver) -> list[str]:
    """Return a list of stripped .text values from ALL matching elements."""
    try:
        return [
            el.text.strip()
            for el in driver.find_elements(_by(selector_type), selector)
            if el.text.strip()
        ]
    except Exception:
        return []


def _get_all_attrs(selector_type: str, selector: str,
                   attr: str, driver) -> list[str]:
    """Return a list of `attr` values from ALL matching elements."""
    try:
        return [
            el.get_attribute(attr).strip()
            for el in driver.find_elements(_by(selector_type), selector)
            if el.get_attribute(attr)
        ]
    except Exception:
        return []


# ── Page guard ─────────────────────────────────────────────────────────────────
# Adjust this function to match the URL structure of the target site.
# Return True  → page is a scrapeable product page
# Return False → page is a category/nav page; parse() will return None

def _is_product_page(url: str) -> bool:
    return "/product/" in url and "/product-category/" not in url


# ── Main parse function ────────────────────────────────────────────────────────

def parse(driver, seller_name: str, base_url: str) -> dict | None:
    """
    Scrape one product page and return a filled BASE_PRODUCT dict.

    Parameters
    ----------
    driver      : Selenium WebDriver — page already loaded by main.py
    seller_name : SELLER_NAME from .env  (e.g. "Herlan")
    base_url    : BASE_URL from main.py  (e.g. "https://herlan.com")

    Returns
    -------
    dict   → one row written to the output CSV by main.py
    None   → URL skipped and logged to failed_urls.txt by main.py
    """

    current_url = driver.current_url

    # Skip non-product pages (category pages, navigation, etc.)


    product = _get_base_product()

    # ── product_name ───────────────────────────────────────────────────────────
    # auto-derives → product_slug
    product["product_name"] = _get_text(
        "xpath", '//div[@class="mt-2 title-full fs-6"]', driver
    )

    # ── seller_product_name ────────────────────────────────────────────────────
    # Usually identical to product_name on WooCommerce sites
    product["seller_product_name"] = product["product_name"]

    # ── seller_product_url ─────────────────────────────────────────────────────
    product["seller_product_url"] = current_url

    # ── prices ─────────────────────────────────────────────────────────────────
    # WooCommerce price block:
    #   1 <bdi>  → regular price only  (current = original)
    #   2 <bdi>  → first = original,   second = sale / current
    try:
        price_els = driver.find_elements(By.XPATH, '//span[contains(@class,"fw-semibold")]')
        if len(price_els) >= 2:
            product["original_price"] = (
                price_els[0].text.replace("৳", "").replace(",", "").strip()
            )
            product["current_price"] = (
                price_els[2].text.replace("৳", "").replace(",", "").strip()
            )
        elif len(price_els) == 1:
            product["current_price"] = (
                price_els[0].text.replace("৳", "").replace(",", "").strip()
            )
            product["original_price"] = product["current_price"]
    except Exception:
        pass    # both prices stay ""

    # ── currency ───────────────────────────────────────────────────────────────
    product["currency"] = "BDT"

    # ── primary_image_url ──────────────────────────────────────────────────────
    product["primary_image_url"] = _get_attr(
        "xpath", '(//div[@data-swiper-slide-index and contains(@class,"swiper-slide-visible")]/img)[1]', "src", driver
    )

    # ── image_urls (all gallery images, semicolon-separated) ──────────────────
    product["image_urls"] = ";".join(
        _get_all_attrs("xpath", '//div[@data-swiper-slide-index and contains(@class,"swiper-slide-visible")]/img', "src", driver)
    )

    # ── category_name ──────────────────────────────────────────────────────────
    # auto-derives → category_slug
    # product["category_name"] = _get_text(
    #     "xpath", '(//nav[@class="woocommerce-breadcrumb"]/a)[last()]', driver
    # )

    # ── brand_name ─────────────────────────────────────────────────────────────
    # auto-derives → brand_slug
    product["brand_name"] = _get_text(
        "xpath", '//div[@class="title fw-bold fs-5"]/a', driver
    )

    # ── in_stock ───────────────────────────────────────────────────────────────
    # auto-derives → is_active
    try:
        stock_els  = driver.find_elements(
            By.XPATH,
            '(//span[@class="ms-1 m-fs-6 fs-6"])[1]'
        )
        stock_text = stock_els[0].text if stock_els else ""
        product["in_stock"] = "Yes" if "Add to Cart" in stock_text else "No"
    except Exception:
        pass    # in_stock stays ""

    # ── product_description ────────────────────────────────────────────────────
    # We grab the entire first accordion div's .text in one call.
    # Selenium's .text returns all visible text inside an element (including
    # nested children) cleanly — equivalent to scrapling's //text() joined.
    # Using //* and joining .text of each child would duplicate text because
    # a parent element's .text already includes its children's text.
    product["product_description"] = _get_text(
        "xpath", '//ul[@id="shortDesc"]', driver
    )

    # ── review_count ───────────────────────────────────────────────────────────
    # product["review_count"] = _get_text("css", "span.count", driver) or "0"

    # ── seller metadata ────────────────────────────────────────────────────────
    product["seller_name"]         = seller_name
    product["base_url"]            = base_url
    product["seller_country_code"] = "BD"

    # ── Fields not available on herlan.com ────────────────────────────────────
    # These remain "" → empty CSV cells.
    # Add the XPath/CSS extraction here if the site exposes them.
    #
    #   model                   _get_text("xpath", "...", driver)
    #   sku                     _get_text("xpath", "...", driver)
    #   specifications          _get_text("xpath", "...", driver)
    #   attributes              _get_text("xpath", "...", driver)
    #   variation_type          _get_text("xpath", "...", driver)
    #   stock_quantity          _get_text("xpath", "...", driver)
    #   seller_rating           _get_text("xpath", "...", driver)
    #   shipping_cost           _get_text("xpath", "...", driver)
    #   free_shipping           _get_text("xpath", "...", driver)
    #   estimated_delivery_days _get_text("xpath", "...", driver)
    #   seller_sku              _get_text("xpath", "...", driver)
    #   category_path           _get_text("xpath", "...", driver)
    #   category_description    _get_text("xpath", "...", driver)

    return product