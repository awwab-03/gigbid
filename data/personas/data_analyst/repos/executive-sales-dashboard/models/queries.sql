SELECT customer_id, SUM(amount) OVER (PARTITION BY region)
-- dashboard KPI tiles
