SELECT 'customer' AS table_name, COUNT(*) AS row_count
FROM customer

UNION ALL

SELECT 'product', COUNT(*)
FROM product

UNION ALL

SELECT 'order', COUNT(*)
FROM "order"

UNION ALL

SELECT 'order_item', COUNT(*)
FROM order_item

UNION ALL

SELECT 'payment', COUNT(*)
FROM payment;