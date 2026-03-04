import sqlite3
import logging
import os

logger = logging.getLogger("Database")

class ProductDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self.cursor = None
        self._init_db()

    def _init_db(self):
        """Initialize connection and create table if not exists"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row  # Allows accessing columns by name
        self.cursor = self.conn.cursor()
        
        # Enable WAL mode for better concurrency (optional but recommended)
        self.cursor.execute("PRAGMA journal_mode=WAL;")
        
        # Create table. We use seller_product_url as the PRIMARY KEY.
        # We store everything as TEXT for simplicity, but you can refine types later.
        create_table_sql = """
        CREATE TABLE IF NOT EXISTS products (
            seller_product_url TEXT PRIMARY KEY,
            product_name TEXT,
            category_slug TEXT,
            product_slug TEXT,
            seller_slug TEXT,
            current_price TEXT,
            brand_slug TEXT,
            brand_name TEXT,
            product_description TEXT,
            model TEXT,
            sku TEXT,
            primary_image_url TEXT,
            image_urls TEXT,
            specifications TEXT,
            attributes TEXT,
            variation_type TEXT,
            parent_product_slug TEXT,
            original_price TEXT,
            currency TEXT,
            in_stock TEXT,
            stock_quantity TEXT,
            seller_rating TEXT,
            review_count TEXT,
            shipping_cost TEXT,
            free_shipping TEXT,
            estimated_delivery_days TEXT,
            seller_sku TEXT,
            seller_product_name TEXT,
            category_path TEXT,
            category_name TEXT,
            category_description TEXT,
            seller_name TEXT,
            base_url TEXT,
            seller_country_code TEXT,
            is_active TEXT,
            last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
        self.cursor.execute(create_table_sql)
        self.conn.commit()

    def get_product(self, url):
        """Fetch a single product by URL to compare data"""
        try:
            self.cursor.execute("SELECT * FROM products WHERE seller_product_url = ?", (url,))
            row = self.cursor.fetchone()
            if row:
                return dict(row)
            return None
        except sqlite3.Error as e:
            logger.error(f"DB Read Error: {e}")
            return None

    def upsert_product(self, product_data):
        """Insert a new product or Replace existing one"""
        keys = list(product_data.keys())
        values = list(product_data.values())
        
        # specific SQL syntax for "Insert or Update"
        placeholders = ", ".join(["?"] * len(keys))
        columns = ", ".join(keys)
        
        # This SQL will update the row if the URL already exists
        sql = f"""
        INSERT OR REPLACE INTO products ({columns}, last_updated)
        VALUES ({placeholders}, CURRENT_TIMESTAMP)
        """
        
        try:
            self.cursor.execute(sql, values)
            self.conn.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"DB Write Error: {e}")
            return False

    def close(self):
        if self.conn:
            self.conn.close()