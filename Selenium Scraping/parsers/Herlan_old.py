"""
parsers/Herlan.py — Product parser for herlan.com
===================================================
CONTRACT (must be followed by every parser):
  • Expose exactly one public function:

        parse(driver, seller_name: str, base_url: str) -> dict | None

  • Return a filled copy of BASE_PRODUCT (imported from main) — OR —
    return None if the page is not a scrapeable product page.

  • Use try/except on every individual field extraction so that one
    missing element never crashes the whole parser.

  • Do NOT fill these fields — main.py derives them automatically:
        product_slug, brand_slug, category_slug, seller_slug,
        parent_product_slug, is_active

  • You CAN override them if the site provides a better/canonical value.

HOW TO CREATE A NEW PARSER:
  1. Copy this file to  parsers/{SELLER_NAME}.py
  2. Update the XPath expressions below to match the new site's HTML.
  3. Set SELLER_NAME in .env — the dynamic importer will find it automatically.
"""

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ── BASE_PRODUCT is imported from main so all parsers share the same template ─
# We import it lazily to avoid circular imports.
import importlib

def _get_base_product():
    main = importlib.import_module("main")
    return main.BASE_PRODUCT.copy()


# ── Small XPath helper ────────────────────────────────────────────────────────

def _get_text(driver, xpath: str, default: str = "") -> str:
    """
    Return the stripped text of the FIRST element matched by xpath.
    Returns `default` if nothing is found or an exception occurs.

    Usage:
        name = _get_text(driver, '//h1[@class="product_title"]/text()')
    
    NOTE: Selenium's find_element does not support /text() in XPath.
          Use the element's .text property instead (handled below).
          For attributes like /@src, use _get_attr() instead.
    """
    try:
        # Strip /text() suffix — Selenium reads text via .text, not XPath text()
        clean_xpath = xpath.rstrip("/text()") if xpath.endswith("/text()") else xpath
        el = driver.find_element(By.XPATH, clean_xpath)
        return el.text.strip()
    except Exception:
        return default


def _get_attr(driver, xpath: str, attr: str, default: str = "") -> str:
    """
    Return the value of `attr` from the FIRST element matched by xpath.
    Returns `default` if nothing is found or an exception occurs.

    Usage:
        src = _get_attr(driver, '//img[@class="main-image"]', "src")
    """
    try:
        el = driver.find_element(By.XPATH, xpath)
        return el.get_attribute(attr).strip()
    except Exception:
        return default


def _get_all_attrs(driver, xpath: str, attr: str) -> list[str]:
    """
    Return a list of `attr` values from ALL elements matched by xpath.
    Returns an empty list if nothing is found.

    Usage:
        srcs = _get_all_attrs(driver, '//li[@itemprop="associatedMedia"]/img', "src")
    """
    try:
        elements = driver.find_elements(By.XPATH, xpath)
        return [el.get_attribute(attr).strip() for el in elements if el.get_attribute(attr)]
    except Exception:
        return []


def _get_all_texts(driver, xpath: str) -> list[str]:
    """
    Return a list of stripped .text values from ALL elements matched by xpath.
    Returns an empty list if nothing is found.
    """
    try:
        elements = driver.find_elements(By.XPATH, xpath)
        return [el.text.strip() for el in elements if el.text.strip()]
    except Exception:
        return []


# ── Main parse function ───────────────────────────────────────────────────────

def parse(driver, seller_name: str, base_url: str) -> dict | None:
    """
    Scrape one product page and return a filled BASE_PRODUCT dict.

    Parameters
    ----------
    driver      : Selenium WebDriver (page is already loaded by main.py)
    seller_name : Value of SELLER_NAME from .env  (e.g. "Herlan")
    base_url    : Value of BASE_URL from main.py  (e.g. "https://herlan.com")

    Returns
    -------
    dict   — filled product dict to be written as one CSV row
    None   — page is not a product page; main.py will skip and log it
    """

    current_url = driver.current_url

    # ── Guard: only scrape actual product pages ───────────────────────────────
    # Adjust this condition to match the URL pattern of the target site.
    # herlan.com product pages contain "/product/" but NOT "/product-category/"
    if "/product/" not in current_url or "/product-category/" in current_url:
        return None

    product = _get_base_product()

    # ── product_name ──────────────────────────────────────────────────────────
    # XPath: the <h1> with class "product_title entry-title"
    # NOTE: main.py auto-derives product_slug from this value.
    try:
        product["product_name"] = _get_text(
            driver, '//h1[@class="product_title entry-title"]'
        )
    except Exception:
        product["product_name"] = ""

    # ── seller_product_name ───────────────────────────────────────────────────
    # Usually the same as product_name on most WooCommerce sites.
    product["seller_product_name"] = product["product_name"]

    # ── seller_product_url ────────────────────────────────────────────────────
    product["seller_product_url"] = current_url

    # ── current_price ─────────────────────────────────────────────────────────
    # WooCommerce: sale price is the SECOND <bdi> inside .price
    # If there is no sale, there is only one <bdi> — handled by original_price below.
    try:
        price_els = driver.find_elements(By.XPATH, '//p[@class="price"]//bdi')
        if len(price_els) >= 2:
            # Two prices present → first = original, second = sale/current
            product["current_price"] = (
                price_els[1].text.replace("৳", "").replace(",", "").strip()
            )
            product["original_price"] = (
                price_els[0].text.replace("৳", "").replace(",", "").strip()
            )
        elif len(price_els) == 1:
            # Only one price → it is both current and original
            product["current_price"] = (
                price_els[0].text.replace("৳", "").replace(",", "").strip()
            )
            product["original_price"] = product["current_price"]
    except Exception:
        product["current_price"]  = ""
        product["original_price"] = ""

    # ── currency ──────────────────────────────────────────────────────────────
    # Hardcoded in BASE_PRODUCT template — override here if the site uses a
    # different currency for some products.
    product["currency"] = "BDT"

    # ── primary_image_url ─────────────────────────────────────────────────────
    # First image in the product gallery (<li itemprop="associatedMedia">)
    try:
        product["primary_image_url"] = _get_attr(
            driver,
            '(//li[@itemprop="associatedMedia"]/img)[1]',
            "src"
        )
    except Exception:
        product["primary_image_url"] = ""

    # ── image_urls ────────────────────────────────────────────────────────────
    # All gallery images joined by ";"
    try:
        imgs = _get_all_attrs(
            driver,
            '//li[@itemprop="associatedMedia"]/img',
            "src"
        )
        product["image_urls"] = ";".join(imgs)
    except Exception:
        product["image_urls"] = ""

    # ── category_name ─────────────────────────────────────────────────────────
    # Last breadcrumb link before the current page title
    # NOTE: main.py auto-derives category_slug from this value.
    try:
        product["category_name"] = _get_text(
            driver,
            '(//nav[@class="woocommerce-breadcrumb"]/a)[last()]'
        )
    except Exception:
        product["category_name"] = ""

    # ── brand_name ────────────────────────────────────────────────────────────
    # WooCommerce product tag item — first tag is treated as brand
    # NOTE: main.py auto-derives brand_slug from this value.
    try:
        product["brand_name"] = _get_text(
            driver,
            '(//li[contains(@class,"product-tag-item")])[1]/a'
        )
    except Exception:
        product["brand_name"] = ""

    # ── in_stock ──────────────────────────────────────────────────────────────
    # WooCommerce shows a <p> containing "In stock" text
    # NOTE: main.py auto-derives is_active from this value.
    try:
        stock_el = driver.find_elements(
            By.XPATH, '//p[contains(@class,"stock") or contains(text(),"In stock")]'
        )
        stock_text = stock_el[0].text if stock_el else ""
        product["in_stock"] = "Yes" if "in stock" in stock_text.lower() else "No"
    except Exception:
        product["in_stock"] = ""

    # ── product_description ───────────────────────────────────────────────────
    # First accordion section on herlan.com — adjust XPath per site
    try:
        desc_els = _get_all_texts(
            driver,
            '(//div[@class="cg-accordion-item"])[1]//*'
        )
        product["product_description"] = " ".join(desc_els)
    except Exception:
        product["product_description"] = ""

    # ── review_count ─────────────────────────────────────────────────────────
    try:
        product["review_count"] = _get_text(
            driver,
            '//span[@class="count"]'   # adjust if site uses a different element
        ) or "0"
    except Exception:
        product["review_count"] = "0"

    # ── seller metadata ───────────────────────────────────────────────────────
    product["seller_name"]         = seller_name
    product["base_url"]            = base_url
    product["seller_country_code"] = "BD"

    # ── Fields NOT available on herlan.com ────────────────────────────────────
    # Leave these blank ("") — they will be written as empty CSV cells.
    # Fill them in if the site exposes them.
    #
    #   model, sku, specifications, attributes, variation_type,
    #   stock_quantity, seller_rating, shipping_cost, free_shipping,
    #   estimated_delivery_days, seller_sku, category_path,
    #   category_description, seller_product_url

    return product
