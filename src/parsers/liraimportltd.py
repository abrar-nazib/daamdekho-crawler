import logging

logger = logging.getLogger("LiraImportLtd")

# Define the base structure specifically for this site if needed, 
# or import a shared one if they are all identical.
BASE_PRODUCT = {
    "category_slug": "", 
    "product_name": "", 
    "product_slug": "", 
    "seller_slug": "",
    "current_price": "", 
    "seller_product_url": "", 
    "brand_slug": "", 
    "brand_name": "", 
    "product_description": "", 
    "model": "", 
    "sku": "", 
    "primary_image_url": "", 
    "image_urls": "", 
    "specifications": "", 
    "attributes": "", 
    "variation_type": "",
    "parent_product_slug": "", 
    "original_price": "", 
    "currency": "BDT", 
    "in_stock": "", 
    "stock_quantity": "", 
    "seller_rating": "", 
    "review_count": "", 
    "shipping_cost": "",
    "free_shipping": "", 
    "estimated_delivery_days": "", 
    "seller_sku": "", 
    "seller_product_name": "", 
    "category_path": "", 
    "category_name": "", 
    "category_description": "", 
    "seller_name": "",
    "base_url": "",
    "seller_country_code": "BD", 
    "is_active": ""
}
def parse(response, seller_name, base_url, recurse=True):
    logger.info(f"🌍 Visiting URL: {response.url}")

    # --- 1. Detect product page vs category ---
    is_product_page = (
        "/product/" in response.url and "product-category" not in response.url
    ) or bool(response.css("body.single-product"))

    if is_product_page:
        logger.info("🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()

        product["product_name"] = response.xpath(
            '//h1[@class="product_title entry-title"]/text()'
        ).get("").strip()
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        product["primary_image_url"] = response.xpath(
            '//div[contains(@class,"woocommerce-product-gallery")]//img/@src'
        ).get("").strip()

        price_text = response.css("p.price span.woocommerce-Price-amount bdi::text").get("")
        product["current_price"] = price_text.replace("৳", "").replace(",", "").strip() if price_text else ""

        product["category_name"] = response.css(
            "nav.woocommerce-breadcrumb a:nth-child(3)::text"
        ).get("").strip()
        product["review_count"] = "0"

        product["in_stock"] = "YES"
        product["seller_sku"] = ""
        product["seller_name"] = seller_name
        product["base_url"] = base_url
        product["is_active"] = "1"

        yield product

    else:
        logger.info("🗂️ Category/Nav page detected.")

    # --- 2. LINK FOLLOWING ON CATEGORY PAGES ---
    if not recurse:
        logger.info("🛑 Recursion is OFF. Stopping here.")
        return

    # Only bother looking for links on non-product or mixed pages
    target_selectors = [
        "ul.products li.product a.woocommerce-LoopProduct-link::attr(href)",  # product links
        "nav.woocommerce-pagination a.page-numbers::attr(href)",              # pagination
    ]

    valid_links = response.css(", ".join(target_selectors)).getall()
    unique_links = list(set(valid_links))

    logger.info(f"🔍 Found {len(unique_links)} unique target links.")

    for link in unique_links:
        if any(
            ignored in link.lower()
            for ignored in ["/account", "/cart", "/checkout", "/login", "javascript:", "tel:", "mailto:"]
        ):
            continue
        yield response.follow(link)