import time
import os
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.support import expected_conditions as EC
import random
from lxml import html
import csv
import re

options = webdriver.ChromeOptions()
options.add_experimental_option("detach", True)  # Keeps browser open after script ends
options.add_experimental_option('excludeSwitches', ['enable-logging'])
driver = webdriver.Chrome(options=options)
driver.implicitly_wait(5)

input_file = "basic_output.csv"
output_file = "scraped_products.csv"

# CSV column headers (mirrors the original DB schema)
FIELDNAMES = [
    "title",
    "sale_price",
    "link",
    "price",
    "primary_image_url",
    "image_urls",
    "stock",
    "brand",
    "description",
    "rating",
    "reviews",
]


def init_csv(filepath: str):
    """Create the output CSV with headers if it doesn't already exist."""
    if not os.path.exists(filepath):
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        print(f"Output file '{filepath}' created with headers.")
    else:
        print(f"Output file '{filepath}' already exists — appending rows.")


def append_product(filepath: str, product: dict):
    """Append a single product row to the CSV file."""
    with open(filepath, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(product)
    print("Product saved to CSV.")


# ── Read input ──────────────────────────────────────────────────────────────
with open(input_file, newline="", encoding="utf-8") as f:
    rows = list(csv.reader(f))

init_csv(output_file)

# ── Scrape each row ──────────────────────────────────────────────────────────
for i in range(1, len(rows)):
    row = rows[i]
    link = row[2].strip()

    if not link or not link.startswith("http"):
        print(f"⚠ Got Invalid Link: {link}. Breaking the loop...")
        break

    product_info = {}
    product_info["title"] = row[0]
    product_info["sale_price"] = row[1]
    product_info["link"] = link

    try:
        driver.get(link)

        # Brand
        try:
            brand = driver.find_element(By.XPATH, '//span[@class="text-sm text-brand"]')
            product_info["brand"] = brand.text
        except Exception:
            product_info["brand"] = ""

        # Price (original / MRP)
        try:
            price_el = driver.find_element(
                By.XPATH,
                '//div[@class="text-sm whitespace-nowrap text-gray-500 line-through product_single_mrp_generate"]',
            )
            price = driver.execute_script(
                "return arguments[0].textContent.trim();", price_el
            )
            if price:
                clean_price = re.sub(r"[^\d]", "", price)
                product_info["price"] = clean_price if clean_price else product_info["sale_price"]
            else:
                product_info["price"] = product_info["sale_price"]
        except Exception:
            product_info["price"] = product_info["sale_price"]

        # Primary image URL
        try:
            img = driver.find_element(By.XPATH, '(//img[contains(@alt,"Image")])[1]')
            product_info["primary_image_url"] = img.get_attribute("src")
        except Exception:
            product_info["primary_image_url"] = ""

        # All image URLs (newline-separated)
        try:
            images = driver.find_elements(By.XPATH, '//img[contains(@alt,"Image")]')
            urls = list(dict.fromkeys(img.get_attribute("src") for img in images))
            product_info["image_urls"] = "\n".join(urls)
        except Exception:
            product_info["image_urls"] = ""

        # Stock availability
        try:
            driver.find_element(By.XPATH, '//span[contains(text(),"Add To Cart")]')
            product_info["stock"] = True
        except Exception:
            product_info["stock"] = False

        # Description
        try:
            description = driver.find_element(By.XPATH, '//div[@class="mt-4"]')
            product_info["description"] = description.text
        except Exception:
            product_info["description"] = ""

        # Rating
        try:
            rating_text = driver.find_element(
                By.XPATH, '//span[@class="text-gray-700"]'
            ).text
            product_info["rating"] = rating_text.split("/")[0].strip()
            print("Rating:", product_info["rating"])
        except Exception:
            product_info["rating"] = ""

        # Review count
        try:
            text = driver.find_element(
                By.XPATH, '//div[@class="text-sm text-gray-500"]'
            ).text
            product_info["reviews"] = text.split()[0]
            print("Reviews:", product_info["reviews"])
        except Exception:
            product_info["reviews"] = ""

    except Exception as e:
        print(f"❌ Error scraping {link}: {e}")
        # Fill missing fields with empty strings so the row is still written
        for field in FIELDNAMES:
            product_info.setdefault(field, "")

    append_product(output_file, product_info)

print("Done ✅ CSV updated successfully.")