-- customers(customer_id, name, email)
-- payments(payment_id, order_id, amount, payment_status)
-- orders(order_id, customer_id, order_date, total_amount, status)

-- CHECK SIZE OF TABLES
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

-- Check for customers with at least one order but all order does not have payments
SELECT
    c.customer_id
FROM customers c
JOIN orders o
    ON c.customer_id = o.customer_id
LEFT JOIN payments p
    ON o.order_id = p.order_id
GROUP BY c.customer_id
HAVING COUNT(p.payment_id) = 0;

-- Check for customers with more than one order
SELECT
    c.customer_id
FROM customers c
LEFT JOIN orders o
    ON c.customer_id = o.customer_id
GROUP BY c.customer_id
HAVING COUNT(o.order_id) > 1; 


# Delete all data in the tables
TRUNCATE TABLE
    customer,
    product,
    "order",
    order_item,
    payment
RESTART IDENTITY CASCADE;