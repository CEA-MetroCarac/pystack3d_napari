import os
import warnings
from pathlib import Path
import shutil
import ast
from threading import Thread, Event
import numpy as np
from tomlkit import dumps, parse
import napari
from napari.utils.transforms import Affine

from qtpy.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QCheckBox,
                            QFrame, QProgressBar, QTableWidget, QTableWidgetItem, QFileDialog,
                            QMessageBox, QDialog)
from qtpy.QtCore import Qt, QMimeData, QSize, Signal, QTimer, QObject, QEvent
from qtpy.QtGui import QDrag, QIcon

from pystack3d.utils import reformat_params

from pystack3d_napari.utils import get_layers, convert_params, update_progress, get_params
from pystack3d_napari.utils import get_disk_info, get_ram_info, update_widgets_params
from pystack3d_napari import KWARGS_RENDERING, FILTER_DEFAULT

QFRAME_STYLE = {'transparent': "#{} {{ border: 2px solid transparent; border-radius: 6px; }}",
                'blue': "#{} {{ border: 2px solid black; border-radius: 6px; }}"}

msg = "Starting a Matplotlib GUI outside of the main thread will likely fail."
warnings.filterwarnings("ignore", message=msg)
warnings.filterwarnings("ignore", category=UserWarning)


def get_napari_icon(icon_name):
    path = Path(os.path.dirname(napari.__file__)) / 'resources' / 'icons' / f'{icon_name}.svg'
    icon = QIcon(str(path))
    return QIcon(icon.pixmap(QSize(24, 24), QIcon.Disabled))


def add_layers(dirname, channels, ind_min=0, ind_max=99999, is_init=False):
    layers = get_layers(dirname, channels, ind_min=ind_min, ind_max=ind_max, is_init=is_init)
    viewer = napari.current_viewer()
    for data, kwargs, layer_type in layers:
        getattr(viewer, f"add_{layer_type}")(data, **kwargs, **KWARGS_RENDERING)


def size(layers):
    size_tot = 0
    for layer in layers:
        if hasattr(layer, 'data'):
            data = layer.data
        elif isinstance(layer, list) and isinstance(layer[0], tuple):
            data = layer[0][0]
        else:
            continue

        if hasattr(data, 'nbytes'):
            size_tot += data.nbytes
        elif isinstance(data, list) and all(hasattr(arr, 'nbytes') for arr in data):
            size_tot += sum(arr.nbytes for arr in data)
        elif hasattr(data, 'size') and hasattr(data, 'dtype'):
            size_tot += data.size * data.dtype.itemsize

    return size_tot


def change_ndisplay(state):
    enabled = (state == Qt.Checked)
    viewer = napari.current_viewer()
    viewer.window._qt_viewer.viewerButtons.ndisplayButton.setEnabled(enabled)
    if enabled:
        msg = "Displaying large datasets in 3D may crash your system.\n" \
              "Think to check your available RAM !"
        QMessageBox.warning(viewer.window._qt_window, "3D View Enabled", msg)
    else:
        viewer.dims.ndisplay = 2


def show_warning(msg, parent=None):
    dialog = QDialog(parent)
    dialog.setWindowModality(Qt.ApplicationModal)
    dialog.setWindowFlags(dialog.windowFlags() | Qt.WindowStaysOnTopHint)

    layout = QVBoxLayout()
    layout.setContentsMargins(20, 20, 20, 20)
    layout.setSpacing(15)

    label = QLabel(msg)
    layout.addWidget(label)

    btn = QPushButton("OK")
    layout.addWidget(btn, alignment=Qt.AlignCenter)

    def on_ok():
        dialog.accept()

    btn.clicked.connect(on_ok)

    dialog.setLayout(layout)
    dialog.exec_()


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
            show_button.setToolTip(f"No images related to {process_name}")
            show_button.setEnabled(False)
        else:
            show_button.setIcon(get_napari_icon("visibility"))
            show_button.setToolTip("Generate napari image(s)")
            show_button.clicked.connect(self.show_results)

        delete_button = QPushButton()
        delete_button.setIcon(get_napari_icon("delete"))
        delete_button.setToolTip(f"Delete all processed data from '{process_name}' in the history")
        delete_button.clicked.connect(self.delete)

        header_layout = QHBoxLayout()
        header_layout.addWidget(self.toggle_button)
        header_layout.addWidget(self.title_label)

        header_layout2 = QHBoxLayout()
        header_layout2.addWidget(self.checkbox)
        header_layout2.addWidget(self.run_button)
        header_layout2.addWidget(self.progress_bar)
        header_layout2.addWidget(show_button)
        header_layout2.addWidget(delete_button)

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

        progress_done = Event()
        eval_done = Event()

        def wrapped_update_progress():
            update_progress(nchannels=len(self.parent.stack.channels(self.process_name)),
                            nproc=self.parent.nproc,
                            queue_incr=self.parent.stack.queue_incr,
                            pbar_signal=self.pbar_signal)
            progress_done.set()

        def wrapped_eval():
            params = convert_params(self.widget.asdict())
            self.parent.stack.params[self.process_name] = params
            self.parent.stack.params['nproc'] = self.parent.nproc
            self.parent.stack.eval(process_steps=self.process_name,
                                   show_pbar=False,
                                   pbar_init=True)
            eval_done.set()

        def monitor():
            progress_done.wait()
            eval_done.wait()
            self.parent.finish_signal.emit()

        Thread(target=wrapped_update_progress, daemon=True).start()
        Thread(target=wrapped_eval, daemon=True).start()
        Thread(target=monitor, daemon=True).start()

    def update_progress_bar(self, percent):
        self.progress_bar.setValue(percent)

    def show_results(self):
        if self.parent.stack:
            add_layers(dirname=self.parent.stack.pathdir / 'process' / self.process_name,
                       channels=self.parent.stack.params['channels'])

    def delete(self):
        if self.parent.stack:
            history = self.parent.stack.params['history']
            if self.process_name in history:
                ind = history.index(self.process_name)
                process_names = history[ind:]
                msg = (f"You are about to delete all the processed data for "
                       f"{str(process_names)[1:-1]} located in 'project_dir/process'.\n\n"
                       f"Do you confirm ?")
                reply = QMessageBox.question(None, "Confirm", msg,
                                             QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
                if reply == QMessageBox.Yes:
                    for section in self.parent.process_container.widgets():
                        if section.process_name in process_names:
                            section.progress_bar.setValue(0)
                            history.remove(section.process_name)
                            dir_process = self.parent.project_dir / 'process' / section.process_name
                            if dir_process.is_dir():
                                shutil.rmtree(dir_process)

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


class CroppingPreview(QWidget):
    def __init__(self, widget, is_final=False):
        super().__init__()
        self.widget = widget
        self.name = 'area (CROPPING FINAL)' if is_final else 'area (CROPPING)'

        self.button = QPushButton("SHOW/HIDE AREA")
        self.button.clicked.connect(self.preview)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(5)
        layout.addWidget(self.button)
        self.setLayout(layout)

    def preview(self):
        viewer = napari.current_viewer()
        if self.name in viewer.layers:
            del self.watcher
            del viewer.layers[self.name]
        else:
            selected = viewer.layers.selection
            selected_images = [layer for layer in selected if
                               isinstance(layer, napari.layers.Image)]
            n_select = len(selected_images)
            if n_select != 1:
                msg = "WARNING: A{}layer corresponding to the stack with the appropriate " \
                      "dimensions for cropping must be selected."
                msg = msg.format(' ') if n_select == 0 else msg.format(' single ')
                show_warning(msg)
            else:
                layer = selected_images[0]
                h, w = layer.data.shape[-2:]
                xmin, xmax, ymin, ymax = ast.literal_eval(self.widget.area.value)
                xmin, xmax = max(xmin, 0), min(xmax, w)
                ymin, ymax = min(h - ymin, h), max(h - ymax, 0)
                rectangle = np.array([[ymin, xmin], [ymin, xmax], [ymax, xmax], [ymax, xmin]])
                area_layer = viewer.add_shapes([rectangle], edge_color='red', edge_width=2,
                                               face_color='transparent', name=self.name)
                area_layer.mode = 'transform'

                def on_shape_change():
                    affine = Affine(affine_matrix=area_layer.affine.affine_matrix)
                    coords = affine(area_layer.data[0])
                    coords[:, 1] = np.clip(coords[:, 1], 0, w)  # x
                    coords[:, 0] = np.clip(coords[:, 0], 0, h)  # y
                    area_layer.data = [coords]
                    area_layer.affine = Affine()  # reset affine to avoid applying again
                    xmin, xmax = int(coords[:, 1].min()), int(coords[:, 1].max())
                    ymin, ymax = int(h - coords[:, 0].max()), int(h - coords[:, 0].min())
                    self.widget.area.value = str([xmin, xmax, ymin, ymax])

                self.watcher = MouseReleaseWatcher(on_shape_change)
                viewer.window._qt_viewer.canvas.native.installEventFilter(self.watcher)


class DiskRAMUsageWidget(QWidget):
    def __init__(self):
        super().__init__()
        self.usages = ['Disk', 'RAM']
        self.pbars = []
        self.labels = []

        self.init_ui()
        self.update_usage()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_usage)
        self.timer.start(1000)

    def init_ui(self):

        layout = QVBoxLayout()

        for _ in range(len(self.usages)):
            hlayout = QHBoxLayout()
            pbar = QProgressBar()
            pbar.setFixedWidth(40)
            label = QLabel()
            hlayout.addWidget(pbar)
            hlayout.addWidget(label)
            layout.addLayout(hlayout)

            self.pbars.append(pbar)
            self.labels.append(label)

        self.setLayout(layout)

    def update_usage(self):
        for usage, pbar, label in zip(self.usages, self.pbars, self.labels):
            total, used, _ = eval(f"get_{usage.lower()}_info()")  # get_ram_info or get_disk_info
            percent = int(100 * used / total)
            pbar.setValue(percent)
            self.update_color(percent, pbar)
            label.setText(f" {usage} used / total : "
                          f"{used / 1_073_741_824:.2f} / {total / 1_073_741_824:.2f} (GB)")

    def update_color(self, percent, pbar):
        if percent < 70:
            color = "#4caf50"  # green
        elif percent < 90:
            color = "#ff9800"  # orange
        else:
            color = "#f44336"  # red

        pbar.setStyleSheet(f"""
            QProgressBar {{border: 1px solid grey; border-radius: 5px; text-align: center;}}
            QProgressBar::chunk {{background-color: {color}; width: 1px;}} """)


class DragDropPushButton(QPushButton):
    def __init__(self, parent, label, callback, mode):
        super().__init__(label)
        self.setToolTip("Click OR Drag and Drop")
        self.parent = parent
        self.callback = callback
        self.mode = mode
        self.setAcceptDrops(True)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                path = Path(url.toLocalFile())
                if self._is_valid(path):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = Path(url.toLocalFile())
            if self._is_valid(path):
                self.callback(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def _is_valid(self, path: Path):
        if self.mode == ".toml file":
            return path.is_file() and path.suffix == ".toml"
        elif self.mode == "dir":
            return path.is_dir()
        return False


class SelectProjectDirWidget(DragDropPushButton):
    def __init__(self, parent):
        super().__init__(parent, label='  Select  ', callback=self.select_project_dir, mode="dir")

        self.clicked.connect(self.select_project_dir_from_filedialog)

    def select_project_dir_from_filedialog(self):
        project_dir = QFileDialog.getExistingDirectory()
        if project_dir:
            self.select_project_dir(project_dir)

    def select_project_dir(self, project_dir):
        self.parent.project_dir = Path(project_dir)
        self.parent.init_widget['project_dir'].value = Path(project_dir)


class LoadParamsWidget(DragDropPushButton):
    def __init__(self, parent):
        super().__init__(parent, label='LOAD PARAMS', callback=self.load_params, mode=".toml file")

        self.clicked.connect(self.load_params_from_filedialog)

    def load_params_from_filedialog(self):
        fname_toml, _ = QFileDialog.getOpenFileName(filter="TOML files (*.toml)")
        if fname_toml:
            self.load_params(fname_toml)

    def load_params(self, fname_toml):
        with open(fname_toml, 'r') as fid:
            params = dict(parse(fid.read()))
            update_widgets_params(params, self.parent.init_widget, self.parent.process_container)


class SaveParamsWidget(DragDropPushButton):
    def __init__(self, parent):
        super().__init__(parent, label='SAVE PARAMS', callback=self.save_params, mode=".toml file")

        self.clicked.connect(self.save_params_from_filedialog)

    def save_params_from_filedialog(self):
        fname_toml, _ = QFileDialog.getSaveFileName(filter="TOML files (*.toml)")
        if fname_toml:
            self.save_params(fname_toml)

    def save_params(self, fname_toml):
        params = get_params(self.parent.init_widget, keep_null_string=False)
        params['process_steps'] = self.parent.process_container.process_names
        params['history'] = self.parent.stack.params['history'] if self.parent.stack else []

        for section in self.parent.process_container.widgets():
            params[section.process_name] = get_params(section.widget, keep_null_string=False)

        with open(fname_toml, 'w') as fid:
            fid.write(dumps(reformat_params(params)))


class MouseReleaseWatcher(QObject):
    def __init__(self, callback):
        super().__init__()
        self.callback = callback

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonRelease:
            self.callback()
        return False


if __name__ == "__main__":
    import sys
    from qtpy.QtWidgets import QApplication

    app = QApplication(sys.argv)
    w = DiskRAMUsageWidget()
    w.show()
    sys.exit(app.exec_())
