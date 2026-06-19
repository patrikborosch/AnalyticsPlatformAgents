# Data Generation Plan

## Purpose

Generate synthetic evaluation datasets that skills will ingest, transform, and query. All data is deterministic so that expected results can be pre-computed.

## Datasets

### Dataset 1: `sales_transactions`
Simulates retail sales data. Used by SQL DW and Spark skills.

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| transaction_id | INT | Unique PK, sequential 1..N | 1 |
| customer_id | INT | FK, range 1..100 | 42 |
| product_id | INT | FK, range 1..50 | 7 |
| product_name | STRING | Deterministic from product_id | "Product_007" |
| category | STRING | 5 categories, round-robin | "Electronics" |
| quantity | INT | product_id mod 10 + 1 | 8 |
| unit_price | DECIMAL(10,2) | product_id * 9.99 | 69.93 |
| total_amount | DECIMAL(10,2) | quantity * unit_price | 559.44 |
| transaction_date | DATE | Sequential days from 2025-01-01 | 2025-01-01 |
| region | STRING | 4 regions, round-robin | "East" |

**Row counts:** 100 rows (small), 1000 rows (medium), 10000 rows (large)

**Generation rule (deterministic):**
```
For i in 1..N:
  transaction_id = i
  customer_id = (i % 100) + 1
  product_id = (i % 50) + 1
  product_name = f"Product_{product_id:03d}"
  category = ["Electronics","Clothing","Food","Home","Sports"][i % 5]
  quantity = (product_id % 10) + 1
  unit_price = round(product_id * 9.99, 2)
  total_amount = round(quantity * unit_price, 2)
  transaction_date = date(2025,1,1) + timedelta(days=(i-1) % 365)
  region = ["East","West","North","South"][i % 4]
```

### Dataset 2: `customers`
Dimension table for join testing.

| Column | Type | Description |
|--------|------|-------------|
| customer_id | INT | PK, 1..100 |
| customer_name | STRING | "Customer_{id:03d}" |
| email | STRING | "customer{id}@example.com" |
| signup_date | DATE | 2024-01-01 + (id-1) days |
| tier | STRING | ["Bronze","Silver","Gold"][id % 3] |

**Row count:** 100 rows

### Dataset 3: `products`
Dimension table for join testing.

| Column | Type | Description |
|--------|------|-------------|
| product_id | INT | PK, 1..50 |
| product_name | STRING | "Product_{id:03d}" |
| category | STRING | Same 5 categories |
| base_price | DECIMAL(10,2) | id * 9.99 |

**Row count:** 50 rows

### Dataset 4: `sensor_readings` (JSON/nested)
For Spark consumption testing with semi-structured data.

```json
{
  "device_id": "sensor_001",
  "timestamp": "2025-01-01T00:00:00Z",
  "readings": {
    "temperature": 22.5,
    "humidity": 45.0,
    "pressure": 1013.25
  },
  "tags": ["indoor", "floor1"]
}
```

**Row count:** 500 records, 10 devices, 50 readings each.

## Pre-computed Expected Results (Golden Answers)

These are saved in `evalsets/expected-results/` and used for verification.

| Query | Expected Result |
|-------|----------------|
| `SELECT COUNT(*) FROM sales_transactions` (small) | 100 |
| `SELECT SUM(total_amount) FROM sales_transactions` (small) | Pre-computed decimal |
| `SELECT COUNT(*) FROM sales_transactions WHERE category='Electronics'` (small) | 20 |
| `SELECT region, COUNT(*) FROM sales_transactions GROUP BY region` (small) | East:25, West:25, North:25, South:25 |
| `SELECT c.tier, SUM(s.total_amount) FROM sales_transactions s JOIN customers c ON s.customer_id = c.customer_id GROUP BY c.tier` | Pre-computed per tier |

## File Formats

| Format | Used By | Location |
|--------|---------|----------|
| CSV | SQL DW COPY INTO, general ingestion | `evalsets/data-generation/*.csv` |
| JSON | Spark semi-structured processing | `evalsets/data-generation/*.json` |
| Parquet spec | Spark native format | Generated via PySpark during eval |

## Generation Script

The evaluating agent should generate data using Python:

```python
import csv, json
from datetime import date, timedelta

def generate_sales(n):
    rows = []
    categories = ["Electronics","Clothing","Food","Home","Sports"]
    regions = ["East","West","North","South"]
    for i in range(1, n+1):
        pid = (i % 50) + 1
        qty = (pid % 10) + 1
        up = round(pid * 9.99, 2)
        rows.append({
            "transaction_id": i,
            "customer_id": (i % 100) + 1,
            "product_id": pid,
            "product_name": f"Product_{pid:03d}",
            "category": categories[i % 5],
            "quantity": qty,
            "unit_price": up,
            "total_amount": round(qty * up, 2),
            "transaction_date": str(date(2025,1,1) + timedelta(days=(i-1) % 365)),
            "region": regions[i % 4]
        })
    return rows
```
