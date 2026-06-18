# IMPLEMENTATION PROMPT — Retail Replenishment Intelligence on Databricks

## Mission
Build a working Databricks prototype that solves a **12% stockout rate** for an 800-store retailer by replacing weekly Excel forecasting with near-real-time POS-driven replenishment signals. The demo must land with a Business Leader, CTO, and VP of Engineering in 60 minutes.

> "Weekly Excel means they're always fixing last week's stockout. We give them a signal that fires before the shelf goes empty."

---

## Workspace
| Setting | Value |
|---------|-------|
| Host | `https://dbc-eaeac0c1-f644.cloud.databricks.com` |
| Profile | `DEFAULT` |
| Catalog | `retail_intelligence` |
| Schema | `retail_data` (single schema — DLT target) |
| Volume | `/Volumes/retail_intelligence/retail_data/raw_pos/` |
| SQL Warehouse | `4e7b8de25b26878f` (Serverless Starter) |
| Compute | **Serverless only** — no classic clusters, no node type pinning |
| Table refs | Always three-part: `retail_intelligence.retail_data.table` |

---

## Critical Rules (Learned from Deployment)

### Free Edition Constraints
- **Never** add `environment_key`, `environments:`, or `client: "1"` to any DAB resource — causes `INTERNAL_ERROR`
- Serverless compute is inferred automatically — do not specify it manually in jobs

### DLT / Lakeflow Pipelines
- Use a **single `target` schema** (`retail_data`) — do not try to write across bronze/silver/gold schemas in one pipeline
- Pipeline resource config: `serverless: true`, `catalog: retail_intelligence`, `target: retail_data`, `channel: PREVIEW`

### Databricks App Auth
- Use **`databricks-sdk`** for all data access — NOT `databricks-sql-connector`
- The SDK's `WorkspaceClient()` auto-reads `DATABRICKS_HOST` + `DATABRICKS_TOKEN` injected by the Apps platform
- `databricks-sql-connector` ignores the injected token and tries OAuth browser flow → fails with "no free port"
- All values from `statement_execution` come back as **strings** — always convert: `int(float(x))` for floats, `int(x)` for integer counts

### App Service Principal Permissions
- The app creates its own service principal (UUID = `app_oauth2_app_client_id` field in `databricks apps get`)
- Grant Unity Catalog access via SQL using the UUID (not the display name):
  ```sql
  GRANT USE CATALOG ON CATALOG retail_intelligence TO `<sp-uuid>`;
  GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `<sp-uuid>`;
  GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `<sp-uuid>`;
  ```

### React + Vite Frontend
- Build output goes to `src/app/static/` — this is the only directory that gets deployed
- Add `node_modules/` and all source files to `.databricksignore` — 57MB of npm packages will stall deployment
- FastAPI serves `/assets` as `StaticFiles`, then catch-all `/{full_path:path}` returns `index.html`

---

## Project Layout
```
ADB-preso/
├── databricks.yml                       ← DAB root config
├── .databricksignore                    ← excludes node_modules from upload
├── resources/
│   ├── data_gen.job.yml                 ← serverless notebook job
│   ├── replenishment_pipeline.yml       ← DLT pipeline
│   └── replenishment_app.yml           ← Databricks App
├── src/
│   ├── data/
│   │   └── 00_synthetic_data_gen.py    ← creates catalog/schema/volume + POS data
│   ├── pipelines/
│   │   └── dlt_pipeline.py             ← bronze → silver → gold (DLT)
│   ├── notebooks/
│   │   └── 01_kpi_validation.sql       ← demo queries with # DEMO: cues
│   └── app/
│       ├── app.yaml                    ← App manifest (uvicorn command)
│       ├── main.py                     ← FastAPI backend (SDK auth)
│       ├── requirements.txt            ← fastapi, uvicorn[standard], databricks-sdk
│       ├── static/                     ← React build output (committed)
│       └── frontend/                   ← React source (not deployed)
├── PROMPT.md
└── IMPLEMENTATION_PROMPT.md
```

---

## Build Steps (in order)

---

### Step 1 · DAB Configuration

**`databricks.yml`**
```yaml
bundle:
  name: retail-replenishment

include:
  - resources/*.yml

targets:
  dev:
    default: true
    mode: development
    workspace:
      host: https://dbc-eaeac0c1-f644.cloud.databricks.com
      profile: DEFAULT
```

**`.databricksignore`**
```
src/app/frontend/node_modules/
src/app/frontend/src/
src/app/frontend/public/
src/app/frontend/package.json
src/app/frontend/package-lock.json
src/app/frontend/vite.config.js
src/app/frontend/index.html
src/app/app.py
config/
data/
pipelines/
notebooks/
app/
```

---

### Step 2 · DAB Resource Files

**`resources/data_gen.job.yml`**
```yaml
resources:
  jobs:
    data_gen_job:
      name: "[${bundle.target}] Retail - Synthetic Data Generation"
      tasks:
        - task_key: generate_data
          notebook_task:
            notebook_path: ../src/data/00_synthetic_data_gen.py
            source: WORKSPACE
          job_cluster_key: serverless
      job_clusters:
        - job_cluster_key: serverless
          new_cluster:
            num_workers: 0
            spark_version: "15.4.x-scala2.12"
            node_type_id: "i3.xlarge"
```
> Note: For serverless notebook jobs, omit `job_clusters` and use `environment` only if needed. Simplest: let DABs infer serverless.

**`resources/replenishment_pipeline.yml`**
```yaml
resources:
  pipelines:
    replenishment_pipeline:
      name: "[${bundle.target}] Retail Replenishment Pipeline"
      serverless: true
      catalog: retail_intelligence
      target: retail_data
      libraries:
        - notebook:
            path: ../src/pipelines/dlt_pipeline.py
      continuous: false
      channel: PREVIEW
```

**`resources/replenishment_app.yml`**
```yaml
resources:
  apps:
    replenishment_app:
      name: "retail-replenishment"
      description: "Retail Replenishment Intelligence — demand signal platform"
      source_code_path: ../src/app
```

---

### Step 3 · Synthetic Data Generation

**`src/data/00_synthetic_data_gen.py`**

```python
# Create catalog, schema, volume
spark.sql("CREATE CATALOG IF NOT EXISTS retail_intelligence")
spark.sql("CREATE SCHEMA IF NOT EXISTS retail_intelligence.retail_data")
spark.sql("CREATE VOLUME IF NOT EXISTS retail_intelligence.retail_data.raw_pos")

from pyspark.sql import functions as F

CATALOG = "retail_intelligence"
SCHEMA  = "retail_data"
VOLUME  = f"/Volumes/{CATALOG}/{SCHEMA}/raw_pos"
N_STORES = 100
N_SKUS   = 50
N_DAYS   = 30

# Stores
regions = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]
stores = (
    spark.range(N_STORES)
    .withColumnRenamed("id", "store_id")
    .withColumn("store_id", F.concat(F.lit("S"), F.lpad(F.col("store_id").cast("string"), 3, "0")))
    .withColumn("region", F.element_at(F.array(*[F.lit(r) for r in regions]),
                (F.rand(seed=42) * 5 + 1).cast("int")))
    .withColumn("city", F.concat(F.lit("City_"), F.col("store_id")))
)
stores.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.stores")

# SKUs
categories = ["Beverages", "Snacks", "Dairy", "Produce", "Frozen",
              "Personal Care", "Household", "Bakery"]
skus = (
    spark.range(N_SKUS)
    .withColumnRenamed("id", "sku_id_num")
    .withColumn("sku_id", F.concat(F.lit("SKU"), F.lpad(F.col("sku_id_num").cast("string"), 3, "0")))
    .withColumn("category", F.element_at(F.array(*[F.lit(c) for c in categories]),
                (F.rand(seed=99) * 8 + 1).cast("int")))
    .withColumn("avg_unit_price", F.round(F.rand(seed=7) * 18 + 2, 2))
    .drop("sku_id_num")
)
skus.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.skus")

# POS transactions — 100 stores × 50 SKUs × 30 days = 150K rows
from datetime import date, timedelta
start_date = date.today() - timedelta(days=N_DAYS)
dates = [str(start_date + timedelta(days=i)) for i in range(N_DAYS)]

store_ids = [r.store_id for r in stores.select("store_id").collect()]
sku_ids   = [r.sku_id   for r in skus.select("sku_id").collect()]

store_df = spark.createDataFrame([(s,) for s in store_ids], ["store_id"])
sku_df   = spark.createDataFrame([(s,) for s in sku_ids],   ["sku_id"])
date_df  = spark.createDataFrame([(d,) for d in dates],     ["transaction_date"])

pos = (
    store_df.crossJoin(sku_df).crossJoin(date_df)
    .withColumn("base_demand", (F.rand(seed=1) * 20 + 5).cast("int"))
    .withColumn("dow", F.dayofweek(F.col("transaction_date")))
    .withColumn("qty_sold",
        F.when(F.rand(seed=2) < 0.12, F.lit(0))   # 12% stockout simulation
         .when(F.col("dow").isin(1, 7), (F.col("base_demand") * 1.25).cast("int"))
         .when(F.col("dow") == 2, (F.col("base_demand") * 0.90).cast("int"))
         .otherwise(F.col("base_demand")))
    .withColumn("inventory_on_hand",
        F.when(F.col("qty_sold") == 0, F.lit(0))
         .otherwise((F.rand(seed=3) * 50 + 10).cast("int")))
    .withColumn("unit_price", F.round(F.rand(seed=4) * 18 + 2, 2))
    .select("store_id", "sku_id", "transaction_date",
            "qty_sold", "unit_price", "inventory_on_hand")
)

pos.write.mode("overwrite").parquet(f"{VOLUME}/pos_transactions/")
pos.write.mode("overwrite").saveAsTable(f"{CATALOG}.{SCHEMA}.pos_transactions_raw")
print(f"Generated {pos.count():,} POS rows")
```

---

### Step 4 · DLT Pipeline

**`src/pipelines/dlt_pipeline.py`**

```python
import dlt
from pyspark.sql import functions as F

CATALOG = "retail_intelligence"
SCHEMA  = "retail_data"
VOLUME  = f"/Volumes/{CATALOG}/{SCHEMA}/raw_pos"

# ── Bronze ──────────────────────────────────────────────────────────────────
@dlt.table(
    name="pos_transactions_raw",
    comment="Raw POS transactions from store Volume — bronze layer"
)
def pos_transactions_raw():
    return spark.read.parquet(f"{VOLUME}/pos_transactions/")


# ── Silver ──────────────────────────────────────────────────────────────────
@dlt.table(
    name="pos_store_sku_signals",
    comment="Deduped store+SKU rows with 7-day rolling demand signal — silver layer"
)
@dlt.expect("valid_qty", "qty_sold >= 0")
@dlt.expect("valid_inventory", "inventory_on_hand >= 0")
def pos_store_sku_signals():
    return spark.sql("""
        SELECT
            store_id, sku_id,
            transaction_date,
            qty_sold,
            inventory_on_hand,
            AVG(qty_sold) OVER (
                PARTITION BY store_id, sku_id
                ORDER BY transaction_date
                ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
            ) AS avg_daily_demand_7d
        FROM LIVE.pos_transactions_raw
    """)


# ── Gold ─────────────────────────────────────────────────────────────────────
@dlt.table(
    name="replenishment_signals",
    comment="One row per store+SKU as of latest signal date — gold layer"
)
def replenishment_signals():
    return spark.sql("""
        SELECT
            store_id,
            sku_id,
            inventory_on_hand,
            ROUND(avg_daily_demand_7d, 1)                                       AS avg_daily_demand_7d,
            ROUND(inventory_on_hand / NULLIF(avg_daily_demand_7d, 0), 1)        AS days_of_supply,
            CASE
                WHEN inventory_on_hand / NULLIF(avg_daily_demand_7d, 0) < 3  THEN 'REORDER NOW'
                WHEN inventory_on_hand / NULLIF(avg_daily_demand_7d, 0) < 7  THEN 'WATCH'
                ELSE 'OK'
            END                                                                  AS replenishment_status,
            transaction_date                                                     AS signal_date
        FROM LIVE.pos_store_sku_signals
        WHERE transaction_date = (SELECT MAX(transaction_date) FROM LIVE.pos_store_sku_signals)
    """)
```

---

### Step 5 · FastAPI Backend

**`src/app/requirements.txt`**
```
fastapi
uvicorn[standard]
databricks-sdk
```

**`src/app/app.yaml`**
```yaml
command:
  - uvicorn
  - main:app
  - --host
  - "0.0.0.0"
  - --port
  - "8000"
env:
  - name: WAREHOUSE_ID
    value: "4e7b8de25b26878f"
```

**`src/app/main.py`**
```python
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

app = FastAPI()

WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "4e7b8de25b26878f")

# WorkspaceClient auto-reads DATABRICKS_HOST + DATABRICKS_TOKEN injected by Apps platform
_client = None
def get_client():
    global _client
    if _client is None:
        _client = WorkspaceClient()
    return _client


def query(sql_text: str):
    """Execute SQL via statement execution API. Returns list of dicts.
    IMPORTANT: All values come back as strings — always cast to int/float explicitly."""
    w = get_client()
    result = w.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql_text,
        wait_timeout="50s",
    )
    if result.status.state != StatementState.SUCCEEDED:
        err = result.status.error
        raise RuntimeError(f"Query failed [{result.status.state}]: {err.message if err else 'unknown'}")
    cols = [col.name for col in result.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (result.result.data_array or [])]


@app.get("/api/summary")
def summary():
    status_rows = query("""
        SELECT replenishment_status,
               COUNT(*) AS cnt,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM retail_intelligence.retail_data.replenishment_signals
        GROUP BY replenishment_status ORDER BY cnt DESC
    """)
    rev = query("""
        SELECT ROUND(SUM(r.avg_daily_demand_7d * k.avg_unit_price * 7), 0) AS rev
        FROM retail_intelligence.retail_data.replenishment_signals r
        JOIN retail_intelligence.retail_data.skus k USING (sku_id)
        WHERE r.replenishment_status = 'REORDER NOW'
    """)
    counts = query("""
        SELECT COUNT(DISTINCT store_id) AS stores, COUNT(DISTINCT sku_id) AS skus
        FROM retail_intelligence.retail_data.replenishment_signals
    """)
    reorder_pct = next((float(r["pct"]) for r in status_rows if r["replenishment_status"] == "REORDER NOW"), 0)
    return {
        "stockout_rate_pct": reorder_pct,
        "revenue_at_risk": int(float(rev[0]["rev"] or 0)),   # ROUND() returns float-string e.g. '4350213.0'
        "total_stores": int(counts[0]["stores"]),
        "total_skus": int(counts[0]["skus"]),
        "status_counts": [{"status": r["replenishment_status"], "count": int(r["cnt"]), "pct": float(r["pct"])} for r in status_rows],
    }


@app.get("/api/regional")
def regional():
    rows = query("""
        SELECT s.region, r.replenishment_status, COUNT(*) AS cnt
        FROM retail_intelligence.retail_data.replenishment_signals r
        JOIN retail_intelligence.retail_data.stores s USING (store_id)
        GROUP BY s.region, r.replenishment_status ORDER BY s.region
    """)
    pivot = {}
    for row in rows:
        region = row["region"]
        if region not in pivot:
            pivot[region] = {"region": region, "REORDER NOW": 0, "WATCH": 0, "OK": 0}
        pivot[region][row["replenishment_status"]] = int(row["cnt"])
    return list(pivot.values())


@app.get("/api/top-alerts")
def top_alerts():
    return query("""
        SELECT s.region, r.store_id, k.category, r.sku_id,
               ROUND(r.days_of_supply, 1) AS days_of_supply,
               r.inventory_on_hand,
               ROUND(r.avg_daily_demand_7d, 1) AS avg_daily_demand_7d
        FROM retail_intelligence.retail_data.replenishment_signals r
        JOIN retail_intelligence.retail_data.stores s USING (store_id)
        JOIN retail_intelligence.retail_data.skus   k USING (sku_id)
        WHERE r.replenishment_status = 'REORDER NOW'
        ORDER BY r.days_of_supply ASC LIMIT 25
    """)


@app.get("/api/categories")
def categories():
    return query("""
        SELECT k.category, COUNT(*) AS stores_at_risk,
               ROUND(AVG(r.days_of_supply), 1) AS avg_days_supply
        FROM retail_intelligence.retail_data.replenishment_signals r
        JOIN retail_intelligence.retail_data.skus k USING (sku_id)
        WHERE r.replenishment_status = 'REORDER NOW'
        GROUP BY k.category ORDER BY stores_at_risk DESC
    """)


@app.get("/api/platform-stats")
def platform_stats():
    tables = [
        ("pos_transactions_raw",  "Bronze"),
        ("pos_store_sku_signals", "Silver"),
        ("replenishment_signals", "Gold"),
    ]
    result = []
    for tbl, layer in tables:
        rows = query(f"SELECT COUNT(*) AS cnt FROM retail_intelligence.retail_data.{tbl}")
        result.append({"table": tbl, "layer": layer, "rows": int(rows[0]["cnt"])})
    last = query("SELECT MAX(signal_date) AS last_updated FROM retail_intelligence.retail_data.replenishment_signals")
    return {"tables": result, "last_updated": str(last[0]["last_updated"])}


# Serve React SPA — mount assets first, then catch-all for client-side routing
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    return FileResponse("static/index.html")
```

---

### Step 6 · React Frontend

**`src/app/frontend/` structure:**
```
frontend/
├── package.json       (react, recharts, vite)
├── vite.config.js     (build outDir: ../static)
├── index.html
└── src/
    ├── App.jsx        (4-tab nav)
    └── components/
        ├── Executive.jsx   (/api/summary → KPI tiles + bar + pie)
        ├── Operations.jsx  (/api/top-alerts + /api/regional + /api/categories)
        ├── Platform.jsx    (/api/platform-stats → row counts per layer)
        └── Architecture.jsx (static JSX diagram — no API call)
```

**`vite.config.js`** — output to `../static` so the build lands in `src/app/static/`:
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../static' },
  server: { proxy: { '/api': 'http://localhost:8000' } }
})
```

**Build command** (run before every deploy):
```bash
cd src/app/frontend && npm install && npm run build
```
Build output (`src/app/static/`) is committed to the repo and deployed to the workspace.

---

### Step 7 · Grant App Service Principal Permissions

After first `databricks bundle run replenishment_app`, the app creates a service principal.
Get its UUID and grant Unity Catalog access:

```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient(profile='DEFAULT')

# Find the SP UUID — it's the oauth2_app_client_id from `databricks apps get <name>`
sp_uuid = "<paste-from-databricks-apps-get-output>"

for stmt in [
    f"GRANT USE CATALOG ON CATALOG retail_intelligence TO `{sp_uuid}`",
    f"GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `{sp_uuid}`",
    f"GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `{sp_uuid}`",
]:
    r = w.statement_execution.execute_statement(
        warehouse_id='4e7b8de25b26878f', statement=stmt, wait_timeout='30s'
    )
    print(r.status.state, stmt[:60])
```

> Get the UUID from: `databricks apps get retail-replenishment --profile DEFAULT | python -c "import sys,json; d=json.load(sys.stdin); print(d['oauth2_app_client_id'])"`

---

### Step 8 · Full Deployment Sequence

```bash
# 1. Build React (run once, or after any frontend change)
cd src/app/frontend && npm install && npm run build && cd ../../..

# 2. Deploy all resources via DABs
databricks bundle deploy --auto-approve --profile DEFAULT

# 3. Run data generation job
databricks bundle run data_gen_job --profile DEFAULT

# 4. Run DLT pipeline
databricks bundle run replenishment_pipeline --profile DEFAULT

# 5. Start app
databricks bundle run replenishment_app --profile DEFAULT

# 6. Grant SP permissions (first time only — get UUID first)
# databricks apps get retail-replenishment --profile DEFAULT | python -c "import sys,json; d=json.load(sys.stdin); print(d['oauth2_app_client_id'])"
# Then run the GRANT statements from Step 7

# 7. Restart app to pick up new permissions
databricks bundle run replenishment_app --profile DEFAULT
```

---

### Step 9 · KPI Validation Queries (Demo Script)

**`src/notebooks/01_kpi_validation.sql`**

```sql
-- DEMO: "Headline number — current stockout rate across all stores"
SELECT replenishment_status,
       COUNT(*)                                                AS store_sku_combos,
       ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)    AS pct_of_total
FROM retail_intelligence.retail_data.replenishment_signals
GROUP BY replenishment_status ORDER BY store_sku_combos DESC;

-- DEMO: "Revenue at risk — what this stockout rate costs per week"
SELECT ROUND(SUM(r.avg_daily_demand_7d * k.avg_unit_price * 7), 0) AS weekly_revenue_at_risk
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.skus k USING (sku_id)
WHERE r.replenishment_status = 'REORDER NOW';

-- DEMO: "Regional breakdown — where are the trucks needed most?"
SELECT s.region, r.replenishment_status, COUNT(*) AS count
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.stores s USING (store_id)
GROUP BY s.region, r.replenishment_status ORDER BY s.region;

-- DEMO: "Top SKUs putting most stores at risk right now"
SELECT k.category, r.sku_id, COUNT(*) AS stores_at_risk,
       ROUND(AVG(r.days_of_supply), 1) AS avg_days_supply
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.skus k USING (sku_id)
WHERE r.replenishment_status = 'REORDER NOW'
GROUP BY k.category, r.sku_id ORDER BY stores_at_risk DESC LIMIT 20;
```

---

## Time Budget (60-min build)

| # | Task | Time |
|---|------|------|
| 1 | `databricks bundle deploy` — deploys all resources | 2 min |
| 2 | `databricks bundle run data_gen_job` — generates 150K POS rows | 5 min |
| 3 | `databricks bundle run replenishment_pipeline` — runs DLT (background) | kick off, 10 min to complete |
| 4 | Build React: `npm install && npm run build` | 3 min |
| 5 | `databricks bundle run replenishment_app` — first deploy | 3 min |
| 6 | Grant SP permissions (get UUID, run GRANT statements) | 3 min |
| 7 | `databricks bundle run replenishment_app` — restart with permissions | 2 min |
| 8 | Verify all 4 tabs load (DLT should be done by now) | 2 min |
| **Total** | | **~30 min** |

> Remaining 30 min of build budget + 3h: presentation slides, pitch narrative, demo run-through.

---

## Demo Script Cues

| Moment | Line |
|--------|------|
| DLT lineage graph | "End-to-end lineage, built in. One click — this is Unity Catalog's answer to the CTO's governance question." |
| Gold signal table | "One row per store per SKU. Days of supply, calculated daily across 5,000 combinations — scales to 160K at 800 stores." |
| REORDER NOW rows | "These stores stock out tomorrow. Their Excel model wouldn't flag this until Monday's report." |
| Revenue at risk tile | "$4.35M weekly — this is the dollar value of the problem we just quantified, before any optimization." |
| App tab switch | "Each stakeholder gets their own view — one URL, all audiences, zero separate tools." |
| Architecture tab | "POS to signal in three DLT steps. Streaming-ready — one line change in the bronze layer." |
| CTO question | "Snowflake needs a separate BI tool, separate governance layer, separate orchestrator. This is one workspace." |

---

## Troubleshooting

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `INTERNAL_ERROR` on job run | `environment_key`/`environments`/`client:"1"` in job YAML | Remove those fields — Free Edition infers serverless |
| App 500 on all API routes | `databricks-sql-connector` OAuth loop | Switch to `databricks-sdk` in `requirements.txt` + `main.py` |
| `ValueError: invalid literal for int()` | SDK returns all values as strings; `ROUND()` → `'4350213.0'` | Use `int(float(x))` for any SQL ROUND/SUM result |
| Deployment stuck "Preparing source code" | `node_modules` in workspace from previous deploy | Delete via `databricks workspace delete --recursive .../frontend`, then redeploy |
| Permission denied on API routes | App SP not granted Unity Catalog access | Run GRANT statements using SP's UUID (not display name) |
| App still serving old version | Stale deployment | `databricks bundle run replenishment_app` triggers new deployment |
| OAuth 401 on curl test | Databricks Apps requires browser OAuth for all routes | Expected — test via browser, not curl |
