# Skill: Databricks App — React + FastAPI + Databricks SDK

A reusable, proven pattern for building multi-tab Databricks Apps with live SQL data, embedded dashboards, and automatic service principal auth. Based on the Retail Replenishment Intelligence SA demo — built and deployed to production.

**When to use this over Dash/Streamlit:**
- You need custom charts (Recharts, D3) beyond what AI/BI dashboards support
- You want a single self-contained deployment at one URL for multiple audiences
- You need action endpoints (Order Now, Send Alert) not just read-only views
- Dashboards block iframe embedding via X-Frame-Options (use `<iframe>` for AI/BI Lakeview instead)

---

## Stack

| Layer | Choice | Why |
|-------|--------|-----|
| Frontend | React 18 + Vite + Recharts | Fast build, rich charts, small bundle |
| Backend | FastAPI + uvicorn | Async, lightweight, serves React SPA |
| Auth | `databricks-sdk` `WorkspaceClient()` | Auto-reads injected token; sql-connector fails |
| Data | `statement_execution` API | REST-based, works with SP M2M auth |
| Deployment | Databricks Asset Bundles (DABs) | Single command, handles App lifecycle |
| Cache | Python `time.time()` dict | 1-hour TTL — demo survives without warehouse re-hits |

---

## File Structure

```
project/
├── databricks.yml
├── .databricksignore          ← CRITICAL: exclude node_modules BEFORE first deploy
├── resources/
│   └── my_app.yml
└── src/
    └── app/
        ├── app.yaml           ← uvicorn command + env vars
        ├── main.py            ← FastAPI backend + 1-hour cache
        ├── requirements.txt   ← fastapi uvicorn[standard] databricks-sdk
        ├── static/            ← React build output (committed + deployed)
        └── frontend/          ← React source (excluded from deploy)
            ├── package.json
            ├── vite.config.js
            └── src/
                ├── App.jsx    ← data lifting + display:none tabs
                └── components/
```

---

## Checklist: New App

### 1 · `.databricksignore` — create this BEFORE first deploy
```
src/app/frontend/node_modules/
src/app/frontend/src/
src/app/frontend/public/
src/app/frontend/package.json
src/app/frontend/package-lock.json
src/app/frontend/vite.config.js
src/app/frontend/index.html
```
**Why:** `node_modules` is 57MB+. Without this, `bundle deploy` uploads the full npm tree and either stalls "Preparing source code" forever or causes `RESOURCE_DOES_NOT_EXIST` errors mid-deploy.

### 2 · `resources/my_app.yml`
```yaml
resources:
  apps:
    my_app:
      name: "my-app-name"          # Must be unique in workspace
      description: "My App"
      source_code_path: ../src/app
```

### 3 · `src/app/app.yaml`
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
    value: "your-warehouse-id"
  - name: CATALOG
    value: "your_catalog"
  - name: SCHEMA
    value: "your_schema"
```

### 4 · `src/app/requirements.txt`
```
fastapi
uvicorn[standard]
databricks-sdk
```
**Never use** `databricks-sql-connector` in Apps — it tries OAuth browser flow and crashes with "no free port".

### 5 · `src/app/main.py` — complete template with cache

```python
import os
import time

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

app = FastAPI()

WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "fallback-id")
CATALOG      = os.environ.get("CATALOG", "my_catalog")
SCHEMA       = os.environ.get("SCHEMA", "my_schema")
CACHE_TTL    = 3600  # 1 hour — data doesn't change during a demo

_client = None
_cache: dict = {}

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


def query(sql_text: str) -> list[dict]:
    """Execute SQL via statement execution API.
    IMPORTANT: All returned values are STRINGS regardless of SQL type.
    Cast explicitly: int(float(x)) for ROUND/SUM, int(x) for COUNT."""
    result = get_client().statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql_text,
        wait_timeout="50s",
    )
    if result.status.state != StatementState.SUCCEEDED:
        err = result.status.error
        raise RuntimeError(f"Query failed: {err.message if err else result.status.state}")
    cols = [col.name for col in result.manifest.schema.columns]
    return [dict(zip(cols, row)) for row in (result.result.data_array or [])]


# ── Your API routes ────────────────────────────────────────────────────────────

@app.get("/api/example")
def example():
    return cached("example", _example)

def _example():
    rows = query(f"SELECT id, COUNT(*) AS cnt FROM {CATALOG}.{SCHEMA}.my_table GROUP BY id")
    return [{"id": r["id"], "count": int(r["cnt"])} for r in rows]


# ── Serve React SPA — order matters ───────────────────────────────────────────
# Mount /assets BEFORE the catch-all or it will never be reached
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    return FileResponse("static/index.html")
```

### 6 · `src/app/frontend/vite.config.js`
```js
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../static',    // Output lands in src/app/static/ — deployed to workspace
    emptyOutDir: true,
  },
  server: {
    proxy: { '/api': 'http://localhost:8000' }  // Dev: proxy API to local FastAPI
  }
})
```

### 7 · `src/app/frontend/package.json` (minimal)
```json
{
  "name": "app-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
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

---

## React Patterns

### App.jsx — Data Lifting + display:none Tab Switching

The two critical patterns for a smooth demo:

1. **Data lifting**: fetch all API data ONCE in App.jsx on mount, pass as props. Eliminates 2-second reload on every tab click.
2. **display:none/block**: keep all tab components mounted at all times. Prevents iframe reload, preserves component state.

```jsx
import { useState, useEffect } from 'react'
import Executive from './components/Executive'
import Operations from './components/Operations'

const TABS = [
  { key: 'executive',  label: 'Executive Overview'  },
  { key: 'operations', label: 'Ops Command Center'  },
]

const DB_RED = '#FF3621'

export default function App() {
  const [active, setActive] = useState('executive')

  // All data fetched ONCE — never refetched on tab switch
  const [alerts,  setAlerts]  = useState(null)
  const [errors,  setErrors]  = useState({})

  useEffect(() => {
    const load = (url, setter, key) =>
      fetch(url)
        .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
        .then(setter)
        .catch(e => setErrors(prev => ({ ...prev, [key]: e.message })))

    load('/api/top-alerts', setAlerts, 'alerts')
    // add more endpoints here
  }, [])  // empty dep array — runs once only

  return (
    <div style={{ fontFamily: 'system-ui, sans-serif', height: '100vh', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

      {/* Header */}
      <div style={{ padding: '0 32px', height: 64, display: 'flex', alignItems: 'center', borderBottom: '1px solid #eee', flexShrink: 0 }}>
        <div style={{ fontSize: 18, fontWeight: 700, color: DB_RED }}>App Title</div>
      </div>

      {/* Nav */}
      <div style={{ padding: '0 32px', height: 52, display: 'flex', alignItems: 'center', background: '#fafafa', borderBottom: '1px solid #eee', flexShrink: 0 }}>
        <div style={{ display: 'flex', gap: 8 }}>
          {TABS.map(t => (
            <button key={t.key} onClick={() => setActive(t.key)} style={{
              padding: '7px 18px', borderRadius: 4, cursor: 'pointer', fontWeight: 600, fontSize: 13,
              border: `1.5px solid ${DB_RED}`,
              background: active === t.key ? DB_RED : '#fff',
              color:      active === t.key ? '#fff' : DB_RED,
            }}>
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {/* Content — all tabs mounted, only active one visible */}
      {/* display:none keeps iframe loaded and avoids re-fetching data */}
      <div style={{ flex: 1, overflow: 'auto' }}>
        <div style={{ display: active === 'executive'  ? 'block' : 'none', height: '100%' }}><Executive /></div>
        <div style={{ display: active === 'operations' ? 'block' : 'none', height: '100%' }}><Operations alerts={alerts} error={errors.alerts} /></div>
      </div>

    </div>
  )
}
```

### Props-based Component Pattern

Components receive data as props — no `useEffect`, no internal fetch, no loading state of their own.

```jsx
export default function Operations({ alerts, error }) {
  if (error)   return <div style={{ padding: 40, color: '#e74c3c' }}>Error: {error}</div>
  if (!alerts) return <div style={{ padding: 40, color: '#888' }}>Loading...</div>

  return (
    <div style={{ padding: '32px 48px' }}>
      {/* render alerts */}
    </div>
  )
}
```

### Lakeview Dashboard Embedding (iframe tab)

```jsx
export default function Executive() {
  return (
    <iframe
      src="https://YOUR_HOST/embed/dashboardsv3/YOUR_DASHBOARD_ID?o=YOUR_ORG_ID"
      width="100%" height="100%" frameBorder="0"
      allow="clipboard-write" style={{ display: 'block', border: 'none' }}
    />
  )
}
```

The `display:none/block` tab pattern keeps this iframe mounted — it only loads once, not on every tab click. After editing the dashboard in the UI, click **Publish** — the iframe auto-refreshes on next page load.

---

## Type Conversion Reference

The `statement_execution` API returns **all values as strings** in `data_array`. Always cast:

```python
# SQL COUNT(*) → '100'
int(row["count"])

# SQL ROUND(SUM(...), 0) → '4350213.0'  — int() fails! Use float() first
int(float(row["revenue"]))

# SQL ROUND(val, 1) → '79.1'
float(row["pct"])

# SQL MAX(date) → '2026-06-18'
str(row["last_updated"])
```

---

## Order Now / Action Endpoint Pattern

For demo "wow" moments — trigger a real email from a button click:

```python
# In main.py — add these imports
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pydantic import BaseModel

class OrderRequest(BaseModel):
    store_id: str
    sku_id: str
    region: str = ""
    category: str = ""

@app.post("/api/order-sku")
def order_sku(req: OrderRequest):
    to_addr = os.environ.get("ORDER_EMAIL_TO", "")
    if to_addr:
        from_addr = os.environ.get("ORDER_EMAIL_FROM", "")
        password  = os.environ.get("ORDER_EMAIL_PASSWORD", "")
        msg = MIMEMultipart()
        msg["From"] = from_addr
        msg["To"]   = to_addr
        msg["Subject"] = f"URGENT: Purchase Order — SKU {req.sku_id} · Store {req.store_id}"
        msg.attach(MIMEText(f"Replenishment order triggered for {req.store_id} / {req.sku_id}", "plain"))
        try:
            with smtplib.SMTP("smtp.gmail.com", 587) as srv:
                srv.starttls()
                srv.login(from_addr, password)
                srv.sendmail(from_addr, to_addr, msg.as_string())
        except Exception:
            pass
    return {"ok": True, "store_id": req.store_id, "sku_id": req.sku_id}
```

Configure via `app.yaml` env vars:
```yaml
env:
  - name: ORDER_EMAIL_TO
    value: "buyer@company.com"
  - name: ORDER_EMAIL_FROM
    value: "replenishment@company.com"
  - name: ORDER_EMAIL_PASSWORD
    value: "gmail-app-password"  # myaccount.google.com/apppasswords
```

If `ORDER_EMAIL_TO` is not set, endpoint returns `{"ok": true}` silently — safe for demo without email config.

---

## Unity Catalog Grants for App Service Principal

The App creates its own service principal. Grant it access **after** the first `bundle run`:

```bash
# Get the SP UUID
databricks apps get my-app-name --profile DEFAULT | python -c "import sys,json; print(json.load(sys.stdin)['oauth2_app_client_id'])"
```

```sql
-- Run in Databricks SQL worksheet — use UUID, never display name
GRANT USE CATALOG ON CATALOG my_catalog TO `<sp-uuid>`;
GRANT USE SCHEMA ON SCHEMA my_catalog.my_schema TO `<sp-uuid>`;
GRANT SELECT ON SCHEMA my_catalog.my_schema TO `<sp-uuid>`;
```

UUID is stable across redeploys — you only need to do this once.

---

## Deployment Sequence

```bash
# 1. Build frontend (after any React changes — required before every deploy)
cd src/app/frontend && npm install && npm run build && cd ../../..

# 2. Deploy resources (fast — node_modules excluded by .databricksignore)
databricks bundle deploy --auto-approve --profile DEFAULT

# 3. Start the app
databricks bundle run my_app --profile DEFAULT

# 4. First time only: grant SP permissions (get UUID, run grants, restart)
databricks bundle run my_app --profile DEFAULT

# 5. Check logs
databricks apps logs my-app-name --profile DEFAULT | tail -30
```

**Key log lines that confirm success:**
```
[SYSTEM] Starting app with command: uvicorn main:app --host 0.0.0.0 --port 8000
[APP]    Uvicorn running on http://0.0.0.0:8000
[SYSTEM] Deployment successful
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Deploy stuck "Preparing source code" | `node_modules` uploaded before `.databricksignore` existed | `databricks workspace delete --recursive .../frontend` then redeploy |
| `ValueError: invalid literal for int()` | SQL `ROUND()`/`SUM()` returns float-string like `'4350213.0'` | Use `int(float(x))` |
| 500 on all API routes — "no free port" | `databricks-sql-connector` tries OAuth browser auth | Replace with `databricks-sdk` |
| 500 — Permission denied on queries | App SP lacks Unity Catalog grants | Run GRANT statements with SP UUID |
| App shows old version after redeploy | New files deployed but app not restarted | `databricks bundle run <app_resource_key>` |
| `curl` returns 401 | Databricks Apps requires browser OAuth for all routes | Expected — test in browser only |
| SP GRANT fails "principal not found" | Used display name instead of UUID | Use `oauth2_app_client_id` from `databricks apps get` |
| 2-second reload on tab switch | Components unmounting/remounting on each click | Use `display:none/block`, not `{active === 'x' && <Component/>}` |
| iframe reloads on every tab switch | iframe unmounting due to conditional render | `display:none/block` keeps all components mounted |
| Free Edition `INTERNAL_ERROR` on jobs | `environment_key` / `environments` / `client:"1"` in YAML | Remove those fields entirely — serverless is inferred |
