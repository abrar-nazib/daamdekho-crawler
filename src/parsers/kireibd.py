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
    # Grab all links with '/product/' in href
    product_links = response.xpath('//a[contains(@href, "/product/")]/@href').getall()
    unique_products = list(set(product_links))
    logger.info(f"🔍 Found {len(unique_products)} product links with '/product/'.")

    # Find next page link with ?category= matching current url's category
    current_category = None
    match = re.search(r'category=([^&]+)', response.url)
    if match:
        current_category = match.group(1)

    if current_category:
        next_links = response.xpath(f'//a[contains(@href, "?category={current_category}")]/@href').getall()
        unique_next_links = list(set(next_links))
        logger.info(f"🔍 Found {len(unique_next_links)} pagination links for category '{current_category}'.")
    
    # Combine and yield unique links
    all_links = set(unique_products)
    if len(all_links) == 0:
        logger.info("⚠️ No product links found on this page.")
        # Save the page content to a html file for debugging
        debug_filename = f"debug_{seller_name}_{response.url.split('/')[-1]}.html"
        with open(f"/app/data/debug/{debug_filename}", "wb") as f:
            f.write(response.body)
        logger.info(f"📄 Saved page content to {debug_filename} for inspection.")

    if current_category:
        all_links.update(unique_next_links)
    for link in all_links:
        absolute_url = response.urljoin(link)
        yield response.follow(absolute_url)
