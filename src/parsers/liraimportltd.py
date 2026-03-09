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
    """
    Standard entry point function expected by main.py
    """
    logger.info(f"🌍 Visiting URL: {response.url}")
    
    # --- 1. PRODUCT EXTRACTION ---
    # Check if it's a single product page (not a category page)
    is_product_page = "product" in response.url and "product-category" not in response.url
    
    if is_product_page:
        logger.info("🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()
        
        product["product_name"] = response.xpath('//h1[@class="product_title entry-title"]/text()').get("").strip()
        product["product_slug"] = product["product_name"].lower().replace(" ", "-")
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        product["primary_image_url"] = response.xpath('//a[@class="woocommerce-main-image pswp-main-image zoom"]/img/@src').get("").strip()
        
        # Prices
        price_text = response.xpath('(//p[@class="price"]//bdi)[2]/text()').get("").strip()
        product["current_price"] = price_text.replace("৳", "").replace(",", "").strip() if price_text else ""
        
        price_old = response.xpath('(//p[@class="price"]//bdi)[1]/text()').get("").strip()
        product["original_price"] = price_old.replace("৳", "").replace(",", "").strip() if price_old else ""

        # Meta
        product["category_name"] = response.xpath('(//nav[@class="woocommerce-breadcrumb"]/a)[3]/text()').get("").strip()
        product['brand_name'] = response.xpath('//span[@class="product_brand"]/a/text()').get("").strip()
        product["brand_slug"] = product["brand_name"].lower().replace(" ", "-")
        product["review_count"] = 0
        
        # Stock & Status
        # stock_text = response.css('.product-status::text').get("").strip()
        product["in_stock"] = "YES"
        # product["seller_sku"] = response.css('.product-code::text').get("").strip()
        product["seller_sku"] = ""
        product["seller_name"] = seller_name
        product["base_url"] = base_url
        product["is_active"] = "1"
        product["seller_sku"] = response.xpath('(//span[@class="sku"])[1]/text()').get("").strip() 
        overview_lines = response.xpath('//div[@aria-labelledby="tab-title-description"]//text()').getall()
        # Clean and join them with newlines to form a readable description block
        product["product_description"] = "".join([line.strip() for line in overview_lines if line.strip()])
        yield product
    else:
        logger.info("🗂️ Category/Nav page detected.")

    # --- 2. LINK FOLLOWING ---
    if not recurse:
        logger.info(f"🛑 Recursion is OFF. Stopping here.")
        return


    target_selectors = [
        '//div[@class="images-slider-wrapper"]/a/@href',  # Products
        '//a[@class="next page-numbers"]/@href'    # Pagination
    ]
    
    valid_links = response.xpath(', '.join(target_selectors)).getall()
    unique_links = list(set(valid_links))
    
    logger.info(f"🔍 Found {len(unique_links)} unique target links.")
    
    for link in unique_links:
        if any(ignored in link.lower() for ignored in ['/account', '/cart', '/checkout', '/login', 'javascript:', 'tel:', 'mailto:', "question", "review"]):
            continue
        yield response.follow(link)