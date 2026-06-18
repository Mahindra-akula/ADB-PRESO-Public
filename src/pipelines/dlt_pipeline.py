# Databricks notebook source
# dlt_pipeline.py — Lakeflow Declarative Pipeline
# All tables land in retail_intelligence.retail_data (set in pipeline config)

import dlt
from pyspark.sql import functions as F

VOLUME_PATH = "/Volumes/retail_intelligence/retail_data/raw_pos"

# ── Bronze ─────────────────────────────────────────────────────────────────────
@dlt.table(comment="Raw POS transactions from store Volume. Source of truth.")
def pos_transactions_raw():
    return spark.read.parquet(f"{VOLUME_PATH}/pos_transactions/")

# ── Silver ─────────────────────────────────────────────────────────────────────
@dlt.table(comment="Deduped POS with 7 and 14-day rolling demand per store+SKU.")
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
            store_id, sku_id, transaction_date,
            qty_sold, unit_price, inventory_on_hand,
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
@dlt.table(comment="Replenishment signals: days of supply and reorder status per store+SKU.")
def replenishment_signals():
    return spark.sql("""
        SELECT
            store_id, sku_id,
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
        WHERE transaction_date = (SELECT MAX(transaction_date) FROM LIVE.pos_store_sku_signals)
    """)
