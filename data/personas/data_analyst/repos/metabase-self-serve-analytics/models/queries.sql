-- Metabase native question
CREATE INDEX CONCURRENTLY
SELECT customer_id, SUM(amount) OVER (PARTITION BY region)
