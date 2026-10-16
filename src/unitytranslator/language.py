"""Yerel harf yardımcıları; kimlik/hash girdilerini değiştirmez."""


def turkish_lower(value: str) -> str:
    return value.replace("I", "ı").replace("İ", "i").lower()
