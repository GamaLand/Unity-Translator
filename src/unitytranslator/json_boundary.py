"""Dış JSON sınırında yinelenen alan ve standart dışı sayı reddi."""

import json
from typing import Any


def strict_json(raw: str | bytes) -> Any:
    def fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Yinelenen JSON alanı.")
            result[key] = value
        return result

    def invalid_number(value: str) -> Any:
        raise ValueError("Standart dışı JSON sayısı.")

    return json.loads(raw, object_pairs_hook=fields, parse_constant=invalid_number)
