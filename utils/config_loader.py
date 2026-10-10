import yaml

def load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f)

def deep_merge(base: dict, specific: dict) -> dict:
    """
    Deep merge two dictionaries.
    
    Args:
        base: The base dictionary
        specific: The specific dictionary that overrides base values
        
    Returns:
        A new dictionary with merged values, where specific overrides base
    """
    result = base.copy()
    
    for key, value in specific.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            # Recursively merge nested dictionaries
            result[key] = deep_merge(result[key], value)
        else:
            # Override with specific value
            result[key] = value
    
    return result
    
def load_config(config_name: str) -> dict:
    base = load_yaml("config/base.yaml")
    specific = load_yaml(f"config/{config_name}.yaml")

    return deep_merge(base, specific)