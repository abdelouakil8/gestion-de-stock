import sys
from PySide6.QtWidgets import QApplication, QDialog, QPushButton, QVBoxLayout

class TestDialog(QDialog):
    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        self.btn = QPushButton("Cancel")
        self.btn.clicked.connect(self.reject)
        layout.addWidget(self.btn)
        
        # Simulate my geometry fix
        self.setFixedHeight(300)
        self.setMinimumHeight(0)
        self.setMaximumHeight(16777215)

app = QApplication(sys.argv)
d = TestDialog()
d.show()
app.processEvents()
print("Dialog visible. Rejecting...")
d.reject()
print("Dialog result:", d.result())
