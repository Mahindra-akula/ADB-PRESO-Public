# IMPLEMENTATION PROMPT — Retail Replenishment Intelligence on Databricks

## Mission
Build a working Databricks prototype that solves a **12% stockout rate** for an 800-store retailer by replacing weekly Excel forecasting with near-real-time POS-driven replenishment signals. The demo must land with a Business Leader, CTO, and VP of Engineering in 60 minutes.

> "Weekly Excel means they're always fixing last week's stockout. We give them a signal that fires before the shelf goes empty."

---

## Workspace
| Setting | Value |
|---------|-------|
| Host | your Databricks workspace host |
| Profile | `DEFAULT` |
| Catalog | `retail_intelligence` |
| Schema | `retail_data` (single schema — DLT target) |
| Volume | `/Volumes/retail_intelligence/retail_data/raw_pos/` |
| SQL Warehouse | your serverless warehouse ID |
| Compute | **Serverless only** — no classic clusters, no node type pinning |
| Table refs | Always three-part: `catalog.schema.table` |

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
- All values from `statement_execution` come back as **strings** — always convert: `int(float(x))` for ROUND/SUM floats, `int(x)` for integer counts

### App Service Principal Permissions
- The app creates its own service principal (UUID in `oauth2_app_client_id` field from `databricks apps get`)
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
- **Always `npm run build` before `bundle deploy`** after any frontend change

### Demo Performance (Critical)
- Backend: wrap all read endpoints with a **1-hour in-memory cache** — warehouse queries take 2–5s cold; cached they're instant
- Frontend: **lift all data fetches to App.jsx** (single `useEffect` on mount), pass results as props to tabs — eliminates per-tab refetch latency
- Frontend: use **`display:none/block`** not conditional rendering for tabs — keeps all components mounted, preserving iframe state and avoiding remount

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
│       ├── app.yaml                    ← App manifest (uvicorn command + env vars)
│       ├── main.py                     ← FastAPI backend (SDK auth + 1-hour cache)
│       ├── requirements.txt            ← fastapi, uvicorn[standard], databricks-sdk
│       ├── static/                     ← React build output (committed + deployed)
│       └── frontend/                   ← React source (not deployed)
│           └── src/
│               ├── App.jsx             ← 4-tab nav, data lifting, display:none switching
│               └── components/
│                   ├── Executive.jsx   ← iframe → AI/BI dashboard
│                   ├── Operations.jsx  ← Reorder alerts + Order Now button
│                   ├── Platform.jsx    ← Pipeline health stats
│                   └── Architecture.jsx← Static diagram
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
      host: https://YOUR_WORKSPACE_HOST
      profile: DEFAULT
```

**`.databricksignore`** — create this BEFORE first deploy
```
src/app/frontend/node_modules/
src/app/frontend/src/
src/app/frontend/public/
src/app/frontend/package.json
src/app/frontend/package-lock.json
src/app/frontend/vite.config.js
src/app/frontend/index.html
src/app/app.py
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
```

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
    value: "YOUR_WAREHOUSE_ID"
  # Optional: configure email for Order Now button
  # - name: ORDER_EMAIL_TO
  #   value: "buyer@company.com"
  # - name: ORDER_EMAIL_FROM
  #   value: "replenishment@company.com"
  # - name: ORDER_EMAIL_PASSWORD
  #   value: "gmail-app-password"
```

**`src/app/main.py`** — includes 1-hour cache + Order Now email endpoint

```python
import os
import time
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

app = FastAPI()

WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "YOUR_WAREHOUSE_ID")
CACHE_TTL    = 3600  # 1 hour — survive a full demo without re-hitting the warehouse

_client = None
_cache: dict = {}  # { key: (fetched_at, result) }

def get_client():
    global _client
    if _client is None:
        _client = WorkspaceClient()   # Auto-reads DATABRICKS_HOST + DATABRICKS_TOKEN
    return _client

def cached(key: str, fn):
    now = time.time()
    if key in _cache and now - _cache[key][0] < CACHE_TTL:
        return _cache[key][1]
    result = fn()
    _cache[key] = (now, result)
    return result


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


# ── API routes ─────────────────────────────────────────────────────────────────

@app.get("/api/summary")
def summary():
    return cached("summary", _summary)

def _summary():
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
        "revenue_at_risk": int(float(rev[0]["rev"] or 0)),  # ROUND() returns float-string e.g. '4350213.0'
        "total_stores": int(counts[0]["stores"]),
        "total_skus": int(counts[0]["skus"]),
        "status_counts": [{"status": r["replenishment_status"], "count": int(r["cnt"]), "pct": float(r["pct"])} for r in status_rows],
    }


@app.get("/api/regional")
def regional():
    return cached("regional", _regional)

def _regional():
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
    return cached("top-alerts", _top_alerts)

def _top_alerts():
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
    return cached("categories", _categories)

def _categories():
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
    return cached("platform-stats", _platform_stats)

def _platform_stats():
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


# ── Order Now endpoint ─────────────────────────────────────────────────────────

class OrderRequest(BaseModel):
    store_id: str
    sku_id: str
    region: str = ""
    category: str = ""
    days_of_supply: float = 0
    inventory_on_hand: int = 0
    avg_daily_demand_7d: float = 0

@app.post("/api/order-sku")
def order_sku(req: OrderRequest):
    to_addr = os.environ.get("ORDER_EMAIL_TO", "")
    if to_addr:
        from_addr = os.environ.get("ORDER_EMAIL_FROM", "replenishment@retail-demo.com")
        password  = os.environ.get("ORDER_EMAIL_PASSWORD", "")
        smtp_host = os.environ.get("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))

        msg = MIMEMultipart()
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg["Subject"] = f"URGENT: Purchase Order — SKU {req.sku_id} · Store {req.store_id}"
        body = (
            f"AUTOMATED REPLENISHMENT ORDER\n{'─'*40}\n"
            f"Region:            {req.region}\n"
            f"Store:             {req.store_id}\n"
            f"SKU:               {req.sku_id}\n"
            f"Category:          {req.category}\n"
            f"Current Stock:     {req.inventory_on_hand} units\n"
            f"Days of Supply:    {req.days_of_supply} days\n"
            f"Avg Daily Demand:  {req.avg_daily_demand_7d} units/day\n\n"
            f"Status: REORDER NOW — stock critically low.\n"
            f"Triggered from the Retail Replenishment Intelligence platform."
        )
        msg.attach(MIMEText(body, "plain"))
        try:
            with smtplib.SMTP(smtp_host, smtp_port) as srv:
                srv.starttls()
                if password:
                    srv.login(from_addr, password)
                srv.sendmail(from_addr, to_addr, msg.as_string())
        except Exception:
            pass

    return {"ok": True, "store_id": req.store_id, "sku_id": req.sku_id}


# ── Serve React SPA ────────────────────────────────────────────────────────────
# Mount /assets BEFORE the catch-all route — order matters
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    return FileResponse("static/index.html")
```

---

### Step 6 · React Frontend

**`src/app/frontend/vite.config.js`**
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
export default defineConfig({
  plugins: [react()],
  build: { outDir: '../static', emptyOutDir: true },
  server: { proxy: { '/api': 'http://localhost:8000' } }
})
```

**`src/app/frontend/package.json`** (minimal)
```json
{
  "name": "retail-replenishment-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": { "dev": "vite", "build": "vite build" },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "recharts": "^2.13.0"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^5.4.19"
  }
}
```

**`src/app/frontend/src/App.jsx`** — data lifting + display:none tab switching

```jsx
import { useState, useEffect } from 'react'
import Executive from './components/Executive'
import Operations from './components/Operations'
import Platform from './components/Platform'
import Architecture from './components/Architecture'

const TABS = [
  { key: 'executive',    label: 'Executive Overview'      },
  { key: 'operations',   label: 'Operations Command Center'},
  { key: 'platform',     label: 'Platform & Governance'   },
  { key: 'architecture', label: 'Solution Architecture'   },
]

const DB_RED   = '#FF3621'
const HEADER_H = 64
const NAV_H    = 52

export default function App() {
  const [active, setActive] = useState('executive')

  // All data fetched ONCE at mount — never re-fetches on tab switch
  const [regional,  setRegional]  = useState(null)
  const [alerts,    setAlerts]    = useState(null)
  const [cats,      setCats]      = useState(null)
  const [platform,  setPlatform]  = useState(null)
  const [errors,    setErrors]    = useState({})

  useEffect(() => {
    const load = (url, setter, key) =>
      fetch(url)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
        .then(setter)
        .catch(e => setErrors(prev => ({ ...prev, [key]: e.message })))

    load('/api/regional',       setRegional, 'regional')
    load('/api/top-alerts',     setAlerts,   'alerts')
    load('/api/categories',     setCats,     'cats')
    load('/api/platform-stats', setPlatform, 'platform')
  }, [])  // empty dep array — runs once only

  return (
    <div style={{ fontFamily: "'Segoe UI', system-ui, sans-serif", height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ height: HEADER_H, padding: '0 32px', display: 'flex', alignItems: 'center', borderBottom: '1px solid #e0e0e0', background: '#fff', flexShrink: 0 }}>
        <div>
          <div style={{ fontSize: 18, fontWeight: 700, color: DB_RED }}>Retail Replenishment Intelligence</div>
          <div style={{ fontSize: 12, color: '#888', marginTop: 2 }}>800-Store Demand Signal Platform · Powered by Databricks</div>
        </div>
      </div>

      {/* Nav */}
      <div style={{ height: NAV_H, padding: '0 32px', display: 'flex', alignItems: 'center', background: '#fafafa', borderBottom: '1px solid #e0e0e0', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setActive(t.key)} style={{
              padding: '7px 18px', cursor: 'pointer', borderRadius: 4, fontSize: 13, fontWeight: 600,
              border: `1.5px solid ${DB_RED}`,
              background: active === t.key ? DB_RED : '#fff',
              color:      active === t.key ? '#fff' : DB_RED,
              transition: 'all 0.15s',
            }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content — all tabs rendered but only active one visible */}
      {/* display:none keeps components mounted — iframe stays loaded, no data re-fetch */}
      <div style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
        <div style={{ display: active === 'executive'    ? 'block' : 'none', height: '100%' }}><Executive /></div>
        <div style={{ display: active === 'operations'   ? 'block' : 'none', height: '100%' }}><Operations alerts={alerts} regional={regional} cats={cats} error={errors.alerts || errors.regional} /></div>
        <div style={{ display: active === 'platform'     ? 'block' : 'none', height: '100%' }}><Platform   data={platform} error={errors.platform} /></div>
        <div style={{ display: active === 'architecture' ? 'block' : 'none', height: '100%' }}><Architecture /></div>
      </div>

    </div>
  )
}
```

**`src/app/frontend/src/components/Executive.jsx`** — Lakeview iframe
```jsx
export default function Executive() {
  return (
    <iframe
      src="https://YOUR_WORKSPACE_HOST/embed/dashboardsv3/YOUR_DASHBOARD_ID?o=YOUR_ORG_ID"
      width="100%" height="100%" frameBorder="0"
      allow="clipboard-write" style={{ display: 'block', border: 'none' }}
    />
  )
}
```

**Props-based component pattern** (Operations, Platform):
```jsx
// Components receive data as props — no useEffect, no internal fetch
export default function Operations({ alerts, regional, cats, error }) {
  if (error)  return <div style={{ padding: 40, color: '#e74c3c' }}>Error: {error}</div>
  if (!alerts) return <div style={{ padding: 40, color: '#888' }}>Loading...</div>
  // ... render charts and table
}
```

**Build command** (run before every deploy):
```bash
cd src/app/frontend && npm install && npm run build && cd ../../..
```
Build output (`src/app/static/`) is committed to the repo and deployed to the workspace.

---

### Step 7 · Grant App Service Principal Permissions

After first `databricks bundle run replenishment_app`, the app creates a service principal.
Get its UUID and grant Unity Catalog access:

```bash
# Get SP UUID
databricks apps get retail-replenishment --profile DEFAULT | python -c "import sys,json; d=json.load(sys.stdin); print(d['oauth2_app_client_id'])"
```

Then run in a Databricks SQL worksheet (replace UUID):
```sql
GRANT USE CATALOG ON CATALOG retail_intelligence TO `<sp-uuid>`;
GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `<sp-uuid>`;
GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `<sp-uuid>`;
```

Or via Python SDK:
```python
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

w = WorkspaceClient(profile='DEFAULT')
sp_uuid = "<paste-from-databricks-apps-get-output>"

for stmt in [
    f"GRANT USE CATALOG ON CATALOG retail_intelligence TO `{sp_uuid}`",
    f"GRANT USE SCHEMA ON SCHEMA retail_intelligence.retail_data TO `{sp_uuid}`",
    f"GRANT SELECT ON SCHEMA retail_intelligence.retail_data TO `{sp_uuid}`",
]:
    r = w.statement_execution.execute_statement(
        warehouse_id='YOUR_WAREHOUSE_ID', statement=stmt, wait_timeout='30s'
    )
    print(r.status.state, stmt[:60])
```

---

### Step 8 · Full Deployment Sequence

```bash
# 1. Build React (run once, or after any frontend change)
cd src/app/frontend && npm install && npm run build && cd ../../..

# 2. Deploy all resources via DABs
databricks bundle deploy --auto-approve --profile DEFAULT

# 3. Run data generation job
databricks bundle run data_gen_job --profile DEFAULT

# 4. Run DLT pipeline (kicks off in background — takes ~10 min)
databricks bundle run replenishment_pipeline --profile DEFAULT

# 5. Start app
databricks bundle run replenishment_app --profile DEFAULT

# 6. Grant SP permissions (first time only — get UUID first, then SQL grants above)

# 7. Restart app to pick up new permissions
databricks bundle run replenishment_app --profile DEFAULT

# 8. Verify all 4 tabs load correctly
```

---

### Step 9 · KPI Validation Queries

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

## Time Budget (~45 min build)

| # | Task | Time |
|---|------|------|
| 1 | `databricks bundle deploy` — deploys all resources | 2 min |
| 2 | `databricks bundle run data_gen_job` — generates 150K POS rows | 5 min |
| 3 | `databricks bundle run replenishment_pipeline` — kick off DLT (background) | 10 min to complete |
| 4 | `npm install && npm run build` | 3 min |
| 5 | `databricks bundle run replenishment_app` — first deploy | 3 min |
| 6 | Get SP UUID + run GRANT statements | 3 min |
| 7 | Restart app + verify all 4 tabs | 4 min |
| **Total** | | **~30 min** |

> DLT runs in background while you do steps 4–6. By the time you restart the app, gold table is ready.

---

## Demo Script Cues

| Moment | Line |
|--------|------|
| DLT lineage graph | "End-to-end lineage, built in. One click — this is Unity Catalog's answer to the CTO's governance question." |
| Gold signal table | "One row per store per SKU. Days of supply, calculated daily across 5,000 combinations — scales to 160K at 800 stores." |
| REORDER NOW rows | "These stores stock out tomorrow. Their Excel model wouldn't flag this until Monday's report." |
| Revenue at risk tile | "$4.35M weekly — this is the dollar value of the problem we just quantified, before any optimization." |
| App tab switch | "Each stakeholder gets their own view — one URL, all audiences, zero separate tools." |
| Order Now button | "One click triggers a purchase order email. No ERP integration needed for the demo." |
| Architecture tab | "POS to signal in three DLT steps. Streaming-ready — one line change in the bronze layer." |
| CTO question | "Snowflake needs a separate BI tool, separate governance layer, separate orchestrator. This is one workspace." |

---

## Troubleshooting

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| `INTERNAL_ERROR` on job/pipeline run | `environment_key`/`environments`/`client:"1"` in YAML | Remove those fields — Free Edition infers serverless |
| App 500 on all API routes — "no free port" | `databricks-sql-connector` OAuth loop | Switch to `databricks-sdk` in `requirements.txt` + `main.py` |
| `ValueError: invalid literal for int()` | SDK returns all values as strings; `ROUND()` → `'4350213.0'` | Use `int(float(x))` for any SQL ROUND/SUM result |
| Deployment stuck "Preparing source code" | `node_modules` in workspace from previous deploy | Delete via `databricks workspace delete --recursive .../frontend`, then redeploy |
| Permission denied on API routes | App SP not granted Unity Catalog access | Run GRANT statements using SP's UUID (not display name) |
| SP GRANT fails "principal not found" | Used display name instead of UUID | Use `oauth2_app_client_id` from `databricks apps get` |
| App still serving old version | Stale deployment | `databricks bundle run replenishment_app` |
| Tab switch causes 2-second reload | Components unmounting/remounting on each click | Use `display:none/block` not conditional rendering |
| iframe reloads on every tab switch | iframe component unmounting | Ensure `display:none/block` pattern — never `{active === 'x' && <Component/>}` |
| OAuth 401 on curl test | Databricks Apps requires browser OAuth for all routes | Expected — test via browser, not curl |
