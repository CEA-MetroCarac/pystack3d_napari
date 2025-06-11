import os
import warnings
from pathlib import Path
import ast
from threading import Thread
import numpy as np
import napari

from qtpy.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
                            QFrame, QProgressBar, QTableWidget, QTableWidgetItem)
from qtpy.QtCore import Qt, QMimeData, QSize, Signal
from qtpy.QtGui import QDrag, QIcon

from pystack3d_napari.utils import get_stacks, convert_params, update_progress
from pystack3d_napari import KWARGS_RENDERING, FILTER_DEFAULT

QFRAME_STYLE = {'transparent': "#{} {{ border: 2px solid transparent; border-radius: 6px; }}",
                'blue': "#{} {{ border: 2px solid black; border-radius: 6px; }}"}

warnings.filterwarnings("ignore",
                        message="Starting a Matplotlib GUI outside of the main thread will likely "
                                "fail.")


def get_napari_icon(icon_name):
    path = Path(os.path.dirname(napari.__file__)) / 'resources' / 'icons' / f'{icon_name}.svg'
    icon = QIcon(str(path))
    return QIcon(icon.pixmap(QSize(24, 24), QIcon.Disabled))


class CompactLayouts:
    @staticmethod
    def apply(widgets):
        for widget in widgets:
            layout = widget.layout()
            layout.setContentsMargins(0, 0, 4, 0)
            layout.setSpacing(1)


class CollapsibleSection(QFrame):
    toggled = Signal(object)
    pbar_signal = Signal(int)
    finish_signal = Signal()

    def __init__(self, parent, process_name: str, widget):
        super().__init__()
        self.parent = parent
        self.process_name = process_name
        self.widget = widget
        self.is_open = False

        self.setAcceptDrops(True)
        self.setObjectName(process_name)

        self.pbar_signal.connect(self.update_progress_bar)

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

        show_button = QPushButton()
        if process_name == "registration_calculation":
            show_button.setIcon(get_napari_icon("visibility_off"))
        else:
            show_button.setIcon(get_napari_icon("visibility"))
            show_button.clicked.connect(self.show_results)

        remove_button = QPushButton()
        remove_button.setIcon(get_napari_icon("delete"))
        remove_button.clicked.connect(self.remove_history)

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(self.title_label)

        header_layout2 = QHBoxLayout()
        header_layout2.addWidget(self.checkbox)
        header_layout2.addWidget(self.run_button)
        header_layout2.addWidget(self.progress_bar)
        header_layout2.addWidget(show_button)
        header_layout2.addWidget(remove_button)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.addLayout(header_layout)
        self.main_layout.addWidget(self.content)
        self.main_layout.addLayout(header_layout2)

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

    def run(self, callback=None):
        if self.parent.stack is None:
            return

        Thread(target=update_progress,
               args=(self.parent.stack.queue_incr, self.pbar_signal, self.finish_signal)
               ).start()

        params = convert_params(self.widget.asdict())
        self.parent.stack.params[self.process_name] = params
        self.parent.stack.params['nproc'] = self.parent.nproc
        Thread(target=self.parent.stack.eval,
               kwargs={'process_steps': self.process_name, 'show_pbar': False, 'pbar_init': True},
               ).start()

        if callback:
            self.finish_signal.connect(self.parent.run_next_step)

    def update_progress_bar(self, percent):
        self.progress_bar.setValue(percent)

    def show_results(self):
        if self.parent.stack:
            results = get_stacks(dirname=self.parent.stack.pathdir / 'process' / self.process_name,
                                 channels=self.parent.stack.params['channels'])
            viewer = napari.current_viewer()
            for result in results:
                for data, kwargs, layer_type in result:
                    getattr(viewer, f"add_{layer_type}")(data, **kwargs, **KWARGS_RENDERING)

    def remove_history(self):
        if self.parent.stack:
            history = self.parent.stack.params['history']
            if self.process_name in history:
                ind = history.index(self.process_name)
                self.parent.stack.params['history'] = history[:ind]

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            drag = QDrag(self)
            drag.setPixmap(self.grab())
            mime_data = QMimeData()
            mime_data.setText(self.objectName())
            drag.setMimeData(mime_data)
            drag.exec_(Qt.MoveAction)


class DragDropContainer(QWidget):
    def __init__(self, process_steps):
        super().__init__()
        self.process_steps = process_steps
        self.layout = QVBoxLayout(self)
        self.setAcceptDrops(True)

    def widgets(self):
        return [self.layout.itemAt(i).widget() for i in range(self.layout.count())]

    def add_widget(self, widget):
        self.layout.addWidget(widget)
        widget.toggled.connect(self.on_widget_toggled)

    def on_widget_toggled(self, opened_widget):
        for widget in self.widgets():
            if widget != opened_widget and widget.is_open:
                widget.toggle()

    def get_widget(self, name):
        for i, widget in enumerate(self.widgets()):
            if widget.objectName() == name:
                return widget, i
        return None, -1

    def reorder_widgets(self, process_steps):
        widgets = self.widgets()

        for widget in widgets:
            if widget.process_name not in process_steps:
                widget.checkbox.setChecked(False)

        for i, process_name in enumerate(process_steps):
            self.move_widget(process_name, insert_at=i)

        self.process_steps = [widget.process_name for widget in widgets]

    def move_widget(self, process_name, insert_at):
        widget, i0 = self.get_widget(name=process_name)
        self.layout.removeWidget(widget)
        self.layout.insertWidget(insert_at, widget)

    def dragEnterEvent(self, event):
        event.accept()

    def dragMoveEvent(self, event):
        event.accept()

    def dropEvent(self, event):
        process_name = event.mimeData().text()

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

        self.move_widget(process_name, insert_at)

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

        self.process_steps = [widget.process_name for widget in self.widgets()]

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

    def sizeHint(self):
        return QSize(0, 0)  # force automatic readjustment

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

        self.button = QPushButton("SHOW/HIDE AREA")
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
