# Databricks notebook source
# 00_synthetic_data_gen.py
# Generates 100 stores × 50 SKUs × 30 days = 150,000 rows of synthetic POS data

# COMMAND ----------
# %run ../config/pipeline_config

# COMMAND ----------
from pyspark.sql import functions as F
import datetime

CATALOG      = "retail_intelligence"
SCHEMA       = "retail_data"
VOLUME_PATH  = f"/Volumes/{CATALOG}/{SCHEMA}/raw_pos"
N_STORES     = 100
N_SKUS       = 50
N_DAYS       = 30

# COMMAND ----------
# ── Workspace setup ────────────────────────────────────────────────────────────
spark.sql(f"CREATE CATALOG IF NOT EXISTS {CATALOG}")
spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {CATALOG}.{SCHEMA}.raw_pos")

# COMMAND ----------
# ── Dimension: stores ──────────────────────────────────────────────────────────
regions = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
states_by_region = {
    "Northeast": ["NY", "MA", "CT", "NJ", "PA"],
    "Southeast": ["FL", "GA", "NC", "SC", "VA"],
    "Midwest":   ["IL", "OH", "MI", "IN", "WI"],
    "Southwest": ["TX", "AZ", "NM", "NV", "OK"],
    "West":      ["CA", "WA", "OR", "CO", "UT"],
}

stores_data = [
    (i + 1, f"STORE_{i+1:04d}", regions[i % 5], states_by_region[regions[i % 5]][i % 5])
    for i in range(N_STORES)
]
stores_df = spark.createDataFrame(stores_data, ["store_id", "store_name", "region", "state"])
stores_df.write.format("delta").mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.stores")
print(f"stores: {stores_df.count()} rows")

# COMMAND ----------
# ── Dimension: skus ────────────────────────────────────────────────────────────
categories = ["beverages", "snacks", "dairy", "produce", "frozen",
              "personal_care", "household", "bakery"]
avg_prices = {"beverages": 4.99, "snacks": 2.49, "dairy": 3.99, "produce": 2.99,
              "frozen": 5.99, "personal_care": 6.99, "household": 7.49, "bakery": 3.49}

skus_data = [
    (i + 1, f"SKU_{i+1:04d}", categories[i % 8], avg_prices[categories[i % 8]])
    for i in range(N_SKUS)
]
skus_df = spark.createDataFrame(skus_data, ["sku_id", "sku_name", "category", "avg_unit_price"])
skus_df.write.format("delta").mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.skus")
print(f"skus: {skus_df.count()} rows")

# COMMAND ----------
# ── Fact: POS transactions ─────────────────────────────────────────────────────
end_date   = datetime.date.today()
start_date = end_date - datetime.timedelta(days=N_DAYS - 1)

dates_df  = spark.sql(f"SELECT explode(sequence(DATE('{start_date}'), DATE('{end_date}'), INTERVAL 1 DAY)) AS transaction_date")
store_ids = spark.table(f"{CATALOG}.{SCHEMA}.stores").select("store_id")
sku_ids   = spark.table(f"{CATALOG}.{SCHEMA}.skus").select("sku_id", "avg_unit_price")

pos_raw = (
    dates_df.crossJoin(store_ids).crossJoin(sku_ids)
    .withColumn("day_of_week", F.dayofweek("transaction_date"))
    .withColumn("base_qty", (F.rand(seed=42) * 50 + 10).cast("int"))
    .withColumn("seasonal_multiplier",
        F.when(F.col("day_of_week").isin(1, 7), 1.25)
         .when(F.col("day_of_week") == 2, 0.90)
         .otherwise(1.0))
    .withColumn("is_stockout", F.rand(seed=99) < 0.12)
    .withColumn("qty_sold",
        F.when(F.col("is_stockout"), 0)
         .otherwise((F.col("base_qty") * F.col("seasonal_multiplier")).cast("int")))
    .withColumn("inventory_on_hand",
        F.when(F.col("is_stockout"), 0)
         .otherwise((F.rand(seed=7) * 100 + 20).cast("int")))
    .withColumn("unit_price", F.col("avg_unit_price"))
    .select("store_id", "sku_id", "transaction_date", "qty_sold", "unit_price", "inventory_on_hand")
)

pos_raw.write.mode("overwrite").parquet(f"{VOLUME_PATH}/pos_transactions/")
print(f"POS transactions: {pos_raw.count()} rows → {VOLUME_PATH}/pos_transactions/")
