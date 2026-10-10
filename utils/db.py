from sqlalchemy import create_engine
from utils.config_loader import load_yaml

def get_engine():
    config = load_yaml("config/base.yaml")
    db = config["database"]

    url = (
        f"postgresql+psycopg://"
        f"{db['user']}:{db['password']}@"
        f"{db['host']}:{db['port']}/{db['name']}"
    )

    return create_engine(url)