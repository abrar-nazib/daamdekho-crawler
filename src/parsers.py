import logging

# Set up a logger specifically for the parsers
logger = logging.getLogger("Parser")

# A template dictionary matching your ref.csv perfectly.
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

def parse_startech(response, seller_name, base_url):
    """Extraction logic specifically for StarTech"""
    
    logger.info(f"[StarTech] 🌍 Visiting URL: {response.url}")
    
    # --- 1. PRODUCT EXTRACTION LOGIC ---
    if "product" in response.url or response.xpath('//div[contains(@class, "product-details")]').get():
        logger.info(f"[StarTech] 🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()
        
        product["product_name"] = response.css("h1.product-name::text").get("").strip()
        product["product_description"] = response.xpath('//*[@id="description"]/div[2]/p[1]//text()').get("").strip()
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        
        product["primary_image_url"] = response.xpath("/html/body/div[5]/div[1]/div/div[2]/div[1]/div[1]/div/a/img/@src").get("").strip()
        
        product["current_price"] = response.css('td.product-price::text').get("").strip()
        product["original_price"] = response.css('td.product-regular-price::text').get("").strip()

        product["category_name"] = response.xpath('/html/body/section/div/ul/li[2]/a/span/text()').get("").strip()
        product["review_count"] = response.xpath('//*[@id="write-review"]/div[1]/div[1]/h2/text()').get("").strip()
        
        stock_text = response.css('.product-status::text').get("").strip()
        product["in_stock"] = "Yes" if "In Stock" in stock_text else "No"
        product["seller_sku"] = response.css('.product-code::text').get("").strip()
        product["seller_name"] = seller_name
        product["base_url"] = base_url
        product["is_active"] = "1" if product["in_stock"] == "Yes" else "0"

        yield product
    else:
        logger.info(f"[StarTech] 🗂️ Category/Nav page detected. Scanning for links...")

    # --- 2. LINK FOLLOWING LOGIC (Un-indented so it runs on ALL pages) ---
    target_selectors =[
        # 'ul.navbar-nav a::attr(href)',   # Mega-menu categories
        'h4.p-item-name a::attr(href)',  # Products in grids
        'ul.pagination a::attr(href)'    # Next pages in categories
    ]
    
    # Combine the selectors into one comma-separated string
    valid_links = response.css(', '.join(target_selectors)).getall()
    
    # Remove duplicates from the page to clean up our logs
    unique_links = list(set(valid_links))
    
    logger.info(f"[StarTech] 🔍 Found {len(unique_links)} unique target links on this page.")
    
    links_queued = 0
    for link in unique_links:
        # Extra safety measure: ensure we don't accidentally crawl login/cart urls
        if any(ignored in link.lower() for ignored in['/account', '/cart', '/checkout', '/login', 'javascript:', 'tel:', 'mailto:', "qestion", "/question", "review", "/review"]):
            continue
            
        # logger.info(f"[StarTech] ---> Queuing link: {link}")
        links_queued += 1
        yield response.follow(link)

    logger.info(f"[StarTech] ✅ Successfully added {links_queued} links to the crawl queue from {response.url}")


def parse_ryans(response, seller_name, base_url):
    """Extraction logic specifically for Ryans"""
    for link in response.css("a::attr(href)").getall():
        yield response.follow(link)

PARSERS = {
    "startech.com.bd": parse_startech,
    "ryanscomputers.com": parse_ryans
}