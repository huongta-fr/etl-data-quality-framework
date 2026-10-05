CREATE TABLE customer (
    customer_id INTEGER PRIMARY KEY,
    first_name VARCHAR(100) NOT NULL,
    last_name VARCHAR(100) NOT NULL,
    email VARCHAR(255) NOT NULL,
    phone VARCHAR(50),
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE product (
    product_id INTEGER PRIMARY KEY,
    product_name VARCHAR(255) NOT NULL,
    category VARCHAR(100),
    price NUMERIC(10, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE "order" (
    order_id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    order_date TIMESTAMP NOT NULL,
    status VARCHAR(30) NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,

    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(customer_id)
);

CREATE TABLE order_item (
    order_item_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    product_id INTEGER NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL,

    CONSTRAINT fk_order_item_order
        FOREIGN KEY (order_id)
        REFERENCES "order"(order_id),

    CONSTRAINT fk_order_item_product
        FOREIGN KEY (product_id)
        REFERENCES product(product_id)
);

CREATE TABLE payment (
    payment_id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL,
    payment_date TIMESTAMP NOT NULL,
    payment_method VARCHAR(50) NOT NULL,
    amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(30) NOT NULL,
    transaction_id VARCHAR(100),

    CONSTRAINT fk_payment_order
        FOREIGN KEY (order_id)
        REFERENCES "order"(order_id)
);