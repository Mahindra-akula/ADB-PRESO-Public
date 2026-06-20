# Genie Space — Seed Questions

**Space ID:** `01f16817409719d09c80a762fa6a01bf`  
**Tables:** All in `retail_intelligence.retail_data` schema  
- `retail_intelligence.retail_data.replenishment_signals` — Gold: status (REORDER NOW / WATCH / OK) per store+SKU
- `retail_intelligence.retail_data.pos_store_sku_signals` — Silver: 7 & 14-day rolling demand per store+SKU
- `retail_intelligence.retail_data.stores` — 100 stores, region, state
- `retail_intelligence.retail_data.skus` — 50 SKUs, category, avg_unit_price

> **Note:** Schema is `retail_data`, NOT `gold`/`silver`/`bronze`. All layers land in one schema.

---

## Ops Team Questions
- Which stores have the most SKUs at risk of stockout today?
- Show me the top 10 SKUs with less than 3 days of supply.
- Which stores in the Northeast need a replenishment order today?
- What is the average days of supply across all stores right now?
- Which stores have zero inventory on hand for any SKU?

## Business Leader Questions
- What is the current stockout rate across all stores?
- What is the estimated weekly revenue at risk from current stockouts?
- Which product category has the highest stockout rate?
- How many stores are in REORDER NOW status right now?

## Regional Manager Questions
- Which region has the most stores on REORDER NOW status?
- Compare stockout rates between the Southwest and West regions.
- How many stores in Texas are below 3 days of supply?
- Show me the top 5 stores by revenue at risk in the Southeast region.

## CTO / Data Questions
- How many store and SKU combinations are being tracked?
- What is the distribution of replenishment status across all combinations?
- When was the last signal generated for store 1?
- Which SKUs have the highest average daily demand across all stores?
