import logging
import json

logger = logging.getLogger("Ryans")

# Standard schema (Shared with StarTech to ensure CSV consistency)
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
    Parser for Ryans Computers
    """
    logger.info(f"🌍 Visiting URL: {response.url}")

    # --- 1. PRODUCT EXTRACTION LOGIC ---
    # We identify a product page by the presence of the <h1> title tag or the 'Add to Cart' form
    if response.css('h1[itemprop="name"]') or response.css('button.details-cart-btn'):
        logger.info("🛒 Product page detected! Extracting data...")
        product = BASE_PRODUCT.copy()
        
        # Basic Info
        product["product_name"] = response.css('h1[itemprop="name"]::text').get("").strip()
        product["product_slug"] = product["product_name"].lower().replace(" ", "-")
        product["seller_product_name"] = product["product_name"]
        product["seller_product_url"] = response.url
        
        # Meta Data (SKU)
        # HTML: <p>Product Id: <span>33.01.200.1448</span>
        product["seller_sku"] = response.css('p:contains("Product Id") span::text').get("").strip()
        
        # Prices
        # HTML: <span class="new-sp-text">Tk 68,000</span> (Special Price)
        # HTML: <span class="new-reg-text">Tk 73,780</span> (Regular Price)
        current_price_text = response.css('span.new-sp-text::text').get("").strip()
        original_price_text = response.css('span.new-reg-text::text').get("").strip()
        
        product["current_price"] = current_price_text.replace("Tk", "").replace(",", "").strip()
        product["original_price"] = original_price_text.replace("Tk", "").replace(",", "").strip()
        
        # Images
        # HTML: <img class="slideshow-items active" src="...">
        # We prefer the 'active' one or just the first one found in the main slider
        product["primary_image_url"] = response.css('img.slideshow-items::attr(src)').get("").strip()
        
        # Breadcrumbs / Category Info
        # HTML: <a href="...">All Laptop</a> -> <a href="...">Lenovo</a>
        # We skip Home (index 0). Index 1 is Category, Index 2 is Brand usually.
        breadcrumb_links = response.css('div.card-body div.d-flex a[itemtype="http://schema.org/Thing"]')
        if len(breadcrumb_links) > 1:
            product["category_name"] = breadcrumb_links[1].css('::text').get("").strip()
            # Slugify the category name
            product["category_slug"] = product["category_name"].lower().replace(" ", "-")
            
        if len(breadcrumb_links) > 2:
            product["brand_name"] = breadcrumb_links[-2].css('::text').get("").strip()
            product["brand_slug"] = product["brand_name"].lower().replace(" ", "-")

        # Description
        # We extract all list items inside the overview section
        overview_lines = response.css('div.overview ul.category-info li::text').getall()
        # Clean and join them with newlines to form a readable description block
        product["product_description"] = "".join([line.strip() for line in overview_lines if line.strip()])

        # Review Count
        # We count the number of review cards present on the page
        reviews = response.css('div.qna-body')
        product["review_count"] = str(len(reviews))

        # Stock Status (Checking for "Check Availability" button vs "Add to Cart")
        # If "Add to Cart" exists in the desktop buttons, it's likely in stock.
        # However, Ryans uses "Check Availability" modal for zones. 
        # We can default to Active=1 if the page loaded successfully, or look for specific stock meta tags.
        # HTML: <link itemprop="availability" href="https://schema.org/InStock">
        stock_status = response.css('link[itemprop="availability"]::attr(href)').get("")
        product["in_stock"] = "Yes" if "InStock" in stock_status else "No"
        product["is_active"] = "1" if product["in_stock"] == "Yes" else "0"

        product["seller_name"] = seller_name
        product["base_url"] = base_url

        yield product
    else:
        logger.info("🗂️ Listing/Nav page detected.")

    # Check if this is a listing page by looking for the product grid
    if response.css('div.category-single-product'):
        logger.info("🔄 Recursion is ON. Scanning listing page for products...")
        
        # A. Harvest Products from this page
        # HTML: <h4 class="product-name"><a href="...">...</a></h4>
        product_links = response.css('h4.product-name a::attr(href)').getall()
        unique_products = list(set(product_links))
        
        logger.info(f"🔍 Found {len(unique_products)} product links.")
        
        for link in unique_products:
            yield response.follow(link)

        # B. Handle Pagination (Next Button)
        # HTML: <li class="page-item"><a ... rel="next">›</a></li>
        next_page = response.css('li.page-item a[rel="next"]::attr(href)').get()
        if next_page:
            logger.info(f"➡️ Pagination found. Queuing Next Page: {next_page}")
            yield response.follow(next_page)
    else:
        logger.info("ℹ️ No product grid found on this page. No links followed.")