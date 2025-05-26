from pathlib import Path
import numpy as np
import tifffile
import dm3_lib as dm3
from collections import namedtuple
import matplotlib.pyplot as plt

from qtpy.QtWidgets import (QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QCheckBox, QFrame, QSizePolicy)
from qtpy.QtCore import Qt, QMimeData
from qtpy.QtGui import QDrag


def error(message):
    """
    Shows a pop up with the given error message.
    """
    e = QMessageBox()
    print("ERROR: ", message)
    e.setText(message)
    e.setIcon(QMessageBox.Critical)
    e.setWindowTitle("Error")
    e.show()
    return e


def get_reader(path):
    if isinstance(path, str):
        if path.endswith(('.tif', '.tiff')):
            return read_tif
        elif path.endswith(('.dm3', '.dm4')):
            return read_dm
    return None


def read_tif(path):
    with tifffile.TiffFile(path) as tif:
        arr = np.array([page.asarray() for i, page in enumerate(tif.pages)])
        return [(arr.astype(np.float32), {"name": Path(path).name})]


def read_dm(path):
    arr = dm3.DM3(path).imagedata
    return [(arr.astype(np.float32), {"name": Path(path).name})]


class CollapsibleSection(QFrame):
    def __init__(self, title: str, run_callback=None):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setAcceptDrops(True)
        self.setObjectName(title)
        self.run_callback = run_callback  # function to call when RUN clicked

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.content.setVisible(False)

        self.toggle_button = QPushButton("▼")
        self.toggle_button.setMaximumWidth(20)
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self.toggle)

        self.title_label = QLabel(title)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(self.toggle_content_enabled)

        self.run_button = QPushButton("RUN")
        self.run_button.setFixedWidth(50)
        self.run_button.clicked.connect(self.run)

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(self.title_label)
        header_layout.addStretch()
        header_layout.addWidget(self.checkbox)
        header_layout.addWidget(self.run_button)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(5, 5, 5, 5)
        self.main_layout.setSpacing(2)
        self.main_layout.addLayout(header_layout)
        self.main_layout.addWidget(self.content)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    def toggle(self):
        visible = not self.content.isVisible()
        self.content.setVisible(visible)
        self.toggle_button.setText("▲" if visible else "▼")

    def toggle_content_enabled(self, state):
        enabled = (state == Qt.Checked)
        self.content.setEnabled(enabled)
        self.run_button.setEnabled(enabled)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
        self._linked_widget = widget  # store magicgui widget reference

    def run(self):
        if hasattr(self, '_linked_widget') and hasattr(self._linked_widget, 'run'):
            self._linked_widget.run()
        elif self.run_callback:
            self.run_callback()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            drag = QDrag(self)
            mime_data = QMimeData()
            mime_data.setText(self.objectName())
            drag.setMimeData(mime_data)
            drag.exec_(Qt.MoveAction)


class DragDropContainer(QWidget):
    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.setLayout(self.layout)
        self.setAcceptDrops(True)

    def add_section(self, section):
        self.layout.addWidget(section)

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        # find moving item
        dragged_name = event.mimeData().text()

        dragged_widget = None
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if w.objectName() == dragged_name:
                dragged_widget = w
                break

        if not dragged_widget:
            return

        # find the insert position
        drop_pos = event.pos()
        insert_at = self.layout.count() - 1

        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if widget == dragged_widget:
                continue
            if drop_pos.y() < widget.y() + widget.height() // 2:
                insert_at = i
                break

        self.layout.removeWidget(dragged_widget)
        self.layout.insertWidget(insert_at, dragged_widget)

        event.accept()
