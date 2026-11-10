COPY sales FROM 's3://
SELECT customer_id, SUM(amount) OVER (PARTITION BY region)
