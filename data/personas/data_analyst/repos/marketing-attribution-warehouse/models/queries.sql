SELECT customer_id, SUM(amount) OVER (PARTITION BY region)
{{ config(materialized='incremental') }}
-- Looker Studio blended data source
