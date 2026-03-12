import logging
import re

logger = logging.getLogger("KireiBD")

# Standard schema
BASE_PRODUCT = {
    "category_slug": "", "product_name": "", "product_slug": "", "seller_slug": "",
    "current_price": "", "seller_product_url": "", "brand_slug": "", "brand_name": "",
    "product_description": "", "model": "", "sku": "", "primary_image_url": "",
    "image_urls": "", "specifications": "", "attributes": "", "variation_type": "",
    "parent_product_slug": "", "original_price": "", "currency": "BDT", "in_stock": "",
    "stock_quantity": "", "seller_rating": "", "review_count": "", "shipping_cost": "",
    "free_shipping": "", "estimated_delivery_days": "", "seller_sku": "",
    "seller_product_name": "", "category_path": "", "category_name": "",
    "category_description": "", "seller_name": "", "base_url": "",
    "seller_country_code": "BD", "is_active": ""
}

def parse(response, seller_name, base_url, recurse=True):
    logger.info(f"🌍 Visiting URL: {response.url}")

    # --- 1. PRODUCT EXTRACTION LOGIC ---
    if "/product/" in response.url and response.css('div.post-content'):
        logger.info("🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()
        
        product["product_name"] = response.css('div.post-content h3.fw-medium::text').get("").strip()
        product["product_slug"] = response.url.split('/')[-1]
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        
        current_price_text = response.css('div.post-content__price h3.fw-medium::text').get("").strip()
        original_price_text = response.css('div.post-content__price del::text').get("").strip()
        product["current_price"] = current_price_text.replace("৳", "").replace(",", "").strip()
        product["original_price"] = original_price_text.replace("৳", "").replace(",", "").strip()

        # FIXED PRIMARY IMAGE SELECTOR
        product["primary_image_url"] = response.css('img[src*="cdn.kireibd.com/storage/all/"]::attr(src)').get("").strip()

        product["brand_name"] = response.css('div.post-content__brand a::text').get("").strip()
        brand_href = response.css('div.post-content__brand a::attr(href)').get("")
        if brand_href and "brand=" in brand_href:
            product["brand_slug"] = brand_href.split('brand=')[-1]

        sku_text = response.xpath('//div[@class="post-content__brand"]/strong[contains(text(), "Barcode")]/following-sibling::text()[1]').get()
        if sku_text:
            product["seller_sku"] = sku_text.replace(":", "").strip()

        categories = response.xpath('//span[contains(text(), "Category")]/following-sibling::a')
        if categories:
            last_category = categories[-1]
            product["category_name"] = last_category.xpath('.//text()').get("").replace(",", "").strip()
            cat_href = last_category.xpath('./@href').get("")
            if cat_href and "category=" in cat_href:
                product["category_slug"] = cat_href.split('category=')[-1]

        review_text = response.css('div.rating button::text').get("")
        if review_text:
            match = re.search(r'\d+', review_text)
            product["review_count"] = match.group(0) if match else "0"
        else:
            product["review_count"] = "0"

        stock_text = response.css('span.trk-btn--stock-out::text').get("").strip().lower()
        product["in_stock"] = "No" if "out of stock" in stock_text else "Yes"
        product["is_active"] = "1" if product["in_stock"] == "Yes" else "0"

        desc_lines = response.xpath('//div[contains(@class, "product-details__content")]//text()').getall()
        product["product_description"] = " ".join([t.strip() for t in desc_lines if t.strip()])

        product["seller_name"] = seller_name
        product["base_url"] = base_url

        yield product
        return # End here for product pages
    else:
        logger.info("🗂️ Listing/Nav page detected.")

    # --- 2. LINK FOLLOWING LOGIC ---
    if not recurse:
        logger.info(f"🛑 Recursion is OFF. Not following links.")
        return

    items = response.css('div.product__item')
    
    if items:
        logger.info(f"🔄 Scanning listing page... Found {len(items)} 'div.product__item' blocks.")
        
        # EXTENSIVE DEBUGGING: Print out the raw HTML of the first product block it found
        # so we can see exactly what the scraper sees.
        first_item_html = items[0].get()
        logger.info(f"🧐 RAW HTML of first item (First 300 chars): {first_item_html[:300]}")

        # Switched to bulletproof XPath for attributes
        thumb_links = response.xpath('//a[contains(@class, "product__item-thumb")]/@href').getall()
        title_links = response.xpath('//div[contains(@class, "product__item-content")]//h6/a/@href').getall()
        next_links = response.xpath('//a[@rel="next"]/@href').getall()
        
        logger.info(f"🔍 DEBUG Extract -> Thumbs: {len(thumb_links)}, Titles: {len(title_links)}, Pagination: {len(next_links)}")

        valid_links = thumb_links + title_links + next_links
        unique_links = list(set(valid_links))
        
        logger.info(f"🔍 Total unique target links: {len(unique_links)}")
        
        links_queued = 0
        for link in unique_links:
            if any(ignored in link.lower() for ignored in['/account', '/cart', '/checkout', '/login', 'javascript:', 'tel:', 'mailto:']):
                continue
            
            links_queued += 1
            yield response.follow(link)
            
        logger.info(f"✅ Added {links_queued} links to queue.")
    else:
        logger.warning("⚠️ No product grids found! Printing full page body snippet to debug.")
        safe_url = re.sub(r'[^\w\-_\.]', '_', response.url)
        debug_file_path = f"/app/data/debug/{safe_url}.html"
        with open(debug_file_path, "w", encoding="utf-8") as debug_file:
            debug_file.write(response.text)
        logger.info(f"📝 Full page HTML saved to: {debug_file_path}")