"""Worker-thread plumbing — THE ONLY sanctioned way to call the API from UI.

run_api(fn, on_success, on_error) executes `fn` on Qt's global thread pool
and delivers the result (or an ApiError) back on the UI thread via signals.
The UI thread never blocks on network I/O; auditing the worker rule means
checking that every ApiClient call site goes through run_api().
"""

import traceback
from collections.abc import Callable

from loguru import logger
from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal, Slot

from services.api_client import ApiError
from ui import strings


class _WorkerSignals(QObject):
    success = Signal(object)
    error = Signal(object)  # ApiError


class _ApiWorker(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        # Lifetime is managed by the _ACTIVE registry below — without it the
        # Python wrapper (and its signals QObject) can be garbage-collected
        # before the queued signal reaches the UI thread.
        self.setAutoDelete(False)
        self.fn = fn
        self.signals = _WorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            result = self.fn()
        except ApiError as exc:
            self.signals.error.emit(exc)
        except Exception:
            logger.error("Worker crash:\n{}", traceback.format_exc())
            self.signals.error.emit(ApiError("unexpected", strings.UNEXPECTED_ERROR))
        else:
            self.signals.success.emit(result)


_ACTIVE: set[_ApiWorker] = set()


def run_api(
    fn: Callable[[], object],
    on_success: Callable[[object], None],
    on_error: Callable[[object], None],
) -> None:
    """Run a blocking API call off the UI thread; deliver results back on it."""
    worker = _ApiWorker(fn)
    _ACTIVE.add(worker)

    def _finish(callback: Callable[[object], None], payload: object) -> None:
        try:
            callback(payload)
        finally:
            _ACTIVE.discard(worker)

    worker.signals.success.connect(lambda result: _finish(on_success, result))
    worker.signals.error.connect(lambda err: _finish(on_error, err))
    QThreadPool.globalInstance().start(worker)
