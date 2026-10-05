from pathlib import Path
import json
import random
from datetime import datetime

import pandas as pd
import yaml
from faker import Faker


CONFIG_PATH = Path("config/gen_data.yaml")


def load_config(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def setup_random_seed(seed: int):
    random.seed(seed)
    Faker.seed(seed)


def generate_customers(config: dict, fake: Faker) -> pd.DataFrame:
    n = config["dataset"]["customers"]
    statuses = config["statuses"]["customer"]

    rows = []

    for customer_id in range(1, n + 1):
        rows.append({
            "customer_id": customer_id,
            "first_name": fake.first_name(),
            "last_name": fake.last_name(),
            "email": fake.unique.email(),
            "phone": fake.phone_number(),
            "status": random.choice(statuses),
            "created_at": fake.date_time_between(
                start_date="-2y",
                end_date="now"
            )
        })

    return pd.DataFrame(rows)


def generate_products(config: dict, fake: Faker) -> pd.DataFrame:
    n = config["dataset"]["products"]

    product_config = config["generation"]["product"]
    statuses = config["statuses"]["product"]

    categories = [
        "Electronics",
        "Home",
        "Books",
        "Clothing",
        "Sports",
        "Beauty"
    ]

    rows = []

    for product_id in range(1, n + 1):
        rows.append({
            "product_id": product_id,
            "product_name": fake.catch_phrase(),
            "category": random.choice(categories),
            "price": round(
                random.uniform(
                    product_config["min_price"],
                    product_config["max_price"]
                ),
                2
            ),
            "stock_quantity": random.randint(
                product_config["min_stock"],
                product_config["max_stock"]
            ),
            "status": random.choice(statuses),
            "created_at": fake.date_time_between(
                start_date="-2y",
                end_date="now"
            )
        })

    return pd.DataFrame(rows)


def generate_orders(
    config: dict,
    fake: Faker,
    customers: pd.DataFrame
) -> pd.DataFrame:

    n = config["dataset"]["orders"]
    order_config = config["generation"]["order"]
    statuses = config["statuses"]["order"]

    customer_ids = customers["customer_id"].drop_duplicates().tolist()

    # Parse date strings to datetime objects
    start_date = datetime.strptime(
        order_config["start_date"],
        "%Y-%m-%d"
    )
    end_date = datetime.strptime(
        order_config["end_date"],
        "%Y-%m-%d"
    )

    rows = []

    for order_id in range(1, n + 1):
        rows.append({
            "order_id": order_id,
            "customer_id": random.choice(customer_ids),
            "order_date": fake.date_time_between(
                start_date=start_date,
                end_date=end_date
            ),
            "status": random.choice(statuses),
            "total_amount": 0.0
        })

    return pd.DataFrame(rows)


def generate_order_items(
    config: dict,
    orders: pd.DataFrame,
    products: pd.DataFrame
):
    item_config = config["generation"]["order_items"]

    product_lookup = products.set_index("product_id")["price"].to_dict()
    product_ids = list(product_lookup.keys())

    rows = []
    order_totals = {}

    order_item_id = 1

    for order_id in orders["order_id"]:

        number_of_items = random.randint(
            item_config["min_per_order"],
            item_config["max_per_order"]
        )

        selected_products = random.sample(
            product_ids,
            k=min(number_of_items, len(product_ids))
        )

        total = 0

        for product_id in selected_products:
            quantity = random.randint(1, 3)
            unit_price = product_lookup[product_id]

            rows.append({
                "order_item_id": order_item_id,
                "order_id": order_id,
                "product_id": product_id,
                "quantity": quantity,
                "unit_price": unit_price
            })

            total += quantity * unit_price
            order_item_id += 1

        order_totals[order_id] = round(total, 2)

    order_items = pd.DataFrame(rows)

    orders["total_amount"] = (
        orders["order_id"]
        .map(order_totals)
        .round(2)
    )

    return order_items, orders


def generate_payments(
    config: dict,
    fake: Faker,
    orders: pd.DataFrame
) -> pd.DataFrame:

    methods = config["payment_methods"]
    statuses = config["statuses"]["payment"]

    rows = []

    for _, order in orders.iterrows():

        payment_id = int(order["order_id"])

        rows.append({
            "payment_id": payment_id,
            "order_id": int(order["order_id"]),
            "payment_date": fake.date_time_between(
                start_date=order["order_date"],
                end_date="+10d"
            ),
            "payment_method": random.choice(methods),
            "amount": order["total_amount"],
            "status": random.choice(statuses),
            "transaction_id": fake.uuid4()
        })

    return pd.DataFrame(rows)


'''############## 
Error injection functions
'''
def inject_duplicate(
    df,
    rule,
    datasets,
    seed,
    base_size
):
    count = int(base_size * rule["rate"])

    if count == 0:
        return df, 0

    indexes = df.sample(
        n=count,
        random_state=seed
    ).index

    duplicated_rows = df.loc[indexes]

    df = pd.concat(
        [df, duplicated_rows],
        ignore_index=True
    )

    return df, count


def inject_set(
    df,
    rule,
    datasets,
    seed,
    base_size
):
    count = int(base_size * rule["rate"])

    if count == 0:
        return df, 0

    indexes = df.sample(
        n=count,
        random_state=seed
    ).index

    df.loc[
        indexes,
        rule["column"]
    ] = rule.get("value")

    return df, count


def inject_multiply(
    df,
    rule,
    datasets,
    seed,
    base_size
):
    count = int(base_size * rule["rate"])

    if count == 0:
        return df, 0

    indexes = df.sample(
        n=count,
        random_state=seed
    ).index

    column = rule["column"]

    df.loc[indexes, column] = (
        df.loc[indexes, column]
        * rule["value"]
    ).round(2)

    return df, count

def inject_invalid_fk(
    df,
    rule,
    datasets,
    seed,
    base_size
):
    count = int(base_size * rule["rate"])

    if count == 0:
        return df, 0

    indexes = df.sample(
        n=count,
        random_state=seed
    ).index

    reference_df = datasets[
        rule["reference_dataset"]
    ]

    reference_column = rule["reference_column"]

    invalid_start = (
        reference_df[reference_column].max()
        + rule.get("offset", 100000)
    )

    df.loc[
        indexes,
        rule["column"]
    ] = [
        invalid_start + i
        for i in range(count)
    ]

    return df, count


def apply_error(
    datasets: dict[str, pd.DataFrame],
    rule: dict,
    seed: int,
    base_size: int
):
    dataset_name = rule["dataset"]
    operation = rule["operation"]

    df = datasets[dataset_name].copy()

    match operation:

        case "duplicate":
            df, count = inject_duplicate(
                df, rule, datasets, seed, base_size
            )

        case "set":
            df, count = inject_set(
                df, rule, datasets, seed, base_size
            )

        case "multiply":
            df, count = inject_multiply(
                df, rule, datasets, seed, base_size
            )

        case "invalid_fk":
            df, count = inject_invalid_fk(
                df, rule, datasets, seed, base_size
            )

        case _:
            raise ValueError(
                f"Unsupported operation: {operation}"
            )

    return df, count


def inject_errors(
    config: dict,
    datasets: dict[str, pd.DataFrame]
):
    error_config = config["errors"]
    issues = {}

    if not error_config.get("enabled", False):
        return datasets, issues

    # Keep original dataset sizes before any mutation
    original_sizes = {
        dataset_name: len(df)
        for dataset_name, df in datasets.items()
    }

    for i, rule in enumerate(error_config["rules"]):
        dataset_name = rule["dataset"]

        updated_df, count = apply_error(
            datasets=datasets,
            rule=rule,
            seed=config["seed"] + i,
            base_size=original_sizes[dataset_name]
        )

        datasets[dataset_name] = updated_df
        issues[rule["name"]] = count

    return datasets, issues


def save_csv(
    df: pd.DataFrame,
    output_folder: Path,
    filename: str
):
    path = output_folder / filename

    df.to_csv(
        path,
        index=False
    )

    print(f"Generated: {path} ({len(df)} rows)")


def main():
    config = load_config(CONFIG_PATH)

    seed = config["seed"]

    setup_random_seed(seed)

    fake = Faker()

    base_output_folder = Path(
        config["output"]["folder"]
    )

    output_folder = (
        base_output_folder
        / f"seed_{seed}"
    )

    output_folder.mkdir(
        parents=True,
        exist_ok=True
    )

    # Generate clean relational dataset
    customers = generate_customers(
        config,
        fake
    )

    products = generate_products(
        config,
        fake
    )

    orders = generate_orders(
        config,
        fake,
        customers
    )

    order_items, orders = generate_order_items(
        config,
        orders,
        products
    )

    payments = generate_payments(
        config,
        fake,
        orders
    )

    # Inject intentional errors
    datasets = {
        "customers": customers,
        "products": products,
        "orders": orders,
        "order_items": order_items,
        "payments": payments,
    }

    datasets, issues = inject_errors(
        config,
        datasets
    )

    for dataset_name, df in datasets.items():
        save_csv(
            df,
            output_folder,
            f"{dataset_name}.csv"
        )


    # Save expected issues
    if config["metadata"]["generate_expected_issues"]:

        expected_path = (
            output_folder
            / config["metadata"]["expected_issues_file"]
        )

        with open(
            expected_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                issues,
                file,
                indent=2
            )

        print(f"Generated: {expected_path}")

    print(f"\nOutput folder: {output_folder}")

    print("\nExpected data quality issues:")

    for issue, count in issues.items():
        print(f"  {issue}: {count}")


if __name__ == "__main__":
    main()