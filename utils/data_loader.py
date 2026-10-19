from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_yaml(relative_path: str) -> Any:
    path = PROJECT_ROOT / relative_path
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)
