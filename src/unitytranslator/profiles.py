"""Built-in discovery profiles; a file hint is not proof of compatibility."""

from dataclasses import dataclass

from unitytranslator.source_contracts import validate_relative_source


@dataclass(frozen=True)
class GameProfile:
    id: str
    company: str
    product: str
    source_hint: str
    reader_id: str = "i2"

    def __post_init__(self) -> None:
        validate_relative_source(self.source_hint)
        if any(not value or len(value) > 256 for value in (self.id, self.company, self.product)):
            raise ValueError("Invalid built-in game profile data.")
        if self.reader_id not in ("i2", "krypta-textassets"):
            raise ValueError("Unknown built-in profile reader.")


PROFILES = (
    GameProfile("mechanicus-i2", "BulwarkStudios", "Mechanicus", "resources.assets"),
    GameProfile(
        "krypta-fm-textassets", "Under The Sink", "KryptaFM", "sharedassets0.assets",
        "krypta-textassets",
    ),
)


def match_profile(company: str, product: str) -> GameProfile | None:
    return next(
        (
            profile
            for profile in PROFILES
            if (profile.company, profile.product) == (company, product)
        ),
        None,
    )
