import logging

logger = logging.getLogger("StarTech")

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
    """
    Standard entry point function expected by main.py
    """
    logger.info(f"🌍 Visiting URL: {response.url}")
    
    # --- 1. PRODUCT EXTRACTION ---
    if "product" in response.url or response.xpath('//div[contains(@class, "product-details")]').get():
        logger.info("🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()
        
        product["product_name"] = response.css("h1.product-name::text").get("").strip()
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        product["primary_image_url"] = response.xpath("/html/body/div[5]/div[1]/div/div[2]/div[1]/div[1]/div/a/img/@src").get("").strip()
        
        # Prices
        price_text = response.css('td.product-price::text, td.product-price > ins::text').get("").strip()
        product["current_price"] = price_text.replace("৳", "").replace(",", "").strip() if price_text else ""
        
        price_old = response.css('td.product-regular-price::text').get("").strip()
        product["original_price"] = price_old.replace("৳", "").replace(",", "").strip() if price_old else ""

        # Meta
        product["category_name"] = response.xpath('/html/body/section/div/ul/li[2]/a/span/text()').get("").strip()
        product["review_count"] = response.xpath('//*[@id="write-review"]/div[1]/div[1]/h2/text()').get("").strip()
        
        # Stock & Status
        stock_text = response.css('.product-status::text').get("").strip()
        product["in_stock"] = "Yes" if "In Stock" in stock_text else "No"
        product["seller_sku"] = response.css('.product-code::text').get("").strip()
        product["seller_name"] = seller_name
        product["base_url"] = base_url
        product["is_active"] = "1" if product["in_stock"] == "Yes" else "0"

        yield product
    else:
        logger.info("🗂️ Category/Nav page detected.")

    # --- 2. LINK FOLLOWING ---
    if not recurse:
        logger.info(f"🛑 Recursion is OFF. Stopping here.")
        return

    # Selectors specific to StarTech
    target_selectors = [
        'h4.p-item-name a::attr(href)',  # Products
        'ul.pagination a::attr(href)'    # Pagination
    ]
    
    valid_links = response.css(', '.join(target_selectors)).getall()
    unique_links = list(set(valid_links))
    
    logger.info(f"🔍 Found {len(unique_links)} unique target links.")
    
    for link in unique_links:
        if any(ignored in link.lower() for ignored in ['/account', '/cart', '/checkout', '/login', 'javascript:', 'tel:', 'mailto:', "question", "review"]):
            continue
        yield response.follow(link)