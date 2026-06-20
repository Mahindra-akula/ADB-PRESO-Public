# Databricks notebook source
# dlt_pipeline.py — Lakeflow Declarative Pipeline (DLT)
# Deploy as a pipeline in the workspace: Workflows → Delta Live Tables → Create Pipeline
# Target catalog: retail_intelligence | Compute: Serverless
#
# Tables produced:
#   bronze.pos_transactions_raw      — raw ingestion from Volume
#   silver.pos_store_sku_signals     — deduped + 7/14-day rolling demand
#   gold.replenishment_signals       — reorder status per store+SKU

import dlt
from pyspark.sql import functions as F

CATALOG     = "retail_intelligence"
VOLUME_PATH = f"/Volumes/{CATALOG}/bronze/raw_pos"

# ── Bronze ─────────────────────────────────────────────────────────────────────
@dlt.table(
    name="pos_transactions_raw",
    comment="Raw POS transactions ingested from store Volume. Source of truth for all downstream."
)
def pos_transactions_raw():
    return spark.read.parquet(f"{VOLUME_PATH}/pos_transactions/")

# ── Silver ─────────────────────────────────────────────────────────────────────
@dlt.table(
    name="pos_store_sku_signals",
    comment="Deduped daily POS with 7 and 14-day rolling demand signals per store+SKU."
)
@dlt.expect("valid_qty",       "qty_sold >= 0")
@dlt.expect("valid_inventory", "inventory_on_hand >= 0")
def pos_store_sku_signals():
    return spark.sql("""
        WITH deduped AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY store_id, sku_id, transaction_date
                    ORDER BY transaction_date
                ) AS rn
            FROM LIVE.pos_transactions_raw
        )
        SELECT
            store_id,
            sku_id,
            transaction_date,
            qty_sold,
            unit_price,
            inventory_on_hand,
            AVG(qty_sold) OVER (
                PARTITION BY store_id, sku_id
                ORDER BY transaction_date
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS avg_daily_demand_7d,
            AVG(qty_sold) OVER (
                PARTITION BY store_id, sku_id
                ORDER BY transaction_date
                ROWS BETWEEN 13 PRECEDING AND CURRENT ROW
            ) AS avg_daily_demand_14d,
            CURRENT_TIMESTAMP() AS load_timestamp
        FROM deduped
        WHERE rn = 1
    """)

# ── Gold ───────────────────────────────────────────────────────────────────────
@dlt.table(
    name="replenishment_signals",
    comment="Live replenishment signals: days of supply and reorder status per store+SKU as of latest date."
)
def replenishment_signals():
    return spark.sql("""
        SELECT
            store_id,
            sku_id,
            inventory_on_hand,
            ROUND(avg_daily_demand_7d,  1) AS avg_daily_demand_7d,
            ROUND(avg_daily_demand_14d, 1) AS avg_daily_demand_14d,
            ROUND(inventory_on_hand / NULLIF(avg_daily_demand_7d, 0), 1) AS days_of_supply,
            CASE
                WHEN inventory_on_hand / NULLIF(avg_daily_demand_7d, 0) < 3 THEN 'REORDER NOW'
                WHEN inventory_on_hand / NULLIF(avg_daily_demand_7d, 0) < 7 THEN 'WATCH'
                ELSE 'OK'
            END AS replenishment_status,
            transaction_date AS signal_date
        FROM LIVE.pos_store_sku_signals
        WHERE transaction_date = (
            SELECT MAX(transaction_date) FROM LIVE.pos_store_sku_signals
        )
    """)
