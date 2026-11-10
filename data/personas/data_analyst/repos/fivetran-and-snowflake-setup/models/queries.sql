{{ config(materialized='incremental') }}
SELECT customer_id, SUM(amount) OVER (PARTITION BY region)
