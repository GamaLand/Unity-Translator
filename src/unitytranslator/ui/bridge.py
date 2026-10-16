import asyncio
import threading
from typing import Any

from PySide6.QtCore import QObject, Signal

from unitytranslator.application import ApplicationSession


class BackendBridge(QObject):
    completed = Signal(str, object)
    failed = Signal(str, str)
    progress = Signal(object)
    stopped = Signal()

    def __init__(self):
        super().__init__()
        self.ready = threading.Event()
        self.thread = threading.Thread(
            target=self._thread_main, daemon=True, name="UnityTranslatorIO"
        )
        self.thread.start()
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
            self.failed.emit(command, str(exc))

    def submit(self, command: str, data: dict[str, Any] | None = None):
        return asyncio.run_coroutine_threadsafe(self._perform(command, data or {}), self.loop)

    def shutdown(self):
        async def finish():
            while self.session.extracting:
                await asyncio.sleep(0.1)
            await self.session.close()
            self.loop.stop()

        asyncio.run_coroutine_threadsafe(finish(), self.loop)
