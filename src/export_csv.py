import sqlite3
import csv
import os
import sys

def export_to_csv(seller_name):
    db_path = f"/app/data/databases/{seller_name}.db"
    csv_path = f"/app/data/csvs/{seller_name}_products.csv"
    
    if not os.path.exists(db_path):
        print(f"Database not found: {db_path}")
        return

    print(f"Exporting {seller_name} to CSV...")
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM products")
    rows = cursor.fetchall()
    
    if not rows:
        print("Database is empty.")
        conn.close()
        return

    # Get column names
    col_names = [description[0] for description in cursor.description]

    with open(csv_path, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(col_names)
        writer.writerows(rows)

    print(f"✅ Exported {len(rows)} rows to {csv_path}")
    conn.close()

if __name__ == "__main__":
    # Usage: python src/export_csv.py StarTech
    if len(sys.argv) > 1:
        export_to_csv(sys.argv[1])
    else:
        print("Please provide SELLER_NAME as argument.")