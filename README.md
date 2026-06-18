# Retail Replenishment Intelligence
### Built on Databricks — SA Interview Demo

A working prototype that replaces weekly Excel-based demand forecasting with near-real-time POS-driven replenishment signals for an 800-store retailer. Built as a demonstration for a Databricks Solutions Architect "Build, Demo, Pitch!" interview.

**Live App:** https://retail-replenishment-7474655529260099.aws.databricksapps.com

---

## The Business Problem

An 800-store retailer is losing revenue to stockouts on high-velocity SKUs. Their demand forecasting runs once a week in Excel — which means by the time a stockout is flagged, it already happened. The stores are always fixing *last week's* problem.

> **12% stockout rate** across high-velocity SKUs. Each percentage point costs ~$600K/week in lost revenue.

Their CTO is simultaneously evaluating Databricks, Snowflake, and Microsoft Fabric.

---

## The Solution

Replace the weekly Excel report with a daily replenishment signal pipeline that:

1. Ingests raw POS transactions from all stores
2. Computes rolling 7-day demand per store+SKU
3. Calculates days of supply and flags items as **REORDER NOW / WATCH / OK**
4. Surfaces the signals in a live dashboard app — one URL, every audience

The signals fire *before* the shelf goes empty, not after.

---

## Architecture

```
POS Transactions (800 stores)
         │
         ▼
┌─────────────────┐
│     BRONZE      │  Raw ingestion via Lakeflow Declarative Pipelines
│  pos_raw table  │  Delta Live Tables — Auto Loader ready
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│     SILVER      │  Deduplicated + typed
│  store_sku      │  7-day rolling demand signal per store+SKU
│  signals table  │  DLT expectations enforce data quality
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│      GOLD       │  One row per store+SKU as of latest signal date
│  replenishment  │  Days of supply, REORDER NOW / WATCH / OK status
│  signals table  │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────────────┐
│              Databricks App                         │
│  React + FastAPI + Databricks SDK                   │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  Executive   │  │  Operations  │                │
│  │  Overview    │  │  Command     │                │
│  │              │  │  Center      │                │
│  └──────────────┘  └──────────────┘                │
│  ┌──────────────┐  ┌──────────────┐                │
│  │  Platform &  │  │ Architecture │                │
│  │  Governance  │  │  Diagram     │                │
│  └──────────────┘  └──────────────┘                │
└─────────────────────────────────────────────────────┘
```

### Unity Catalog Layout
```
retail_intelligence (catalog)
└── retail_data (schema)
    ├── stores                   — 100 stores, 5 regions
    ├── skus                     — 50 high-velocity SKUs, 8 categories
    ├── pos_transactions_raw     — Bronze: 150K raw POS rows
    ├── pos_store_sku_signals    — Silver: rolling demand signals
    └── replenishment_signals    — Gold: 5K actionable signals
```

---

## What the App Shows

| Tab | Audience | Key Metrics |
|-----|----------|-------------|
| **Executive Overview** | Business Leader | Stockout rate %, weekly revenue at risk, status distribution |
| **Ops Command Center** | VP of Engineering | Top 25 REORDER NOW alerts, regional heatmap, category risks |
| **Platform & Governance** | CTO | Pipeline row counts per layer, last signal date, platform notes |
| **Architecture** | All | End-to-end data flow diagram |

**Live numbers (demo dataset):**
- 79.1% of store+SKU combos flagged REORDER NOW
- $4.35M estimated weekly revenue at risk
- 150,000 POS transactions processed through the medallion pipeline

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Pipeline | Lakeflow Declarative Pipelines (DLT) — serverless |
| Storage | Delta Lake on Unity Catalog |
| Governance | Unity Catalog — three-part table names, lineage |
| Compute | Databricks Serverless SQL (no cluster management) |
| App backend | FastAPI + Databricks SDK (`WorkspaceClient`) |
| App frontend | React 18 + Vite + Recharts |
| Deployment | Databricks Asset Bundles (DABs) |

---

## Why Databricks vs Snowflake / Microsoft Fabric

| Capability | Databricks | Snowflake | Microsoft Fabric |
|-----------|-----------|-----------|-----------------|
| Pipeline + BI + App in one platform | ✅ | ❌ Needs dbt + Tableau | ⚠️ Partial |
| Streaming-ready with one line change | ✅ `read` → `readStream` | ❌ | ❌ |
| Open format (no vendor lock-in) | ✅ Delta in Volumes | ❌ Proprietary | ⚠️ OneLake |
| Unity Catalog lineage | ✅ Built-in | ❌ Separate tool | ⚠️ Purview |
| Serverless SQL + App hosting | ✅ | ⚠️ Serverless only | ⚠️ |

---

## Repo Structure

```
ADB-preso/
├── databricks.yml                       ← DAB root config
├── .databricksignore                    ← excludes node_modules from workspace upload
├── resources/
│   ├── data_gen.job.yml                 ← serverless job: synthetic data generation
│   ├── replenishment_pipeline.yml       ← Lakeflow DLT pipeline
│   └── replenishment_app.yml           ← Databricks App resource
├── src/
│   ├── data/
│   │   └── 00_synthetic_data_gen.py    ← PySpark: generates 150K POS rows
│   ├── pipelines/
│   │   └── dlt_pipeline.py             ← DLT: bronze → silver → gold
│   ├── notebooks/
│   │   └── 01_kpi_validation.sql       ← demo queries with narrative cues
│   └── app/
│       ├── app.yaml                    ← App manifest (uvicorn on port 8000)
│       ├── main.py                     ← FastAPI: 5 API endpoints + React SPA
│       ├── requirements.txt            ← fastapi, uvicorn, databricks-sdk
│       ├── static/                     ← React build output (deployed)
│       └── frontend/                   ← React source (Vite + Recharts)
├── PROMPT.md                           ← interview scenario + constraints
├── IMPLEMENTATION_PROMPT.md            ← step-by-step build guide with code
├── SKILL_databricks_app_react_fastapi.md ← reusable pattern for similar apps
└── CLAUDE.md                           ← AI pair programming instructions
```

---

## Quickstart

### Prerequisites
- Databricks CLI configured (`DEFAULT` profile)
- Databricks Free Edition workspace with Unity Catalog
- Node.js 18+ (for frontend build)

### Deploy from scratch

```bash
# 1. Build the React frontend
cd src/app/frontend && npm install && npm run build && cd ../../..

# 2. Deploy all resources (pipeline, job, app)
databricks bundle deploy --auto-approve --profile DEFAULT

# 3. Generate synthetic data
databricks bundle run data_gen_job --profile DEFAULT

# 4. Run the DLT pipeline
databricks bundle run replenishment_pipeline --profile DEFAULT

# 5. Start the app
databricks bundle run replenishment_app --profile DEFAULT

# 6. Grant Unity Catalog access to the app service principal (first time only)
#    Get the SP UUID:
databricks apps get retail-replenishment --profile DEFAULT | python -c "import sys,json; print(json.load(sys.stdin)['oauth2_app_client_id'])"
#    Then run the three GRANT statements — see IMPLEMENTATION_PROMPT.md Step 7
```

Full build completes in ~30 minutes. See `IMPLEMENTATION_PROMPT.md` for detailed steps and troubleshooting.

---

## Key Design Decisions

**Single schema (`retail_data`) for all medallion layers** — DLT on Databricks Free Edition works most reliably with one `target` schema per pipeline. Bronze, silver, and gold are differentiated by table name prefix, not schema.

**React + FastAPI instead of Dash + iframes** — Databricks AI/BI dashboards set `X-Frame-Options` headers that block iframe embedding in other apps. A native React frontend with direct SQL queries has no such constraint and enables richer, custom visualizations.

**`databricks-sdk` for app auth** — `databricks-sql-connector` ignores the OAuth token injected by the Apps platform and falls back to a browser OAuth flow, which fails in a serverless container. `WorkspaceClient()` from the SDK reads the injected credentials correctly.

**150K rows for demo** — Scaled down from a full 800-store × 200-SKU × 90-day dataset (14.4M rows) to 100 stores × 50 SKUs × 30 days = 150K rows. Fits in a 30-minute build window with zero architecture changes needed to scale back up.
