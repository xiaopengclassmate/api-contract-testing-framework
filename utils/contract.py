from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"


def load_schema(name: str) -> dict:
    path = SCHEMA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def _registry() -> Registry:
    resources: dict[str, Resource] = {}
    for path in SCHEMA_DIR.glob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources[path.name] = Resource.from_contents(
            contents, default_specification=DRAFT202012
        )
    return Registry().with_resources(resources.items())


def validate_schema(instance: object, schema_name: str) -> None:
    """按消费者契约（JSON Schema）校验响应体。"""
    schema = load_schema(schema_name)
    validator = Draft202012Validator(
        schema,
        registry=_registry(),
        format_checker=FormatChecker(),
    )
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.path))
    if errors:
        messages = "\n".join(
            f"- {list(error.path)}: {error.message}" for error in errors[:10]
        )
        raise AssertionError(
            f"契约校验失败: {schema_name}\n{messages}"
        )
