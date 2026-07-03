from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)


class DataTable(QTableWidget):
    """QTableWidget with the defaults every screen needs: read-only,
    row-selection, stretch columns, alternating rows."""

    def __init__(self, headers: list[str], parent=None) -> None:
        super().__init__(0, len(headers), parent)
        self.setHorizontalHeaderLabels(headers)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.setShowGrid(False)

    def set_rows(self, rows: list[list[str]]) -> None:
        """Replace all rows; each cell is plain text."""
        self.setRowCount(0)
        for row_values in rows:
            row = self.rowCount()
            self.insertRow(row)
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(str(value))
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.setItem(row, col, item)

    def selected_row(self) -> int:
        """Index of the selected row, or -1."""
        indexes = self.selectionModel().selectedRows()
        return indexes[0].row() if indexes else -1
