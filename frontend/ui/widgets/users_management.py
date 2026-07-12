"""Owner-only user administration — list / create / edit-or-reset-PIN /
deactivate the named accounts of the store.

Embedded as the "Utilisateurs" tab of the Settings screen. Every mutation is
an owner action (the API enforces the role); this widget only guides.
"""

import qtawesome as qta
import shiboken6
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from services.workers import run_api
from ui import strings
from ui.styles.tokens import NEUTRAL, SPACING
from ui.widgets.badge import Badge
from ui.widgets.data_table import DataTable
from ui.widgets.modal import ModalDialog, ask_confirm, show_error
from ui.widgets.states import EmptyState, StatefulStack
from ui.widgets.toast import show_toast

_ROLE_KIND = {"owner": "accent", "manager": "success", "cashier": "neutral"}


class UserDialog(ModalDialog):
    """Create or edit a user. `user` present ⇒ edit mode."""

    def __init__(
        self, api, store_id: str, user: dict | None = None, parent=None
    ) -> None:
        title = strings.USER_DIALOG_EDIT if user else strings.USER_DIALOG_NEW
        super().__init__(title, parent)
        self.api = api
        self.store_id = store_id
        self.user = user
        self.result_user: dict | None = None

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText(strings.USER_NAME)
        self.content.addWidget(QLabel(strings.USER_NAME))
        self.content.addWidget(self.name_input)

        self.content.addWidget(QLabel(strings.USER_ROLE))
        self.role_combo = QComboBox()
        for value in ("cashier", "manager", "owner"):
            self.role_combo.addItem(strings.ROLE_LABELS[value], value)
        self.content.addWidget(self.role_combo)

        pin_label = QLabel(strings.USER_PIN_EDIT_HINT if user else strings.USER_PIN)
        self.content.addWidget(pin_label)
        self.pin_input = QLineEdit()
        self.pin_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.pin_input.setPlaceholderText(strings.USER_PIN_PLACEHOLDER)
        self.content.addWidget(self.pin_input)

        self.active_check = QCheckBox(strings.USER_ACTIVE)
        self.active_check.setChecked(True)
        if user:
            self.content.addWidget(self.active_check)

        if user:
            self.name_input.setText(user.get("name", ""))
            index = self.role_combo.findData(user.get("role"))
            if index >= 0:
                self.role_combo.setCurrentIndex(index)
            self.active_check.setChecked(bool(user.get("is_active", True)))
        self.name_input.setFocus()

    def accept(self) -> None:
        name = self.name_input.text().strip()
        if not name:
            show_error(self, strings.REQUIRED_FIELD)
            return
        pin = self.pin_input.text().strip()
        if not self.user and len(pin) < 4:
            show_error(self, strings.USER_PIN_TOO_SHORT)
            return
        if self.user and pin and len(pin) < 4:
            show_error(self, strings.USER_PIN_TOO_SHORT)
            return
        self.ok_button.setEnabled(False)
        if self.user:
            payload: dict = {
                "name": name,
                "role": self.role_combo.currentData(),
                "is_active": self.active_check.isChecked(),
            }
            if pin:
                payload["pin"] = pin
            call = lambda: self.api.update_user(self.user["id"], payload)  # noqa: E731
        else:
            payload = {
                "store_id": self.store_id,
                "name": name,
                "role": self.role_combo.currentData(),
                "pin": pin,
            }
            call = lambda: self.api.create_user(payload)  # noqa: E731
        run_api(call, self._on_saved, self._on_error)

    def _on_saved(self, user: object) -> None:
        self.result_user = user
        super().accept()

    def _on_error(self, err) -> None:
        self.ok_button.setEnabled(True)
        show_error(self, err.message)


class UsersManagementTab(QWidget):
    def __init__(self, api, store_id: str, parent=None) -> None:
        super().__init__(parent)
        self.api = api
        self.store_id = store_id
        self.users: list[dict] = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SPACING["md"])

        toolbar = QHBoxLayout()
        title = QLabel(strings.SETTINGS_TAB_USERS)
        title.setObjectName("SectionTitle")
        toolbar.addWidget(title)
        toolbar.addStretch(1)
        new_button = QPushButton(
            qta.icon("fa5s.user-plus", color="white"), strings.USER_NEW
        )
        new_button.setObjectName("Primary")
        new_button.clicked.connect(self._create)
        self.edit_button = QPushButton(
            qta.icon("fa5s.pen", color=NEUTRAL["600"]), strings.USER_EDIT
        )
        self.edit_button.clicked.connect(self._edit)
        self.edit_button.setEnabled(False)
        self.deactivate_button = QPushButton(strings.USER_DEACTIVATE)
        self.deactivate_button.setObjectName("Danger")
        self.deactivate_button.clicked.connect(self._deactivate)
        self.deactivate_button.setEnabled(False)
        for button in (new_button, self.edit_button, self.deactivate_button):
            toolbar.addWidget(button)
        layout.addLayout(toolbar)

        self.table = DataTable(
            [strings.USER_COL_NAME, strings.USER_COL_ROLE, strings.USER_COL_STATUS]
        )
        self.table.itemSelectionChanged.connect(self._on_selection)
        self.table.itemDoubleClicked.connect(lambda _: self._edit())
        self.stack = StatefulStack(
            self.table, EmptyState("fa5s.users", strings.USER_EMPTY)
        )
        layout.addWidget(self.stack, stretch=1)

    # ------------------------------------------------------------- loading

    def refresh(self) -> None:
        self.stack.show_loading()
        run_api(
            lambda: self.api.list_users(self.store_id),
            self._on_users,
            self._on_error,
        )

    def _on_users(self, users: object) -> None:
        if not shiboken6.isValid(self):
            return
        self.users = list(users or [])
        if not self.users:
            self.stack.show_empty()
            return
        self.table.set_rows(
            [
                [
                    u["name"],
                    "",  # role badge widget below
                    (
                        strings.USER_STATUS_ACTIVE
                        if u["is_active"]
                        else strings.USER_STATUS_INACTIVE
                    ),
                ]
                for u in self.users
            ]
        )
        for row, user in enumerate(self.users):
            holder = QWidget()
            box = QHBoxLayout(holder)
            box.setContentsMargins(SPACING["xs"], 2, SPACING["xs"], 2)
            box.addWidget(
                Badge(
                    strings.ROLE_LABELS.get(user["role"], user["role"]),
                    _ROLE_KIND.get(user["role"], "neutral"),
                )
            )
            box.addStretch(1)
            self.table.setCellWidget(row, 1, holder)
        self.stack.show_content()

    def _on_error(self, err) -> None:
        if not shiboken6.isValid(self):
            return
        self.stack.show_empty()
        show_error(self, err.message)

    # ------------------------------------------------------------- actions

    def _selected(self) -> dict | None:
        row = self.table.selected_row()
        if 0 <= row < len(self.users):
            return self.users[row]
        return None

    def _on_selection(self) -> None:
        has = self._selected() is not None
        self.edit_button.setEnabled(has)
        self.deactivate_button.setEnabled(has)

    def _create(self) -> None:
        dialog = UserDialog(self.api, self.store_id, parent=self)
        if dialog.exec() and dialog.result_user:
            self.refresh()
            show_toast(self, strings.USER_SAVED_TOAST)

    def _edit(self) -> None:
        user = self._selected()
        if not user:
            return
        dialog = UserDialog(self.api, self.store_id, user=user, parent=self)
        if dialog.exec() and dialog.result_user:
            self.refresh()
            show_toast(self, strings.USER_SAVED_TOAST)

    def _deactivate(self) -> None:
        user = self._selected()
        if not user:
            return
        if not ask_confirm(
            self, strings.USER_DEACTIVATE_CONFIRM.format(name=user["name"])
        ):
            return
        run_api(
            lambda: self.api.deactivate_user(user["id"]),
            lambda _result: self._on_deactivated(),
            self._on_error,
        )

    def _on_deactivated(self) -> None:
        self.refresh()
        show_toast(self, strings.USER_DEACTIVATED_TOAST)
