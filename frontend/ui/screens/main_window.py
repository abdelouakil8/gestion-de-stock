from PySide6.QtWidgets import QMainWindow

from ui import strings


class MainWindow(QMainWindow):
    """Application shell — real screens will be mounted here later.

    Layout rule: never assume left-to-right; Arabic (RTL) support arrives
    later via Qt layout direction, so keep positioning direction-agnostic.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(strings.APP_TITLE)
        self.resize(1024, 640)
