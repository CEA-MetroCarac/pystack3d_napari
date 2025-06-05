# import os
import re
import ast
from pathlib import Path
from typing import List, Union
from tomlkit import table, document, inline_table, array
import numpy as np
from tifffile import imread
from multiprocessing import Process

import napari
from napari.layers import Image

from qtpy.QtWidgets import (QMessageBox, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QCheckBox, QFrame, QSizePolicy, QProgressBar,
                            QTableWidget, QTableWidgetItem)
from qtpy.QtCore import Qt, QMimeData, QTimer, Signal
from qtpy.QtGui import QDrag

QFRAME_STYLE = {'transparent': "#{} {{ border: 2px solid transparent; border-radius: 6px; }}",
                'blue': "#{} {{ border: 2px solid #007ACC; border-radius: 6px; }}"}
FILTER_DEFAULT = {'name': 'Gabor', 'noise_level': 20.0, 'sigma': [0.5, 200], 'theta': 0.0}


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


def reformat_params(params):
    doc = document()
    for section_name, section_data in params.items():
        if isinstance(section_data, dict):
            section = table()
            for key, value in section_data.items():
                if section_name == "destriping" and key == "filters":
                    inline_array = array()
                    inline_array.multiline(False)
                    for filt in value:
                        t = inline_table()
                        t.update(filt)
                        inline_array.append(t)
                    section[key] = inline_array
                else:
                    section[key] = value
            doc[section_name] = section
        else:
            doc[section_name] = section_data
    return doc


def process(stack, process_name):
    stack.eval(process_steps=process_name, show_pbar=False, pbar_init=True)


def get_stack(dirname):
    fnames = hsorted(Path(dirname).glob("*.tif"))
    stack = [imread(fname) for fname in fnames]
    stack = np.stack(stack, axis=0)
    print("get_stack", stack.shape)
    return [(stack, {"name": dirname.name.upper()}, "image")]


class CollapsibleSection(QFrame):
    toggled = Signal(object)

    def __init__(self, parent, process_name: str, widget):
        super().__init__()
        self.parent = parent
        self.process_name = process_name
        self.widget = widget
        self.is_open = False

        self.setAcceptDrops(True)
        self.setObjectName(process_name)

        self.setFrameStyle(QFrame.NoFrame)
        self.setLineWidth(2)
        self.setStyleSheet(QFRAME_STYLE["transparent"].format(self.process_name))

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(5, 0, 0, 0)
        self.content.setVisible(False)

        self.toggle_button = QPushButton("►")
        self.toggle_button.setMaximumWidth(20)
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self.toggle)

        self.title_label = QLabel(process_name.upper())

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

        header_layout2 = QHBoxLayout()
        header_layout2.addWidget(self.checkbox)
        header_layout2.addWidget(self.run_button)
        header_layout2.addWidget(self.progress_bar)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.addLayout(header_layout)
        self.main_layout.addWidget(self.content)
        self.main_layout.addLayout(header_layout2)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)

    def toggle(self):
        self.is_open = not self.is_open
        self.content.setVisible(self.is_open)
        self.toggle_button.setText("▼" if self.is_open else "►")
        if self.is_open:
            self.setStyleSheet(QFRAME_STYLE['blue'].format(self.process_name))
            self.toggled.emit(self)
        else:
            self.setStyleSheet(QFRAME_STYLE['transparent'].format(self.process_name))

    def toggle_content_enabled(self, state):
        enabled = (state == Qt.Checked)
        self.content.setEnabled(enabled)
        self.run_button.setEnabled(enabled)

    def add_widget(self, widget):
        self.content_layout.addWidget(widget)
        self._linked_widget = widget  # store magicgui widget reference

    def run(self):
        if self.parent.stack is None:
            return

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

        # params updating
        params = get_params(self.widget.asdict())
        self.parent.stack.params[self.process_name] = params

        Process(target=process, args=(self.parent.stack, self.process_name)).start()

    def handle_result(self):
        result = get_stack(dirname=self.parent.stack.pathdir / 'process' / self.process_name)
        viewer = napari.current_viewer()
        for data, kwargs, layer_type in result:
            getattr(viewer, f"add_{layer_type}")(data, **kwargs)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            drag = QDrag(self)
            drag.setPixmap(self.grab())
            mime_data = QMimeData()
            mime_data.setText(self.objectName())
            drag.setMimeData(mime_data)
            drag.exec_(Qt.MoveAction)


class DragDropContainer(QWidget):
    def __init__(self):
        super().__init__()
        self.sections = []

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.setAcceptDrops(True)

    def add_section(self, section):
        self.layout.addWidget(section)
        self.sections.append(section)
        section.toggled.connect(self.on_section_toggled)

    def on_section_toggled(self, opened_section):
        for section in self.sections:
            if section != opened_section and section.is_open:
                section.toggle()

    def get_widget(self, name):
        widget = None
        for i in range(self.layout.count()):
            w = self.layout.itemAt(i).widget()
            if w.objectName() == name:
                widget = w
                break
        return widget, i

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        # find the moving item
        process_name = event.mimeData().text()
        dragged_widget, i0 = self.get_widget(name=process_name)
        if not dragged_widget:
            return

        drop_pos = event.pos()
        insert_at = self.layout.count() - 1

        for i in range(self.layout.count()):
            widget = self.layout.itemAt(i).widget()
            if drop_pos.y() < widget.y() + widget.height() // 2:
                insert_at = i  # insert position
                break

        if self.layout.itemAt(insert_at).widget().objectName() == 'registration_transformation':
            print('registration widgets cannot be separated')
            return

        self.layout.removeWidget(dragged_widget)
        self.layout.insertWidget(insert_at, dragged_widget)
        dragged_section = self.sections.pop(i0)
        self.sections.insert(insert_at, dragged_section)

        # registration widgets pairing
        if 'registration' in process_name:
            if process_name == 'registration_calculation':
                dragged_widget_2, i0 = self.get_widget(name='registration_transformation')
                insert_at_2 = insert_at + 1 if i0 > insert_at else insert_at
            elif process_name == 'registration_transformation':
                dragged_widget_2, i0 = self.get_widget(name='registration_calculation')
                insert_at_2 = insert_at if i0 > insert_at else insert_at - 1
            else:
                raise IOError
            self.layout.removeWidget(dragged_widget_2)
            self.layout.insertWidget(insert_at_2, dragged_widget_2)
            dragged_section = self.sections.pop(i0)
            self.sections.insert(insert_at_2, dragged_section)

        event.accept()


class FilterTableWidget(QWidget):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.filters = []

        self.table = QTableWidget(2, 4)
        self.table.setHorizontalHeaderLabels(["name", "noise_level", "sigma", "theta"])
        self.table.verticalHeader().setVisible(False)

        self.button = QPushButton("VALIDATE FILTERS")
        self.button.clicked.connect(self.handle_submit)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.table)
        layout.addWidget(self.button)
        self.setLayout(layout)

        self.set_filters([FILTER_DEFAULT])

    def clear(self):
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                self.table.setItem(row, col, QTableWidgetItem(""))

    def set_filters(self, filters: list[dict]):
        self.clear()
        for row, filter in enumerate(filters):
            self.add_filter(filter, row)
        self.center_all_cells()
        self.handle_submit()

    def add_filter(self, filter: dict, row: int = 0):
        self.table.setItem(row, 0, QTableWidgetItem(str(filter['name'])))
        self.table.setItem(row, 1, QTableWidgetItem(str(filter['noise_level'])))
        self.table.setItem(row, 2, QTableWidgetItem(str(filter['sigma'])))
        self.table.setItem(row, 3, QTableWidgetItem(str(filter['theta'])))

    def center_all_cells(self):
        for row in range(self.table.rowCount()):
            for col in range(self.table.columnCount()):
                item = self.table.item(row, col)
                if item:
                    item.setTextAlignment(Qt.AlignCenter)
        self.table.resizeColumnsToContents()
        self.table.resizeRowsToContents()

    def handle_submit(self):
        self.center_all_cells()
        self.filters.clear()
        for row in range(self.table.rowCount()):
            try:
                name = self.table.item(row, 0).text()
                noise = float(self.table.item(row, 1).text()) if self.table.item(row, 1) else 0.
                sigma = self.table.item(row, 2).text()
                sigma = ast.literal_eval(sigma) if sigma else []
                theta = float(self.table.item(row, 3).text()) if self.table.item(row, 3) else 0.
                self.filters.append({"name": name, "noise_level": noise, "sigma": sigma,
                                     "theta": theta})
                self.widget.filters.value = str(self.filters)
            except:
                pass
        print("filters", self.filters)


class CroppingPreview(QWidget):
    def __init__(self, widget):
        super().__init__()
        self.widget = widget

        self.button = QPushButton("SHOW/HIDE PREVIEW")
        self.button.clicked.connect(self.preview)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.button)
        self.setLayout(layout)

    def preview(self):
        name = 'area (CROPPING)'
        viewer = napari.current_viewer()
        if name in viewer.layers:
            del viewer.layers[name]
        else:
            xmin, xmax, ymin, ymax = ast.literal_eval(self.widget.area.value)
            rectangle = np.array([[ymin, xmin], [ymin, xmax], [ymax, xmax], [ymax, xmin]])
            viewer.add_shapes([rectangle],
                              shape_type='polygon',
                              edge_color='red',
                              edge_width=2,
                              face_color='transparent',
                              name=name
                              )
