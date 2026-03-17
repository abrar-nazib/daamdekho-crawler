import logging

logger = logging.getLogger("LiraImportLtd")

# Define the base structure
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

async def parse(response, seller_name, base_url, recurse=True):
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
        # product["primary_image_url"] = response.xpath('(//li[@itemprop="associatedMedia"]/img/@src)[1]').get("").strip()
        # product["primary_image_url"] = product["primary_image_url"].replace("data:", "")
        # all_images = response.xpath('(//li[@itemprop="associatedMedia"]/img/@src)').getall().replace("data:", "")
        # # Filter out data URLs (placeholders)
        # all_images = [img for img in all_images if not img.startswith('data:')]

        # product["image_urls"]  = ";".join([line.strip() for line in all_images if line.strip()])
        # Primary image
        # all_images = response.xpath('//li[@itemprop="associatedMedia"]//img/@src').getall()

        # all_images = [str(img).strip() for img in all_images]

        # # remove base64 placeholders
        # all_images = [img for img in all_images if img and not img.startswith("data:")]

        # # remove duplicates while keeping order
        # all_images = list(dict.fromkeys(all_images))
        all_images = response.xpath('//li[@itemprop="associatedMedia"]//img/@src').getall()

        all_images = [str(img).strip() for img in all_images]

        # remove placeholders
        all_images = [img for img in all_images if not img.startswith("data:")]

        # remove wordpress thumbnails
        all_images = [img for img in all_images if "-150x150" not in img]

        # remove duplicates
        all_images = list(dict.fromkeys(all_images))

        product["primary_image_url"] = all_images[0] if all_images else ""
        product["image_urls"] = ";".join(all_images)
        # Prices
        price_text = response.xpath('(//p[@class="price"]//bdi)[2]/text()').get("").strip()
        product["current_price"] = price_text.replace("৳", "").replace(",", "").strip() if price_text else ""
        
        price_old = response.xpath('(//p[@class="price"]//bdi)[1]/text()').get("").strip()
        product["original_price"] = price_old.replace("৳", "").replace(",", "").strip() if price_old else ""

        # Meta
        product["category_name"] = response.xpath('(//nav[@class="woocommerce-breadcrumb"]/a)[last()]/text()').get("").strip()
        product['brand_name'] = response.xpath('(//li[contains(@class,"product-tag-item")])[1]/a/text()').get("").strip()
        product["brand_slug"] = product["brand_name"].lower().replace(" ", "-")
        product["review_count"] = "0"
        
        # Stock & Status
        stock_status = response.xpath('//p[contains(text(),"In stock")]/text()').get("").strip() 
        product["in_stock"] = "Yes" if "In stock" in stock_status else "No"
        product["seller_name"] = seller_name
        product["base_url"] = base_url
        product["is_active"] = "1" if product["in_stock"] == "Yes" else "0"
        # product["seller_sku"] = response.xpath('(//span[@class="sku"])[1]/text()').get("").strip() 
        overview_lines = response.xpath('(//div[@class="cg-accordion-item"])[1]//text()').getall()
        product["product_description"] = "".join([line.strip() for line in overview_lines if line.strip()])
        # Clean and join them with newlines to form a readable description block
        
        yield product
    else:
        logger.info("🗂️ Category/Nav page detected.")

    previous_height = await response.page.evaluate("document.body.scrollHeight")
    while True:
        await response.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await response.page.wait_for_timeout(1000)
        new_height = await response.page.evaluate("document.body.scrollHeight")
        if new_height == previous_height:
            break
        previous_height = new_height
    
    # --- 2. LINK FOLLOWING ---
    if not recurse:
        logger.info(f"🛑 Recursion is OFF. Not following links from: {response.url}")
        return

    # Use CSS Selectors for link harvesting. It handles multiple classes perfectly.
    target_selectors = [
        '//div[@class="woocommerce-loop-product__title"]/a/@href',
        '//a[@aria-label="Next"]/@href'
    ]

    valid_links = []

    for selector in target_selectors:
        valid_links.extend(response.xpath(selector).getall())
        
        
    unique_links = list(set(valid_links))
    
    logger.info(f"🔍 Found {len(unique_links)} target links on this page.")
    
    for link in unique_links:
        if any(ignored in link.lower() for ignored in['/account', '/cart', '/checkout', '/login', 'javascript:', 'tel:', 'mailto:', "question", "review"]):
            continue
        yield response.follow(link)