from unitytranslator.language import turkish_lower
from unitytranslator.policy import GlossaryRule


def test_turkish_case_and_word_boundaries() -> None:
    assert turkish_lower("Iıİi ÇĞÖŞÜ") == "ııii çğöşü"
    rule = GlossaryRule(source="Iron", target="DEMİR", kind="preferred_translation")
    assert rule.matches("Iron shield", "UI")
    assert not rule.matches("ironic shield", "UI")
    assert rule.matches("demir kalkan", "UI", target=True)
    preserve = GlossaryRule(source="Mars", target="Mars", kind="preserve_name", category="dialog")
    assert preserve.matches("Mars", "dialog")
    assert not preserve.matches("Mars", "UI")


def test_policy_changes_mark_only_affected_and_keep_approvals(tmp_path) -> None:
    from test_repository import draft

    from unitytranslator.filesystem import ProjectPaths
    from unitytranslator.policy import PolicyStore
    from unitytranslator.repository import ProjectRepository

    game = tmp_path / "game"
    game.mkdir()
    with ProjectRepository(ProjectPaths(game, tmp_path / "project")) as repo:
        repo.ingest([draft("UI/iron", "Iron shield"), draft("UI/start", "Start")], {})
        repo.edit("UI/iron", 0, "Demir kalkan")
        iron = next(r for r in repo.page() if r["unit_id"] == "UI/iron")
        repo.approve("UI/iron", iron["version"])
        policies = PolicyStore(repo)
        rule = GlossaryRule(source="Iron", target="Demir", kind="preferred_translation")
        original = policies.set_glossary([rule])
        policies.set_glossary([rule.model_copy(update={"target": "Çelik"})])
        assert policies.rules(original)[0].target == "Demir"
        assert policies.impacted() == [
            {"unit_id": "UI/iron", "reason": "glossary_changed", "status": "approved"}
        ]
        assert repo.count(affected=True) == 1
        assert repo.page(affected=True)[0]["unit_id"] == "UI/iron"
        assert repo.count(affected=True, search="Start") == 0
        assert repo.count(affected=True, status="approved", category="UI") == 1
        assert (
            next(r for r in repo.page() if r["unit_id"] == "UI/iron")["translation"]
            == "Demir kalkan"
        )
        policies.set_glossary([])
        assert policies.impacted()[0]["unit_id"] == "UI/iron"
        retained = repo.page(affected=True)[0]
        repo.approve(retained["unit_id"], retained["version"])
        assert repo.count(affected=True) == 0
        assert repo.page(search="Iron")[0]["translation"] == "Demir kalkan"
        assert repo.page(search="Iron")[0]["status"] == "approved"
        assert (
            repo.db.execute(
                "SELECT count(*) FROM source_snapshots "
                "WHERE metadata_json LIKE '%human_policy_review%'"
            ).fetchone()[0]
            == 1
        )
