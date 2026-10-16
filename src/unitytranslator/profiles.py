"""Built-in discovery profiles; a file hint is not proof of compatibility."""

from dataclasses import dataclass


@dataclass(frozen=True)
class GameProfile:
    id: str
    company: str
    product: str
    source_hint: str


PROFILES = (GameProfile("mechanicus-i2", "BulwarkStudios", "Mechanicus", "resources.assets"),)


def match_profile(company: str, product: str) -> GameProfile | None:
    return next(
        (
            profile
            for profile in PROFILES
            if (profile.company, profile.product) == (company, product)
        ),
        None,
    )
