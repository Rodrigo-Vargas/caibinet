-- Monthly revenue by product
SELECT
    DATE_TRUNC('month', sale_date)  AS month,
    product_name,
    SUM(amount)                     AS total_revenue,
    COUNT(*)                        AS transactions
FROM sales
WHERE sale_date >= '2025-01-01'
GROUP BY 1, 2
ORDER BY 1, 3 DESC;
