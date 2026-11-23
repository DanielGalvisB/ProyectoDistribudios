import os
import yaml


def load_config(path=None):
    path = path or os.environ.get("SRB_CONFIG", "config.yaml")
    with open(path) as f:
        return yaml.safe_load(f)
