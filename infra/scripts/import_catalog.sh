#!/bin/bash
# Product catalog import script
# Usage: ./import_catalog.sh <csv_file>

set -e

CSV_FILE=${1:-"catalog.csv"}

if [ ! -f "$CSV_FILE" ]; then
    echo "Error: CSV file not found: $CSV_FILE"
    echo "Usage: ./import_catalog.sh <csv_file>"
    echo ""
    echo "Expected CSV format:"
    echo "ean,name,brand,category,size"
    echo "4006381333931,Product Name,Brand,Category,500g"
    exit 1
fi

echo "📦 Importing product catalog from: $CSV_FILE"

poetry run python << EOF
import csv
import sys

from src.config import get_settings
from src.db import get_database
from src.db.repositories import ProductRepository
from src.models import ProductDoc

csv_file = "$CSV_FILE"

# Load settings
settings = get_settings()
print(f"Database: {settings.mongodb_database}")

# Connect to database
db = get_database()
product_repo = ProductRepository(db)

# Read CSV and import
imported = 0
updated = 0
errors = 0

with open(csv_file, 'r', encoding='utf-8') as f:
    reader = csv.DictReader(f)
    
    for row in reader:
        try:
            product = ProductDoc(
                ean=row['ean'].strip(),
                name=row.get('name', '').strip(),
                brand=row.get('brand', '').strip() or None,
                category=row.get('category', '').strip() or None,
                size=row.get('size', '').strip() or None,
                source='csv_import',
            )
            
            if product_repo.exists(product.ean):
                product_repo.update(product.ean, product.model_dump(exclude={'id', 'created_at'}))
                updated += 1
            else:
                product_repo.create(product)
                imported += 1
                
        except Exception as e:
            print(f"Error importing row: {row} - {e}")
            errors += 1

print(f"")
print(f"✅ Import complete!")
print(f"   New products: {imported}")
print(f"   Updated: {updated}")
print(f"   Errors: {errors}")
EOF
