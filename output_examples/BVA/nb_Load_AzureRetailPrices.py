"""
nb_Load_AzureRetailPrices
Fetches all Azure Retail Prices from the public REST API and writes to
tbl_AzureRetailPrices in the default Lakehouse (BVAData) as a Delta table
with overwrite mode. Designed to be repeatable.
"""
import requests
from pyspark.sql.types import StructType, StructField, StringType, FloatType, BooleanType

schema = StructType([
    StructField("currencyCode", StringType(), True),
    StructField("tierMinimumUnits", FloatType(), True),
    StructField("retailPrice", FloatType(), True),
    StructField("unitPrice", FloatType(), True),
    StructField("armRegionName", StringType(), True),
    StructField("location", StringType(), True),
    StructField("effectiveStartDate", StringType(), True),
    StructField("meterId", StringType(), True),
    StructField("meterName", StringType(), True),
    StructField("productId", StringType(), True),
    StructField("skuId", StringType(), True),
    StructField("productName", StringType(), True),
    StructField("skuName", StringType(), True),
    StructField("serviceName", StringType(), True),
    StructField("serviceId", StringType(), True),
    StructField("serviceFamily", StringType(), True),
    StructField("unitOfMeasure", StringType(), True),
    StructField("type", StringType(), True),
    StructField("isPrimaryMeterRegion", BooleanType(), True),
    StructField("armSkuName", StringType(), True),
    StructField("reservationTerm", StringType(), True)
])

api_url = "https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview"
all_items = []
page_count = 0
next_page = api_url

print("Starting Azure Retail Prices ingestion...")

while next_page:
    response = requests.get(next_page, timeout=60)
    response.raise_for_status()
    data = response.json()
    items = data.get("Items", [])
    for item in items:
        all_items.append((
            item.get("currencyCode"), item.get("tierMinimumUnits"),
            item.get("retailPrice"), item.get("unitPrice"),
            item.get("armRegionName"), item.get("location"),
            item.get("effectiveStartDate"), item.get("meterId"),
            item.get("meterName"), item.get("productId"),
            item.get("skuId"), item.get("productName"),
            item.get("skuName"), item.get("serviceName"),
            item.get("serviceId"), item.get("serviceFamily"),
            item.get("unitOfMeasure"), item.get("type"),
            item.get("isPrimaryMeterRegion"), item.get("armSkuName"),
            item.get("reservationTerm")
        ))
    page_count += 1
    if page_count % 100 == 0:
        print(f"  Fetched {page_count} pages, {len(all_items)} rows so far...")
    next_page = data.get("NextPageLink")

print(f"Fetched {page_count} pages total, {len(all_items)} rows.")

df = spark.createDataFrame(all_items, schema=schema)
df.write.mode("overwrite").format("delta").saveAsTable("tbl_AzureRetailPrices")

print(f"Table tbl_AzureRetailPrices written with {len(all_items)} rows (overwrite mode).")
