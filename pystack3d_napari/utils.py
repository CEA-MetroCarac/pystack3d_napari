# import os
import re
import ast
from pathlib import Path
from typing import List, Union
import numpy as np
from tifffile import imread
from multiprocessing import Process

import napari

from qtpy.QtWidgets import (QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QCheckBox, QFrame, QSizePolicy, QProgressBar)
from qtpy.QtCore import Qt, QMimeData, QTimer
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


# def get_reader(path: Union[str, List[str]]):
#     # This is where we actually load the data
#     print(1, path)
#     if True:
#         if os.path.isdir(path):
#             files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.tif')]
#         else:
#             files = [f for f in path if f.endswith('.tif')]
#
#         stack = [imread(p) for p in hsorted(files)]
#         stack = np.stack(stack, axis=0)  # 3D stack
#
#         return [(stack, {"name": "Images Stack"}, "image")]
#     else:
#         return None

def get_params(kwargs):
    params = {}
    for arg, value in kwargs.items():
        if isinstance(value, str):
            if value == '':
                value = None
            elif '[' in value or '(' in value:
                value = ast.literal_eval(value)
            else:
                try:
                    value = float(value)
                except:
                    pass
        params[arg] = value
    return params


def process(stack, process_name):
    stack.eval(process_steps=process_name, show_pbar=False, pbar_init=True)


def get_stack(dirname):
    fnames = hsorted(Path(dirname).glob("*.tif"))
    stack = [imread(fname) for fname in fnames]
    stack = np.stack(stack, axis=0)
    print("get_stack", stack.shape)
    return [(stack, {"name": dirname.name.upper()}, "image")]


class CollapsibleSection(QFrame):
    def __init__(self, parent, process_name: str, widget):
        super().__init__()
        self.setFrameShape(QFrame.StyledPanel)
        self.setAcceptDrops(True)
        self.setObjectName(process_name)
        self.parent = parent
        self.process_name = process_name
        self.widget = widget

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(20, 0, 0, 0)
        self.content.setVisible(False)

        self.toggle_button = QPushButton("►")
        self.toggle_button.setMaximumWidth(20)
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self.toggle)

        self.title_label = QLabel(process_name)

        self.checkbox = QCheckBox()
        self.checkbox.setChecked(True)
        self.checkbox.stateChanged.connect(self.toggle_content_enabled)

        self.run_button = QPushButton("RUN")
        self.run_button.setFixedWidth(50)
        self.run_button.clicked.connect(self.run)

        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(self.title_label)
        header_layout.addWidget(self.checkbox)

        header_layout2 = QHBoxLayout()
        header_layout2.addWidget(self.run_button)
        header_layout2.addWidget(self.progress_bar)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.addLayout(header_layout)
        self.main_layout.addWidget(self.content)
        self.main_layout.addLayout(header_layout2)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    def toggle(self):
        visible = not self.content.isVisible()
        self.content.setVisible(visible)
        self.toggle_button.setText("▼" if visible else "►")

    def toggle_content_enabled(self, state):
        enabled = (state == Qt.Checked)
        self.content.setEnabled(enabled)
        self.run_button.setEnabled(enabled)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
        self._linked_widget = widget  # store magicgui widget reference

    def run(self):
        count = 0
        ntot = None

        def update_progress():
            nonlocal count, ntot
            if not self.parent.stack.queue_incr.empty():
                val = self.parent.stack.queue_incr.get_nowait()
                if val != "finished":
                    if ntot:
                        count += val
                        self.progress_bar.setValue(int(100 * count / ntot))
                    else:
                        ntot = val
                if count == ntot:
                    self.handle_result()
                    timer.stop()

        timer = QTimer()
        timer.timeout.connect(update_progress)
        timer.start(200)

        Process(target=process, args=(self.parent.stack, self.process_name)).start()

    def handle_result(self):
        result = get_stack(dirname=self.parent.stack.pathdir / 'process' / self.process_name)
        viewer = napari.current_viewer()
        for data, kwargs, layer_type in result:
            getattr(viewer, f"add_{layer_type}")(data, **kwargs)

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

    def get_widget(self, name):
        widget = None
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if w.objectName() == name:
                widget = w
                break
        return widget

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        # find moving item
        dragged_widget = self.get_widget(name=event.mimeData().text())
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
