"""Deferred work bounded by its target QObject's native lifetime."""

from collections.abc import Callable

from PyQt6.QtCore import QObject, QTimer, pyqtSlot


class DeferredCallback(QTimer):
    """Deliver one callback while its owner exists, then retire the timer."""

    def __init__(self, owner: QObject, delay_ms: int, callback: Callable[[], None]) -> None:
        super().__init__(owner)
        self._callback = callback
        self.setSingleShot(True)
        self.timeout.connect(self._invoke)
        self.start(delay_ms)

    @pyqtSlot()
    def _invoke(self) -> None:
        # The callback may destroy the owner, including this child timer.
        self.deleteLater()
        self._callback()
