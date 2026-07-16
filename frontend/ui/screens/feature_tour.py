"""Interactive guided tour — spotlight coach marks over the live app.

Instead of a static list of features, the tour dims the window, cuts a
highlight "hole" around a real UI element (a sidebar entry, the search field,
the pay button…), navigates between screens as it goes, and explains each
step in a floating callout with Précédent / Suivant / Passer.

Launched from Réglages ("Démarrer la visite"). Direction-agnostic: callout
button order follows the app's RTL/LTR layout direction automatically.

`FeatureTourDialog` is kept as a thin backward-compatible alias so any old
caller (`FeatureTourDialog(parent).exec()`) still starts the new tour.
"""

from collections.abc import Callable

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui import strings
from ui.styles import tokens
from ui.styles.tokens import SPACING


class _Step:
    """One tour step: which screen to show and which widget to spotlight."""

    def __init__(
        self,
        title: str,
        desc: str,
        navigate: Callable | None = None,
        target: Callable | None = None,
    ) -> None:
        self.title = title
        self.desc = desc
        self.navigate = navigate  # (main) -> screen widget to switch to, or None
        self.target = target  # (main) -> widget to spotlight, or None (centered)


class FeatureTour(QWidget):
    """Full-window spotlight overlay that walks the operator through the app."""

    def __init__(self, main_window) -> None:
        central = main_window.centralWidget()
        super().__init__(central)
        self._main = main_window
        self._central = central
        self._hole: QRect | None = None
        self._index = 0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._steps = self._build_steps()
        self._build_callout()
        self._main.installEventFilter(self)

    # ------------------------------------------------------------ construction

    def _build_callout(self) -> None:
        self._callout = QFrame(self)
        self._callout.setObjectName("TourCallout")
        self._callout.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self._callout)
        layout.setContentsMargins(
            SPACING["lg"], SPACING["lg"], SPACING["lg"], SPACING["md"]
        )
        layout.setSpacing(SPACING["sm"])

        self._step_label = QLabel()
        self._step_label.setObjectName("TourStepLabel")
        layout.addWidget(self._step_label)

        self._title_label = QLabel()
        self._title_label.setObjectName("TourTitle")
        self._title_label.setWordWrap(True)
        layout.addWidget(self._title_label)

        self._desc_label = QLabel()
        self._desc_label.setObjectName("Muted")
        self._desc_label.setWordWrap(True)
        layout.addWidget(self._desc_label)
        layout.addSpacing(SPACING["xs"])

        buttons = QHBoxLayout()
        buttons.setSpacing(SPACING["sm"])
        self._skip_btn = QPushButton(strings.FEATURE_TOUR_SKIP)
        self._skip_btn.setObjectName("Ghost")
        self._skip_btn.clicked.connect(self.finish)
        buttons.addWidget(self._skip_btn)
        buttons.addStretch(1)
        self._prev_btn = QPushButton(strings.FEATURE_TOUR_PREV)
        self._prev_btn.setObjectName("Ghost")
        self._prev_btn.clicked.connect(self._prev)
        buttons.addWidget(self._prev_btn)
        self._next_btn = QPushButton(strings.FEATURE_TOUR_NEXT)
        self._next_btn.setObjectName("Primary")
        self._next_btn.setDefault(True)
        self._next_btn.clicked.connect(self._next)
        buttons.addWidget(self._next_btn)
        layout.addLayout(buttons)

        self._callout.setFixedWidth(360)

    def _build_steps(self) -> list[_Step]:
        # Navigation targets are screen KEYS (MainWindow.navigate accepts
        # them) and spotlight targets come from the key→button map, so the
        # sidebar can be reordered without breaking the tour.
        return [
            _Step(strings.FEATURE_TOUR_WELCOME, strings.FEATURE_TOUR_WELCOME_DESC),
            _Step(
                strings.FEATURE_TOUR_CHECKOUT_TITLE,
                strings.FEATURE_TOUR_NAV_CAISSE_DESC,
                navigate=lambda m: "checkout",
                target=lambda m: m._nav_by_key["checkout"],
            ),
            _Step(
                strings.FEATURE_TOUR_SEARCH_TITLE,
                strings.FEATURE_TOUR_SEARCH_DESC,
                navigate=lambda m: "checkout",
                target=lambda m: m.checkout.search,
            ),
            _Step(
                strings.FEATURE_TOUR_PAY_TITLE,
                strings.FEATURE_TOUR_PAY_DESC,
                navigate=lambda m: "checkout",
                target=lambda m: m.checkout.pay_button,
            ),
            _Step(
                strings.FEATURE_TOUR_INVENTORY_TITLE,
                strings.FEATURE_TOUR_INVENTORY_DESC,
                navigate=lambda m: "inventory",
                target=lambda m: m._nav_by_key["inventory"],
            ),
            _Step(
                strings.FEATURE_TOUR_CUSTOMERS_TITLE,
                strings.FEATURE_TOUR_CUSTOMERS_DESC,
                navigate=lambda m: "customers",
                target=lambda m: m._nav_by_key["customers"],
            ),
            _Step(
                strings.FEATURE_TOUR_STATS_TITLE,
                strings.FEATURE_TOUR_STATS_DESC,
                navigate=lambda m: "statistics",
                target=lambda m: m._nav_by_key["statistics"],
            ),
            _Step(
                strings.FEATURE_TOUR_ALERTS_TITLE,
                strings.FEATURE_TOUR_ALERTS_DESC,
                navigate=lambda m: "alerts",
                target=lambda m: m._nav_by_key["alerts"],
            ),
            _Step(
                strings.FEATURE_TOUR_SETTINGS_TITLE,
                strings.FEATURE_TOUR_SETTINGS_DESC,
                navigate=lambda m: "settings",
                target=lambda m: m._nav_by_key["settings"],
            ),
            _Step(
                strings.FEATURE_TOUR_DONE_TITLE,
                strings.FEATURE_TOUR_DONE_DESC,
                navigate=lambda m: "checkout",
            ),
        ]

    # ------------------------------------------------------------- lifecycle

    def start(self) -> None:
        self.setGeometry(self._central.rect())
        self.show()
        self.raise_()
        self.setFocus()
        self._index = 0
        self._render_current()

    def finish(self) -> None:
        self._main.removeEventFilter(self)
        self.hide()
        self.deleteLater()

    def _next(self) -> None:
        if self._index >= len(self._steps) - 1:
            self.finish()
            return
        self._index += 1
        self._render_current()

    def _prev(self) -> None:
        if self._index > 0:
            self._index -= 1
            self._render_current()

    def _render_current(self) -> None:
        step = self._steps[self._index]
        if step.navigate is not None:
            screen = step.navigate(self._main)  # a screen key (or None)
            if screen is not None:
                self._main.navigate(screen)
        # Give the just-navigated screen a beat to lay out before we measure
        # the target's on-screen geometry.
        QTimer.singleShot(60, self._apply_step)

    def _apply_step(self) -> None:
        if not self.isVisible():
            return
        self.setGeometry(self._central.rect())
        self.raise_()
        step = self._steps[self._index]
        total = len(self._steps)
        self._step_label.setText(
            strings.FEATURE_TOUR_STEP.format(n=self._index + 1, total=total)
        )
        self._title_label.setText(step.title)
        self._desc_label.setText(step.desc)
        is_last = self._index >= total - 1
        self._prev_btn.setVisible(self._index > 0)
        self._skip_btn.setVisible(not is_last)
        self._next_btn.setText(
            strings.FEATURE_TOUR_FINISH if is_last else strings.FEATURE_TOUR_NEXT
        )

        target = step.target(self._main) if step.target is not None else None
        self._hole = self._target_rect(target)
        self._position_callout()
        self.update()

    # --------------------------------------------------------------- geometry

    def _target_rect(self, target) -> QRect | None:
        if target is None or not target.isVisible() or target.width() <= 0:
            return None
        top_left = self.mapFromGlobal(target.mapToGlobal(QPoint(0, 0)))
        pad = 6
        return QRect(
            top_left.x() - pad,
            top_left.y() - pad,
            target.width() + 2 * pad,
            target.height() + 2 * pad,
        )

    def _position_callout(self) -> None:
        self._callout.adjustSize()
        width, height = self._callout.width(), self._callout.height()
        area = self.rect()
        gap = 14

        if self._hole is None:
            x = area.center().x() - width // 2
            y = area.center().y() - height // 2
        else:
            hole = self._hole
            if hole.bottom() + gap + height <= area.bottom():
                y = hole.bottom() + gap
                x = hole.left()
            elif hole.top() - gap - height >= area.top():
                y = hole.top() - gap - height
                x = hole.left()
            elif hole.right() + gap + width <= area.right():
                x = hole.right() + gap
                y = hole.top()
            else:
                x = hole.left() - gap - width
                y = hole.top()

        x = max(area.left() + gap, min(x, area.right() - width - gap))
        y = max(area.top() + gap, min(y, area.bottom() - height - gap))
        self._callout.move(x, y)

    # ------------------------------------------------------------------ paint

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        overlay = QPainterPath()
        overlay.addRect(QRectF(self.rect()))
        if self._hole is not None:
            hole = QPainterPath()
            hole.addRoundedRect(QRectF(self._hole), 10, 10)
            overlay = overlay.subtracted(hole)
        painter.fillPath(overlay, QColor(15, 23, 42, 200))
        if self._hole is not None:
            painter.setPen(QPen(QColor(tokens.CURRENT_ACCENT), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self._hole), 10, 10)
        painter.end()

    # ----------------------------------------------------------------- events

    def eventFilter(self, obj, event) -> bool:
        if obj is self._main and event.type() in (
            QEvent.Type.Resize,
            QEvent.Type.Move,
        ):
            if self.isVisible():
                self.setGeometry(self._central.rect())
                self._apply_step()
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event) -> None:  # noqa: N802 (Qt override)
        key = event.key()
        if key == Qt.Key.Key_Escape:
            self.finish()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Right):
            self._next()
        elif key == Qt.Key.Key_Left:
            self._prev()
        else:
            super().keyPressEvent(event)


class FeatureTourDialog:
    """Backward-compatible shim: old callers did FeatureTourDialog(parent).exec().

    We now launch the live spotlight tour on the main window instead of a
    static dialog. exec() returns immediately (the tour is modeless).
    """

    def __init__(self, parent=None) -> None:
        self._parent = parent

    def exec(self) -> int:
        window = self._parent.window() if self._parent is not None else None
        if window is None or not hasattr(window, "_nav_by_key"):
            return 0
        tour = FeatureTour(window)
        window._feature_tour = tour  # keep a reference alive during the tour
        tour.start()
        return 1
