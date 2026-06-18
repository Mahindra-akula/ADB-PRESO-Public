import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import StatementState

app = FastAPI()

WAREHOUSE_ID = os.environ.get("WAREHOUSE_ID", "4e7b8de25b26878f")

# SDK auto-reads DATABRICKS_HOST + DATABRICKS_TOKEN (or M2M OAuth) from environment
_client = None

def get_client():
    global _client
    if _client is None:
        _client = WorkspaceClient()
    return _client


def query(sql_text: str):
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
    status_rows = query("""
        SELECT replenishment_status,
               COUNT(*) AS cnt,
               ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1) AS pct
        FROM retail_intelligence.retail_data.replenishment_signals
        GROUP BY replenishment_status
        ORDER BY cnt DESC
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
        "revenue_at_risk": int(float(rev[0]["rev"] or 0)),
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
        GROUP BY s.region, r.replenishment_status
        ORDER BY s.region
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
        ORDER BY r.days_of_supply ASC
        LIMIT 25
    """)


@app.get("/api/categories")
def categories():
    return query("""
        SELECT k.category,
               COUNT(*) AS stores_at_risk,
               ROUND(AVG(r.days_of_supply), 1) AS avg_days_supply
        FROM retail_intelligence.retail_data.replenishment_signals r
        JOIN retail_intelligence.retail_data.skus k USING (sku_id)
        WHERE r.replenishment_status = 'REORDER NOW'
        GROUP BY k.category
        ORDER BY stores_at_risk DESC
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


# ── Serve React SPA ────────────────────────────────────────────────────────────
app.mount("/assets", StaticFiles(directory="static/assets"), name="assets")

@app.get("/{full_path:path}")
def serve_spa(full_path: str):
    return FileResponse("static/index.html")
