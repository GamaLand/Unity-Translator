import asyncio

from test_repository import draft

from unitytranslator.application import ApplicationSession


def test_paging_clamps_6749_records_and_filtered_results(tmp_path):
    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"

    async def run():
        session = ApplicationSession()
        try:
            await session.dispatch("open", {"game": str(game), "project": str(project)})
            session.repo.ingest([draft(f"UI/{i:04}", f"Text #{i:04}") for i in range(6749)], {})
            last = await session.dispatch("page", {"offset": 6800})
            assert last["offset"] == 6600 and last["count"] == 6749
            assert len(last["rows"]) == 149
            one = await session.dispatch("page", {"offset": 6800, "search": "Text #6748"})
            assert one["offset"] == 0 and one["count"] == 1 and len(one["rows"]) == 1
            empty = await session.dispatch("page", {"offset": 6800, "search": "not present"})
            assert empty["offset"] == 0 and empty["count"] == 0 and empty["rows"] == []
        finally:
            await session.close()

    asyncio.run(run())


def test_qt_stops_at_last_page_and_resets_after_filter(tmp_path):
    from PySide6.QtWidgets import QApplication
    from test_ui import wait_for

    from unitytranslator.filesystem import ProjectPaths
    from unitytranslator.repository import ProjectRepository
    from unitytranslator.ui.window import MainWindow

    game = tmp_path / "game"
    game.mkdir()
    project = tmp_path / "project"
    with ProjectRepository(ProjectPaths(game, project)) as repo:
        repo.ingest([draft(f"UI/{i:03}", f"Text {i:03}") for i in range(401)], {})
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    errors = []
    window.bridge.failed.disconnect(window.failed)
    window.bridge.failed.connect(lambda command, message: errors.append((command, message)))
    try:
        window.submit_open_project({"project": str(project), "existing_only": True})
        wait_for(app, lambda: window.review_count == 401 and not window.page_pending)
        assert window.parallel_requests.maximum() == 16
        assert not window.previous_page.isEnabled() and window.next_page.isEnabled()
        for offset in (200, 400):
            window.next_page.click()
            window.change_page(200)  # Repeated clicks while loading cannot skip a page.
            wait_for(app, lambda: not window.page_pending)
            assert window.offset == offset
        assert len(window.review_model.rows) == 1 and not window.next_page.isEnabled()
        for _ in range(5):
            window.next_page.click()
            window.change_page(200)
        assert window.offset == 400 and len(window.review_model.rows) == 1
        window.search.setText("Text 400")
        wait_for(app, lambda: window.review_count == 1 and not window.page_pending)
        assert window.offset == 0
        assert not window.previous_page.isEnabled() and not window.next_page.isEnabled()
        assert not errors
    finally:
        window.close()
        wait_for(app, lambda: window.backend_closed)
