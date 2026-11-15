"""Synthetic 100,000-record persistence budgets; catches quadratic regressions, not speed."""

import time
from collections.abc import Callable
from hashlib import sha256
from pathlib import Path
from typing import Any

from unitytranslator.domain import TextUnitDraft
from unitytranslator.filesystem import ProjectPaths
from unitytranslator.portable import PortableService
from unitytranslator.repository import ProjectRepository
from unitytranslator.review_selection import (
    all_approval_preview,
    approve_all,
    canonical_all_confirmation,
)

UNITS = 100_000
TRANSLATED = 20_000


def unit(index: int) -> TextUnitDraft:
    text = f"Synthetic line number {index} with some words"
    return TextUnitDraft(
        f"unit-{index:06d}", f"key/{index % 997:04d}/{index:06d}", "synthetic.assets", 1, "en",
        text, sha256(text.encode()).hexdigest(), ("menu", "dialogue", "item")[index % 3],
    )


def within(seconds: float, action: Callable[[], Any]) -> Any:
    started = time.perf_counter()
    value = action()
    elapsed = time.perf_counter() - started
    assert elapsed < seconds, f"{elapsed:.1f}s exceeded the {seconds}s budget"
    return value


def test_large_project_operations_stay_within_generous_budgets(tmp_path: Path) -> None:
    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        within(120, lambda: repo.ingest([unit(index) for index in range(UNITS)], {}))

        def translate() -> None:
            with repo.transaction() as db:
                for index in range(TRANSLATED):
                    unit_id = f"unit-{index:06d}"
                    row = db.execute(
                        "SELECT u.source_revision,w.version FROM text_units u "
                        "JOIN work_items w USING(unit_id) WHERE unit_id=?", (unit_id,),
                    ).fetchone()
                    assert repo.candidate(
                        unit_id, row[0], row[1], f"Sentetik satır numarası {index} kelimeler",
                        "model", {}, [],
                    )

        within(120, translate)
        assert len(within(10, lambda: repo.page(0))) == 200
        assert within(10, lambda: repo.page(0, search="number 4"))
        # Selective searches must not walk the whole review-order index.
        assert within(10, lambda: repo.page(0, search="no such phrase")) == []
        assert len(within(10, lambda: repo.page(0, search="number 99999 "))) == 1
        assert within(10, lambda: repo.page(0, status="translated"))
        assert within(20, lambda: repo.count()) == UNITS
        within(5, lambda: [repo.history(f"unit-{index:06d}") for index in range(50)])
        history = within(60, lambda: PortableService(repo).export_history())
        assert len(history) == UNITS
        assert sum(len(item["translations"]) for item in history) == TRANSLATED
        preview = within(60, lambda: all_approval_preview(repo))
        assert preview["count"] == TRANSLATED
        approved = within(120, lambda: approve_all(
            repo, preview, user_action=True,
            confirmation=canonical_all_confirmation(preview["count"]),
        ))
        assert approved == TRANSLATED
