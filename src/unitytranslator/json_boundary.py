"""Reject duplicate keys and non-standard numbers at external JSON boundaries."""

import json
from typing import Any


def strict_json(raw: str | bytes) -> Any:
    def fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON field.")
            result[key] = value
        return result

    def invalid_number(value: str) -> Any:
        raise ValueError("Nonstandard JSON number.")

    try:
        return json.loads(raw, object_pairs_hook=fields, parse_constant=invalid_number)
    except RecursionError as exc:
        raise ValueError("JSON nesting limit exceeded.") from exc
