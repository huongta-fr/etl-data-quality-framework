# End-to-End Automated Data Quality & ETL Testing Framework

## Project Overview

Automated data quality and ETL testing framework
for an e-commerce data platform.

## Technology

- Python
- Pytest
- PostgreSQL
- Docker
- SQL
- Pandas

## Project Status

Day 1 - Environment and infrastructure setup
### Python virtual environment

In project:
python -m venv .venv

Activate.
Windows
.venv\Scripts\activate
macOS/Linux
source .venv/bin/activate

Install package:
pip install -r requirements.txt

Day 3
erDiagram

    CUSTOMER ||--o{ ORDER : places

    ORDER ||--|{ ORDER_ITEM : contains

    PRODUCT ||--o{ ORDER_ITEM : included_in

    ORDER ||--o{ PAYMENT : has

    CUSTOMER {
        int customer_id PK
        string first_name
        string last_name
        string email
        string phone
        string status
        datetime created_at
    }

    PRODUCT {
        int product_id PK
        string product_name
        string category
        decimal price
        int stock_quantity
        string status
        datetime created_at
    }

    ORDER {
        int order_id PK
        int customer_id FK
        datetime order_date
        string status
        decimal total_amount
    }

    ORDER_ITEM {
        int order_item_id PK
        int order_id FK
        int product_id FK
        int quantity
        decimal unit_price
    }

    PAYMENT {
        int payment_id PK
        int order_id FK
        datetime payment_date
        string payment_method
        decimal amount
        string status
        string transaction_id
    }