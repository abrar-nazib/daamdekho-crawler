import logging
import re
logger = logging.getLogger("Banglashoppers")

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

def parse(response, seller_name, base_url, recurse=True):
    """
    Standard entry point function expected by main.py
    """
    logger.info(f"🌍 Visiting URL: {response.url}")
    
    # --- 1. PRODUCT EXTRACTION ---
    # Check if it's a single product page (not a category page)
    is_product_page = is_product_page = bool(response.xpath('//div[@itemprop="sku"]/text()').get())
    
    if is_product_page:
        logger.info("🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()
        
        product["product_name"] = response.xpath('//h1[@class="page-title"]/span/text()').get("").strip()
        product["product_slug"] = product["product_name"].lower().replace(" ", "-")
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        product["primary_image_url"] = response.xpath('(//div[contains(@id,"MagicToolboxSelectors")]/a/@href)[1]').get("").strip()
        # product["primary_image_url"] = response.xpath('(//div[@data-media-type="image"]/picture/img/@src)[1]').get("").strip()
        # print(f"Primary Image URL: {product["primary_image_url"]}")
        all_images = response.xpath('(//div[contains(@id,"MagicToolboxSelectors")]/a/@href)').getall()
        product["image_urls"] = ";".join([img.strip() for img in all_images if img.strip()])
        # Prices
        price_text = response.xpath('(//div[@class="product-info-custom"]//span[@class="price"])[1]/text()').get("").strip()
        product["current_price"] = price_text.replace("Tk", "").replace(",", "").strip() if price_text else ""
        product["current_price"] = product["current_price"][3:]
        price_old = response.xpath('(//div[@class="product-info-custom"]//span[@class="price"])[2]/text()').get("").strip()
        product["original_price"] = price_old
        product["original_price"] = product["original_price"][3:]
        # Meta
        product["category_name"] = response.xpath('(//div[@class="breadcrumbs"]//li/a)[last()-1]/text()').get("").strip()
        product['brand_name'] = response.xpath('//div[@id="brand_name"]/text()').get("").strip()
        product["brand_slug"] = product["brand_name"].lower().replace(" ", "-")
        raw_count = response.xpath('//span[@itemprop="reviewCount"]/text()').get("")
        # Use regex to find all digits and join them (handles "4", "1,200", etc.)
        product["review_count"] = "".join(re.findall(r'\d+', raw_count))
        
        # Stock & Status
        stock_status = response.xpath('//span[contains(@class,"button__text")]/text()').get("").strip().lower()

        # product["in_stock"] = "Yes" if "add to cart" in stock_status else "No"
        product["in_stock"] = "Yes" 
        product["seller_name"] = seller_name
        product["base_url"] = base_url
        product["is_active"] = "1" if product["in_stock"] == "Yes" else "0"
        product["seller_sku"] = response.xpath('//div[@itemprop="sku"]/text()').get("").replace("SKU: ", "").strip()
        # product["seller_rating"] = response.xpath('//span[@id="product-review-average-rating"]/text()').get("").strip()
        
        overview_lines = response.xpath('//div[@id="description"]//text()').getall()
        # Clean and join them with newlines to form a readable description block
        product["product_description"] = "".join([line.strip() for line in overview_lines if line.strip()])
        print(f'Instock: {product["in_stock"]}')
        yield product
    else:
        logger.info("🗂️ Category/Nav page detected.")

    # --- 2. LINK FOLLOWING ---
    if not recurse:
        logger.info(f"🛑 Recursion is OFF. Not following links from: {response.url}")
        return

    # Use CSS Selectors for link harvesting. It handles multiple classes perfectly.
    target_selectors = [
        '//li[@class="item product product-item"]/div/div/a/@href',
        '(//a[@class="action  next"])[1]/@href'
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