import re
from pathlib import Path
import numpy as np
from tifffile import imread

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


def hsorted(list_):
    """ Sort the given list in the way that humans expect """
    list_ = [str(x) for x in list_]
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(list_, key=alphanum_key)


def get_reader(path):
    if isinstance(path, (str, Path)) and Path(path).is_dir():
        return read_stack_from_folder
    elif isinstance(path, list) and all(str(p).endswith(".tif") for p in path):
        return read_stack_from_files
    return None


def read_stack_from_folder(path):
    folder = Path(path)
    files = hsorted(folder.glob("*.tif"))
    if not files:
        return None
    stack = np.array([imread(f) for f in files])
    return [(stack, {"name": folder.name}, "image")]


def read_stack_from_files(paths):
    files = hsorted(Path(p) for p in paths)
    stack = np.array([imread(f) for f in files])
    return [(stack, {"name": "tif_stack"}, "image")]


class CollapsibleSection(QFrame):
    def __init__(self, title: str, run_callback=None):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setAcceptDrops(True)
        self.setObjectName(title)
        self.run_callback = run_callback  # function to call when RUN clicked

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 0, 0, 0)
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
        header_layout.addWidget(self.checkbox)
        header_layout.addWidget(self.run_button)

        self.main_layout = QVBoxLayout(self)
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
        self.layout.setContentsMargins(0, 10, 0, 0)

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
