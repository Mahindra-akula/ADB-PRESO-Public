# Databricks notebook source
# pipeline_config.py — shared constants
# Usage: %run ./config/pipeline_config  (from src/ notebooks)

CATALOG     = "retail_intelligence"
SCHEMA      = "retail_data"
VOLUME_PATH = f"/Volumes/{CATALOG}/{SCHEMA}/raw_pos"

N_STORES    = 100   # demo slice — scales to 800
N_SKUS      = 50
N_DAYS      = 30
REORDER_DAYS = 3
WATCH_DAYS   = 7
