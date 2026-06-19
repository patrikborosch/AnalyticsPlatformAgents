#!/usr/bin/env python3
"""
Generate a deterministic sample of NYC TLC yellow taxi data for smoke tests.

Downloads a single month of public NYC TLC data, extracts a fixed 10,000-row
sample, and writes it as CSV + computes the expected test answers.

Usage:
    python generate_nyctlc_sample.py                     # default: 2024-01, 10000 rows
    python generate_nyctlc_sample.py --month 2024-06     # different month
    python generate_nyctlc_sample.py --rows 5000         # fewer rows
    python generate_nyctlc_sample.py --verify            # check existing files match

Prerequisites:
    pip install pyarrow
"""

import argparse
import csv
import json
import shutil
import ssl
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

try:
    import certifi
    _SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CONTEXT = None

try:
    import pyarrow.parquet as pq
except ImportError:
    pq = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NYC_PARQUET_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{month}.parquet"
DEFAULT_MONTH = "2024-01"
DEFAULT_ROWS = 10_000

# Columns to keep (standard NYC TLC yellow taxi schema)
COLUMNS = [
    "VendorID",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "RatecodeID",
    "store_and_fwd_flag",
    "PULocationID",
    "DOLocationID",
    "payment_type",
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "total_amount",
    "congestion_surcharge",
    "Airport_fee",
]

# CSV output columns (snake_case for lakehouse compatibility)
CSV_COLUMNS = [
    "vendor_id",
    "tpep_pickup_datetime",
    "tpep_dropoff_datetime",
    "passenger_count",
    "trip_distance",
    "ratecode_id",
    "store_and_fwd_flag",
    "pu_location_id",
    "do_location_id",
    "payment_type",
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "total_amount",
    "congestion_surcharge",
    "airport_fee",
]


def download_parquet(month: str, dest: Path) -> None:
    """Download NYC TLC parquet file for a given month."""
    url = NYC_PARQUET_URL.format(month=month)
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} ...")
    req = Request(url, headers={"User-Agent": "skills-for-fabric-testdata/1.0"})
    try:
        ctx = _SSL_CONTEXT
        with urlopen(req, timeout=300, context=ctx) as resp, open(dest, "wb") as f:
            shutil.copyfileobj(resp, f)
    except URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            print("  SSL verification failed, retrying without verification...")
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            with urlopen(req, timeout=300, context=ctx) as resp, open(dest, "wb") as f:
                shutil.copyfileobj(resp, f)
        else:
            raise
    except HTTPError as e:
        raise RuntimeError(f"Download failed (HTTP {e.code}): {url}") from e
    print(f"  -> saved to {dest} ({dest.stat().st_size / 1024 / 1024:.1f} MB)")


def extract_sample(parquet_path: Path, n: int) -> list[dict]:
    """Extract first n valid rows from the parquet file."""
    if pq is None:
        raise RuntimeError("pyarrow is required: pip install pyarrow")

    table = pq.read_table(str(parquet_path), columns=COLUMNS)
    df = table.to_pydict()
    total = len(df[COLUMNS[0]])

    rows = []
    for i in range(min(total, n * 2)):  # scan up to 2x to skip nulls
        if len(rows) >= n:
            break

        vendor_id = df["VendorID"][i]
        trip_distance = df["trip_distance"][i]

        # Skip rows with null vendor or distance (they'd break aggregation queries)
        if vendor_id is None or trip_distance is None:
            continue

        row = {}
        for orig_col, csv_col in zip(COLUMNS, CSV_COLUMNS):
            val = df[orig_col][i]
            if hasattr(val, "isoformat"):
                val = val.isoformat()
            elif isinstance(val, (float, Decimal)):
                val = round(float(val), 2)
            elif val is None:
                val = ""
            row[csv_col] = val

        rows.append(row)

    if len(rows) < n:
        raise RuntimeError(f"Only {len(rows)} valid rows found, need {n}")

    print(f"  -> extracted {len(rows)} rows from {total} total")
    return rows


def compute_expected_values(rows: list[dict]) -> dict:
    """Compute the expected test answers from the sample."""
    row_count = len(rows)

    # Average trip distance by vendor_id
    vendor_distances: dict[int, list[float]] = {}
    for r in rows:
        vid = int(r["vendor_id"])
        dist = float(r["trip_distance"])
        vendor_distances.setdefault(vid, []).append(dist)

    avg_by_vendor = {}
    for vid in sorted(vendor_distances.keys()):
        distances = vendor_distances[vid]
        avg = sum(distances) / len(distances)
        avg_by_vendor[str(vid)] = round(avg, 2)

    return {
        "description": "Expected smoke test values for nyctlc sample dataset",
        "source_month": None,  # filled by caller
        "row_count": row_count,
        "row_count_formatted": f"{row_count:,}",
        "avg_trip_distance_by_vendor": avg_by_vendor,
    }


def write_csv(rows: list[dict], path: Path) -> None:
    """Write rows to CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"  -> wrote {path} ({len(rows)} rows)")


def write_json(data: dict, path: Path) -> None:
    """Write dict to JSON."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")
    print(f"  -> wrote {path}")


def verify(data_dir: Path) -> list[str]:
    """Verify existing files can be loaded and have expected structure."""
    errors = []
    csv_path = data_dir / "nyctlc_sample.csv"
    json_path = data_dir / "nyctlc_expected.json"

    if not csv_path.exists():
        errors.append(f"Missing: {csv_path}")
    else:
        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            if not rows:
                errors.append("CSV is empty")
            missing_cols = {"vendor_id", "trip_distance"} - set(reader.fieldnames or [])
            if missing_cols:
                errors.append(f"CSV missing columns: {missing_cols}")

    if not json_path.exists():
        errors.append(f"Missing: {json_path}")
    else:
        with open(json_path, encoding="utf-8") as f:
            expected = json.load(f)
            if "row_count" not in expected:
                errors.append("JSON missing row_count")
            if "avg_trip_distance_by_vendor" not in expected:
                errors.append("JSON missing avg_trip_distance_by_vendor")

    return errors


def main():
    parser = argparse.ArgumentParser(description="Generate NYC TLC sample for smoke tests")
    parser.add_argument("--month", default=DEFAULT_MONTH, help="NYC TLC month (YYYY-MM)")
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="Sample size")
    parser.add_argument("--verify", action="store_true", help="Verify existing files")
    args = parser.parse_args()

    data_dir = Path(__file__).parent

    if args.verify:
        errors = verify(data_dir)
        if errors:
            print(f"FAIL: {len(errors)} error(s):")
            for e in errors:
                print(f"  - {e}")
            sys.exit(1)
        print("OK: All files valid.")
        sys.exit(0)

    # Download
    raw_dir = data_dir / "raw"
    parquet_path = raw_dir / f"yellow_tripdata_{args.month}.parquet"
    if not parquet_path.exists():
        download_parquet(args.month, parquet_path)
    else:
        print(f"Using cached {parquet_path}")

    # Extract sample
    print(f"Extracting {args.rows} rows...")
    rows = extract_sample(parquet_path, args.rows)

    # Write CSV
    write_csv(rows, data_dir / "nyctlc_sample.csv")

    # Compute and write expected values
    expected = compute_expected_values(rows)
    expected["source_month"] = args.month
    write_json(expected, data_dir / "nyctlc_expected.json")

    print("\nDone! Next steps:")
    print("  1. Review nyctlc_expected.json for the new expected test values")
    print("  2. Update tests/tests.json with these values")
    print("  3. Run the setup script to create the lakehouse and load the data")


if __name__ == "__main__":
    main()
