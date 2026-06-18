-- Databricks notebook source
-- 01_kpi_validation.sql — Run after DLT pipeline. Each query is a live demo moment.

-- COMMAND ----------
-- DEMO: "Current stockout rate across all stores"
SELECT
    replenishment_status,
    COUNT(*)                                                   AS store_sku_combos,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 1)        AS pct_of_total
FROM retail_intelligence.retail_data.replenishment_signals
GROUP BY replenishment_status
ORDER BY store_sku_combos DESC;

-- COMMAND ----------
-- DEMO: "Which categories are putting the most stores at risk?"
SELECT
    k.category,
    COUNT(*)                         AS stores_at_risk,
    ROUND(AVG(r.days_of_supply), 1) AS avg_days_supply,
    ROUND(AVG(k.avg_unit_price), 2) AS unit_price
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.skus k USING (sku_id)
WHERE r.replenishment_status = 'REORDER NOW'
GROUP BY k.category
ORDER BY stores_at_risk DESC;

-- COMMAND ----------
-- DEMO: "Regional breakdown — where are the trucks needed most?"
SELECT
    s.region,
    r.replenishment_status,
    COUNT(*) AS combos
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.stores s USING (store_id)
GROUP BY s.region, r.replenishment_status
ORDER BY s.region, r.replenishment_status;

-- COMMAND ----------
-- DEMO: "Weekly revenue at risk from current stockouts"
SELECT
    ROUND(SUM(r.avg_daily_demand_7d * k.avg_unit_price * 7), 0) AS weekly_revenue_at_risk
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.skus k USING (sku_id)
WHERE r.replenishment_status = 'REORDER NOW';

-- COMMAND ----------
-- DEMO: "Top 10 most urgent store+SKU reorder alerts"
SELECT
    s.region, r.store_id, k.category, r.sku_id,
    r.days_of_supply, r.inventory_on_hand, r.avg_daily_demand_7d
FROM retail_intelligence.retail_data.replenishment_signals r
JOIN retail_intelligence.retail_data.stores s USING (store_id)
JOIN retail_intelligence.retail_data.skus   k USING (sku_id)
WHERE r.replenishment_status = 'REORDER NOW'
ORDER BY r.days_of_supply ASC
LIMIT 10;
