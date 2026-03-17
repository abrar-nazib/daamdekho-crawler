# Selenium Product Scraper

A two-step Selenium-based product scraper that collects product URLs from listing pages (with infinite scroll support) and then scrapes product details from each URL. Parsers are seller-specific and plug in automatically by name.

---

## Project Structure

```
root/
├── .env                          ← seller config (SELLER_NAME, TARGET_DOMAIN)
├── link_extraction.py            ← Step 1: collect product URLs
├── main.py                       ← Step 2: scrape product details
├── failed_urls.txt               ← auto-created, logs failed URLs with reasons
├── data/
│   ├── {SELLER_NAME}_entrypoints.csv   ← your input: category/listing page URLs
│   ├── {SELLER_NAME}_urls.csv          ← output of link_extraction.py
│   └── {SELLER_NAME}_products.csv      ← output of main.py
└── parsers/
    ├── __init__.py
    └── Herlan.py                 ← XPath extraction logic for herlan.com
```

---

## Setup

**1. Activate the virtual environment**

Run this in the root folder of your terminal:
```bash
venv\Scripts\activate
```

**2. Install dependencies**
```bash
pip install selenium lxml python-dotenv
```

**2. Configure `.env`**
```dotenv
SELLER_NAME   = Herlan
TARGET_DOMAIN = herlan.com
```

**3. Add entry points**

Create `data/{SELLER_NAME}_entrypoints.csv` with one category/listing URL per row:
```
https://www.herlan.com/product-category/makeup/
https://www.herlan.com/product-category/skincare/
```

---

## Usage

Run the two steps in order:

```bash
# Step 1 — collect product URLs
python link_extraction.py

# Step 2 — scrape product details
python main.py
```

Both scripts open a visible Chrome browser so you can watch them work.  
`main.py` supports resume — if interrupted, re-running it skips already-scraped URLs.

---

## Adding a New Seller

1. Copy `parsers/Herlan.py` → `parsers/{NewSeller}.py`
2. Update `PRODUCT_LINK_XPATH` in `link_extraction.py` and the XPath expressions in `parse()` to match the new site
3. Update `.env` with the new `SELLER_NAME` and `TARGET_DOMAIN`
4. Add entry points to `data/{NewSeller}_entrypoints.csv`
5. Run the two steps above — nothing else needs changing

---

## Output Fields

Each row in `{SELLER_NAME}_products.csv` contains:

| Field | Notes |
|---|---|
| `product_name`, `product_slug` | slug is auto-derived |
| `current_price`, `original_price`, `currency` | |
| `primary_image_url`, `image_urls` | multiple images semicolon-separated |
| `brand_name`, `brand_slug` | slug is auto-derived |
| `category_name`, `category_slug`, `category_path` | slug is auto-derived |
| `product_description` | |
| `in_stock`, `is_active`, `stock_quantity` | `is_active` auto-derived from `in_stock` |
| `seller_name`, `seller_slug`, `seller_product_url` | |
| `sku`, `model`, `specifications`, `attributes` | blank if not on site |
| `review_count`, `seller_rating` | |
| `shipping_cost`, `free_shipping`, `estimated_delivery_days` | |
| `seller_country_code`, `base_url` | |