# Databricks notebook source
# pipeline_config.py — shared constants for all notebooks
# %run ../config/pipeline_config

CATALOG       = "retail_intelligence"
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"
GOLD_SCHEMA   = "gold"
VOLUME_PATH   = f"/Volumes/{CATALOG}/bronze/raw_pos"

N_STORES      = 100   # demo slice — architecture scales to 800
N_SKUS        = 50    # high-velocity SKUs only
N_DAYS        = 30    # 30-day rolling window
REORDER_DAYS  = 3     # days_of_supply threshold for REORDER NOW
WATCH_DAYS    = 7     # days_of_supply threshold for WATCH
