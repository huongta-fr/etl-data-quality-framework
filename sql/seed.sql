INSERT INTO customer
(customer_id, first_name, last_name, email, phone, status, created_at)
VALUES
(1, 'Alice', 'Martin', 'alice@example.com', '0600000001', 'ACTIVE', '2026-09-01 10:00:00'),
(2, 'Bob', 'Dupont', 'bob@example.com', '0600000002', 'ACTIVE', '2026-09-02 11:00:00'),
(3, 'Claire', 'Bernard', 'claire@example.com', '0600000003', 'INACTIVE', '2026-09-03 12:00:00');


INSERT INTO product
(product_id, product_name, category, price, stock_quantity, status, created_at)
VALUES
(101, 'Laptop', 'Electronics', 999.99, 10, 'ACTIVE', '2026-09-01 09:00:00'),
(102, 'Mouse', 'Electronics', 29.99, 100, 'ACTIVE', '2026-09-01 09:10:00'),
(103, 'Keyboard', 'Electronics', 79.99, 50, 'ACTIVE', '2026-09-01 09:20:00');


INSERT INTO "order"
(order_id, customer_id, order_date, status, total_amount)
VALUES
(1001, 1, '2026-09-10 14:00:00', 'COMPLETED', 1029.98),
(1002, 2, '2026-09-11 15:30:00', 'COMPLETED', 109.98);


INSERT INTO order_item
(order_item_id, order_id, product_id, quantity, unit_price)
VALUES
(1, 1001, 101, 1, 999.99),
(2, 1001, 102, 1, 29.99),
(3, 1002, 103, 1, 79.99),
(4, 1002, 102, 1, 29.99);


INSERT INTO payment
(payment_id, order_id, payment_date, payment_method, amount, status, transaction_id)
VALUES
(5001, 1001, '2026-09-10 14:05:00', 'CARD', 1029.98, 'SUCCESS', 'TXN-10001'),
(5002, 1002, '2026-09-11 15:35:00', 'PAYPAL', 109.98, 'SUCCESS', 'TXN-10002');