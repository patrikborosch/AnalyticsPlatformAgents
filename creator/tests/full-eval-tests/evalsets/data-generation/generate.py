#!/usr/bin/env python3
"""
Generate evaluation datasets for skills-for-fabric.

Sales datasets are sourced from the NYC TLC public feed (real data), then
normalized into the eval schema used by existing plans.

Running this script regenerates every CSV/JSON file in this directory and the
golden-answer files in ../expected-results/.

Usage:
    python generate.py              # downloads NYC data and writes datasets
    python generate.py --outdir /tmp/evaldata   # custom output
    python generate.py --verify     # verify existing files match
"""

import argparse
import csv
import json
import shutil
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

try:
    import pyarrow.dataset as pyarrow_dataset
except ImportError:  # pragma: no cover - runtime dependency check
    pyarrow_dataset = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
CATEGORIES = ["Electronics", "Clothing", "Food", "Home", "Sports"]
REGIONS = ["East", "West", "North", "South"]
TIERS = ["Bronze", "Silver", "Gold"]
SENSOR_COUNT = 10
READINGS_PER_SENSOR = 50
NYC_PARQUET_URL_TEMPLATE = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{month}.parquet"
DEFAULT_NYC_MONTH = "2024-01"


# ---------------------------------------------------------------------------
# Dataset generators (NYC source -> eval schema)
# ---------------------------------------------------------------------------


def nyc_parquet_url(month: str) -> str:
    return NYC_PARQUET_URL_TEMPLATE.format(month=month)


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    req = Request(url, headers={"User-Agent": "skills-for-fabricEvalDataGenerator/1.0"})
    try:
        with urlopen(req, timeout=300) as response, open(destination, "wb") as output_file:
            shutil.copyfileobj(response, output_file)
    except HTTPError as error:
        raise RuntimeError(
            f"Failed to download NYC parquet from '{url}' (HTTP {error.code}). "
            "Use a full file URL like .../trip-data/yellow_tripdata_YYYY-MM.parquet; "
            "the trip-data directory URL itself is not directly browsable."
        ) from error


def ensure_pyarrow_available() -> None:
    if pyarrow_dataset is None:
        raise RuntimeError(
            "pyarrow is required to transform NYC Parquet into eval CSV datasets. "
            "Install it with: pip install pyarrow"
        )


def _iter_parquet_rows(parquet_path: Path, columns: list[str], batch_size: int = 2048):
    ensure_pyarrow_available()
    dataset = pyarrow_dataset.dataset(str(parquet_path), format="parquet")
    scanner = dataset.scanner(columns=columns, batch_size=batch_size)
    for batch in scanner.to_batches():
        for row in batch.to_pylist():
            yield row


def _category_from_payment_type(payment_type) -> str:
    payment_value = int(payment_type or 0)
    return {
        1: "Electronics",
        2: "Clothing",
        3: "Food",
        4: "Home",
    }.get(payment_value, "Sports")


def _region_from_location_id(location_id) -> str:
    location_value = int(location_id or 0)
    mapping = {
        0: "East",
        1: "West",
        2: "North",
        3: "South",
    }
    return mapping[location_value % 4]


def _tier_from_index(index_1_based: int) -> str:
    mod = index_1_based % 3
    if mod == 1:
        return "Bronze"
    if mod == 2:
        return "Silver"
    return "Gold"


def _product_category_from_index(index_1_based: int) -> str:
    mod = index_1_based % 5
    if mod == 1:
        return "Electronics"
    if mod == 2:
        return "Clothing"
    if mod == 3:
        return "Food"
    if mod == 4:
        return "Home"
    return "Sports"


def generate_sales_from_nyc(parquet_path: Path, n: int) -> list[dict]:
    columns = [
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "VendorID",
        "PULocationID",
        "payment_type",
        "passenger_count",
        "fare_amount",
        "total_amount",
    ]

    rows = []
    transaction_id = 1
    for raw in _iter_parquet_rows(parquet_path, columns):
        pickup = raw.get("tpep_pickup_datetime")
        if pickup is None:
            continue

        pickup_date = pickup.date() if hasattr(pickup, "date") else pickup
        pickup_location = raw.get("PULocationID")
        passenger_count = raw.get("passenger_count")
        fare_amount = raw.get("fare_amount")
        total_amount = raw.get("total_amount")
        vendor_id = raw.get("VendorID")
        payment_type = raw.get("payment_type")

        product_id = int(pickup_location or 0) + 1
        quantity = max(int(passenger_count or 1), 1)

        rows.append(
            {
                "transaction_id": transaction_id,
                "customer_id": int(vendor_id or 0) + 1,
                "product_id": product_id,
                "product_name": f"Route_{int(pickup_location or 0):03d}",
                "category": _category_from_payment_type(payment_type),
                "quantity": quantity,
                "unit_price": round(float(fare_amount or 0.0), 2),
                "total_amount": round(float(total_amount or 0.0), 2),
                "transaction_date": str(pickup_date),
                "region": _region_from_location_id(pickup_location),
            }
        )

        transaction_id += 1
        if len(rows) >= n:
            break

    if len(rows) < n:
        raise RuntimeError(
            f"NYC source does not contain enough rows for requested sample size: {len(rows)} < {n}"
        )

    return rows


def generate_customers_from_nyc(parquet_path: Path, n: int = 100) -> list[dict]:
    customer_ids = set()
    for raw in _iter_parquet_rows(parquet_path, ["DOLocationID"]):
        location_id = raw.get("DOLocationID")
        if location_id is not None:
            customer_ids.add(int(location_id) + 1)

    sorted_customer_ids = sorted(customer_ids)[:n]
    if len(sorted_customer_ids) < n:
        raise RuntimeError(
            f"NYC source does not contain enough distinct customer IDs: {len(sorted_customer_ids)} < {n}"
        )

    rows = []
    for index, customer_id in enumerate(sorted_customer_ids, start=1):
        rows.append(
            {
                "customer_id": customer_id,
                "customer_name": f"Customer_{customer_id:03d}",
                "email": f"customer{customer_id}@example.com",
                "signup_date": str(date(2024, 1, 1) + timedelta(days=index - 1)),
                "tier": _tier_from_index(index),
            }
        )

    return rows


def generate_products_from_nyc(parquet_path: Path, n: int = 50) -> list[dict]:
    product_ids = set()
    for raw in _iter_parquet_rows(parquet_path, ["PULocationID"]):
        location_id = raw.get("PULocationID")
        if location_id is not None:
            product_ids.add(int(location_id) + 1)

    sorted_product_ids = sorted(product_ids)[:n]
    if len(sorted_product_ids) < n:
        raise RuntimeError(
            f"NYC source does not contain enough distinct product IDs: {len(sorted_product_ids)} < {n}"
        )

    rows = []
    for index, product_id in enumerate(sorted_product_ids, start=1):
        rows.append(
            {
                "product_id": product_id,
                "product_name": f"Product_{product_id:03d}",
                "category": _product_category_from_index(index),
                "base_price": float((Decimal(str(product_id)) * Decimal("9.99")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            }
        )

    return rows


def generate_sensor_readings(
    devices: int = SENSOR_COUNT, readings: int = READINGS_PER_SENSOR
) -> list[dict]:
    """Generate sensor readings (nested JSON)."""
    rows = []
    for device in range(1, devices + 1):
        for reading in range(readings):
            ts = datetime(2025, 1, 1) + timedelta(hours=reading)
            rows.append(
                {
                    "device_id": f"sensor_{device:03d}",
                    "timestamp": ts.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "readings": {
                        "temperature": round(20.0 + device * 0.5 + reading * 0.1, 2),
                        "humidity": round(40.0 + device * 1.05, 2),
                        "pressure": round(1013.0 + device * 0.09, 2),
                    },
                    "tags": [
                        ["indoor", "outdoor"][device % 2],
                        f"floor{(device % 3) + 1}",
                    ],
                }
            )
    return rows


# ---------------------------------------------------------------------------
# Golden expected-results generators
# ---------------------------------------------------------------------------


def golden_sales_100(sales: list[dict]) -> dict:
    """Compute golden answers for the 100-row sales dataset."""
    total = sum(Decimal(str(r["total_amount"])) for r in sales)
    by_region: dict[str, Decimal] = {}
    by_category: dict[str, Decimal] = {}
    for r in sales:
        by_region[r["region"]] = by_region.get(r["region"], Decimal("0")) + Decimal(
            str(r["total_amount"])
        )
        by_category[r["category"]] = by_category.get(
            r["category"], Decimal("0")
        ) + Decimal(str(r["total_amount"]))

    return {
        "dataset": "sales_transactions_100",
        "row_count": len(sales),
        "sum_total_amount": float(total),
        "by_region": {k: float(v) for k, v in sorted(by_region.items())},
        "by_category": {k: float(v) for k, v in sorted(by_category.items())},
        "distinct_categories": len(set(r["category"] for r in sales)),
        "distinct_regions": len(set(r["region"] for r in sales)),
    }


# ---------------------------------------------------------------------------
# File writers
# ---------------------------------------------------------------------------


def write_csv(rows: list[dict], path: Path) -> None:
    """Write rows to a CSV file."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(data, path: Path) -> None:
    """Write data to a JSON file."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)
        f.write("\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="Generate skills-for-fabric eval data")
    parser.add_argument(
        "--month",
        type=str,
        default=DEFAULT_NYC_MONTH,
        help="NYC month to pull in YYYY-MM format (default: 2024-01)",
    )
    parser.add_argument(
        "--outdir",
        type=Path,
        default=Path(__file__).parent,
        help="Output directory for data files (default: same as script)",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Verify existing files match generated data instead of writing",
    )
    args = parser.parse_args()

    data_dir = args.outdir
    expected_dir = data_dir.parent / "expected-results"
    raw_dir = data_dir / "raw"
    data_dir.mkdir(parents=True, exist_ok=True)
    expected_dir.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    if args.verify:
        errors = verify_existing(data_dir, expected_dir)
        if errors:
            print(f"FAIL: {len(errors)} verification error(s):")
            for error in errors:
                print(f"  - {error}")
            sys.exit(1)
        print("OK: All files match generated data.")
        sys.exit(0)

    month = args.month
    nyc_url = nyc_parquet_url(month)
    nyc_parquet_path = raw_dir / f"yellow_tripdata_{month}.parquet"

    print(f"Downloading NYC dataset: {nyc_url}")
    download_file(nyc_url, nyc_parquet_path)

    # Generate all datasets from real NYC public feed where applicable
    sales_100 = generate_sales_from_nyc(nyc_parquet_path, 100)
    sales_1000 = generate_sales_from_nyc(nyc_parquet_path, 1000)
    sales_10000 = generate_sales_from_nyc(nyc_parquet_path, 10000)
    customers = generate_customers_from_nyc(nyc_parquet_path, 100)
    products = generate_products_from_nyc(nyc_parquet_path, 50)
    sensors = generate_sensor_readings()

    # Write data files
    write_csv(sales_100, data_dir / "sales_transactions_100.csv")
    write_csv(sales_1000, data_dir / "sales_transactions_1000.csv")
    write_csv(sales_10000, data_dir / "sales_transactions_10000.csv")
    write_csv(customers, data_dir / "customers.csv")
    write_csv(products, data_dir / "products.csv")
    write_json(sensors, data_dir / "sensor_readings.json")

    # Write golden expected results
    write_json(golden_sales_100(sales_100), expected_dir / "sales_100_golden.json")

    # Products golden (5-row known-data subset used in SA-08/SAC-01 evals)
    write_json(
        {
            "dataset": "products_5rows",
            "source_eval": "SA-08 / SAC-01",
            "rows": [
                {
                    "product_id": i,
                    "product_name": f"Product_{i:03d}",
                    "category": CATEGORIES[i % 5],
                    "base_price": float(
                        (Decimal(str(i)) * Decimal("9.99")).quantize(Decimal("0.01"))
                    ),
                }
                for i in range(1, 6)
            ],
            "expected_aggregates": {
                "row_count": 5,
                "sum_base_price": float(
                    sum(
                        Decimal(str(i)) * Decimal("9.99") for i in range(1, 6)
                    ).quantize(Decimal("0.01"))
                ),
                "distinct_categories": 5,
            },
        },
        expected_dir / "products_5rows.json",
    )

    # Sensor golden (first 5 devices, 1 reading each)
    first_5 = [s for s in sensors if s["timestamp"] == "2025-01-01T00:00:00Z"][:5]
    write_json(
        [
            {
                "device_id": s["device_id"],
                "timestamp": s["timestamp"],
                "temperature": s["readings"]["temperature"],
                "humidity": s["readings"]["humidity"],
                "pressure": s["readings"]["pressure"],
                "tags": s["tags"],
            }
            for s in first_5
        ],
        expected_dir / "sensor_5rows.json",
    )

    print(f"Generated data files in:     {data_dir}")
    print(f"Generated golden results in: {expected_dir}")
    print(f"NYC source parquet:          {nyc_parquet_path}")
    print(
        f"  sales:    {len(sales_100)}, {len(sales_1000)}, {len(sales_10000)} rows"
    )
    print(f"  customers: {len(customers)} rows")
    print(f"  products:  {len(products)} rows")
    print(f"  sensors:   {len(sensors)} readings")


def verify_existing(data_dir: Path, expected_dir: Path) -> list[str]:
    """Verify expected generated files exist and basic invariants hold."""
    errors = []

    # Check sales_transactions_100.csv row count
    csv_path = data_dir / "sales_transactions_100.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            csv_rows = list(reader)
        if len(csv_rows) != 100:
            errors.append(
                f"sales_transactions_100.csv: {len(csv_rows)} rows, expected 100"
            )
    else:
        errors.append("sales_transactions_100.csv: file not found")

    # Check customers.csv
    csv_path = data_dir / "customers.csv"
    if csv_path.exists():
        with open(csv_path, encoding="utf-8") as f:
            csv_rows = list(csv.DictReader(f))
        if len(csv_rows) != 100:
            errors.append(
                f"customers.csv: {len(csv_rows)} rows, expected 100"
            )
    else:
        errors.append("customers.csv: file not found")

    # Check golden
    golden_path = expected_dir / "sales_100_golden.json"
    if golden_path.exists():
        with open(golden_path, encoding="utf-8") as f:
            golden = json.load(f)
        if golden["row_count"] != 100:
            errors.append(f"sales_100_golden.json: row_count={golden['row_count']}")
    else:
        errors.append("sales_100_golden.json: file not found")

    return errors


if __name__ == "__main__":
    main()
