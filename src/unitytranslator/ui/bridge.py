import asyncio
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from unitytranslator.application import ApplicationSession
from unitytranslator.diagnostics import describe


class BackendBridge(QObject):
    completed = Signal(str, object)
    # The failure is a diagnostics.Failure: English text with code and request identity.
    failed = Signal(str, object)
    progress = Signal(object)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.ready = threading.Event()
        io_thread = threading.Thread(
            target=self._thread_main, daemon=True, name="UnityTranslatorIO"
        )
        # Legacy public name read by shutdown checks; it shadows QObject.thread().
        self.thread = io_thread  # type: ignore[method-assign, assignment]
        io_thread.start()
        self.ready.wait(timeout=5)

    def _thread_main(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.session = ApplicationSession(self.progress.emit)
        self.ready.set()
        try:
            self.loop.run_forever()
        finally:
            self.loop.run_until_complete(self.loop.shutdown_default_executor())
            self.loop.close()
            self.stopped.emit()

    async def _perform(self, command: str, data: dict[str, Any]):
        try:
            result = await self.session.dispatch(command, data)
            self.completed.emit(command, result)
        except Exception as exc:
            self.failed.emit(command, describe(
                exc, command=command, request_token=data.get("request_token"),
                project_id=self.session.current_project_id(),
            ))

    def submit(self, command: str, data: dict[str, Any] | None = None):
        if command in ("create_job", "create_affected_job", "create_page_job"):
            self.session.reserve_preparation()
        if command == "cancel" and self.session.request_preparation_cancel():
            command = "cancel_preparation"
        return asyncio.run_coroutine_threadsafe(self._perform(command, data or {}), self.loop)

    def shutdown(self):
        self.session.request_shutdown()
        async def finish():
            try:
                await self.session.close()
            finally:
                self.loop.stop()

        asyncio.run_coroutine_threadsafe(finish(), self.loop)
