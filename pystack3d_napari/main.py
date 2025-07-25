"""
Main functions dedicated to pystack3D processing
"""
import os
from pathlib import Path
import ast

import napari
from magicgui import magic_factory, magicgui
from qtpy.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QCheckBox
from qtpy.QtGui import QFont
from qtpy.QtCore import QObject, Signal

from pystack3d import Stack3d
from pystack3d_napari import FILTER_DEFAULT
from pystack3d_napari.widgets import (DragDropContainer, CollapsibleSection, FilterTableWidget,
                                      CroppingPreview, CompactLayouts, DiskRAMUsageWidget,
                                      SelectProjectDirWidget, LoadParamsWidget, SaveParamsWidget,
                                      get_napari_icon, add_layers, change_ndisplay)

PROCESS_NAMES = ['cropping', 'bkg_removal', 'intensity_rescaling',
                 'registration_calculation', 'registration_transformation',
                 'destriping', 'resampling', 'cropping_final']


class PyStack3dNapari(QObject):
    finish_signal = Signal()

    def __init__(self, project_dir=None, fname_toml=None):
        super().__init__()
        self.project_dir = project_dir
        self.fname_toml = fname_toml

        self.stack = None
        self.process_container = None
        self.process_names = PROCESS_NAMES
        self.nproc = 1

    def on_init(self, widget):
        widget.native.setFont(QFont("Segoe UI", 10))
        widget.native.setStyleSheet(""" * {padding: 0px; margin: 0px; spacing: 0px;} """)

        self.layout = widget.native.layout()

        self.init_widget = self.create_init_widget()
        show_button = QPushButton()
        show_button.setIcon(get_napari_icon("visibility"))
        show_button.setToolTip("Generate napari image(s)")
        show_button.setFixedSize(18, 18)
        show_button.clicked.connect(self.show_layers)
        button_container = QWidget()
        button_layout = QHBoxLayout(button_container)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.addWidget(self.init_widget['call_button'].native)
        button_layout.addWidget(show_button)
        self.init_widget.native.layout().addWidget(button_container)
        self.layout.addWidget(self.init_widget.native)

        # add Drag and Drop capabilities to the selection button
        qt_field = self.init_widget['project_dir'].native
        push_button = qt_field.findChild(QPushButton)
        sel_proj_dir = SelectProjectDirWidget(self)
        qt_field.layout().replaceWidget(push_button, sel_proj_dir)
        push_button.deleteLater()

        self.process_container = DragDropContainer(self.process_names)
        for process_name in self.process_names:
            process_widget = eval(f"{process_name}_widget()")
            section = CollapsibleSection(self, process_name, process_widget)
            section.add_widget(process_widget.native)
            self.process_container.add_widget(section)
        self.layout.addWidget(self.process_container)

        run_all_widget = self.create_run_all_widget()
        self.layout.addWidget(run_all_widget.native)

        load_save_widget = QWidget()
        hlayout = QHBoxLayout()
        load_params_widget = LoadParamsWidget(self)
        save_params_widget = SaveParamsWidget(self)
        doc_widget = QLabel('<a href="https://cea-metrocarac.github.io/pystack3d">DOC</a>')
        doc_widget.setOpenExternalLinks(True)
        doc_widget.setFixedWidth(30)

        hlayout.addWidget(load_params_widget)
        hlayout.addWidget(save_params_widget)
        hlayout.addWidget(doc_widget)
        load_save_widget.setLayout(hlayout)
        self.layout.addWidget(load_save_widget)

        cbox_visu3D = QCheckBox(" Enable 3D visualisation")
        cbox_visu3D.setChecked(False)
        cbox_visu3D.stateChanged.connect(change_ndisplay)
        self.layout.addWidget(cbox_visu3D)

        usage_widget = DiskRAMUsageWidget()
        self.layout.addWidget(usage_widget)

        widgets = self.process_container.widgets()
        widgets += [self.init_widget.native, run_all_widget.native, load_save_widget, usage_widget]
        CompactLayouts.apply(widgets)

        self.init_widget.nproc.changed.connect(lambda val: setattr(self, 'nproc', val))

        if self.fname_toml:
            load_params_widget.load_params(self.fname_toml)

        if self.project_dir:
            self.init_widget(project_dir=Path(self.project_dir))

    def show_layers(self):
        if self.stack:
            add_layers(dirname=self.project_dir,
                       channels=self.stack.params['channels'],
                       ind_min=self.stack.params['ind_min'],
                       ind_max=self.stack.params['ind_max'],
                       is_init=True)

    def create_widgets(self):
        @magic_factory(widget_init=self.on_init,
                       call_button=False)
        def widgets():
            pass

        return widgets

    def create_init_widget(self):
        @magicgui(call_button="INIT",
                  project_dir={"label": "Project Dir.", "mode": "d"},
                  channels={"label": "Channels",
                            "tooltip": "List the names of the sub-folders "
                                       "for several channels processing:\n"
                                       "ex: ['Channel-1', 'Channel-2']"},
                  ind_min={"label": "Index Min."},
                  ind_max={"label": "Index Max."},
                  nproc={"label": "Nprocs", 'min': 1, 'max': os.cpu_count(),
                         "tooltip": "Number of processors.\nCan be changed at anytime."},
                  )
        def init_widget(project_dir: Path = self.project_dir,
                        ind_min: int = 0,
                        ind_max: int = 99999,
                        channels: str = "",
                        nproc: int = 1):
            if project_dir is None:
                return []

            self.project_dir = project_dir
            channels = ['.'] if channels == '' else ast.literal_eval(channels)

            self.stack = Stack3d(input_name=project_dir, ignore_error=True)
            self.stack.params['channels'] = channels
            self.stack.params['ind_min'] = ind_min
            self.stack.params['ind_max'] = ind_max
            self.stack.params['nproc'] = nproc
            self.stack.params['process_steps'] = self.process_names

            self.show_layers()

        return init_widget

    def create_run_all_widget(self):
        @magicgui(call_button="RUN ALL")
        def run_all_widget():
            self.sections = []
            for section in self.process_container.widgets():
                if section.checkbox.isChecked():
                    self.sections.append(section)
            self.finish_signal.connect(self.run_next_step)
            self.run_next_step()

        return run_all_widget

    def run_next_step(self):
        if len(self.sections) != 0:
            section = self.sections.pop(0)
            section.run(callback=self.run_next_step)
        else:
            self.finish_signal.disconnect(self.run_next_step)


def on_init_cropping(widget):
    layout = widget.native.layout()
    layout.addWidget(CroppingPreview(widget))


@magic_factory(widget_init=on_init_cropping, call_button=False)
def cropping_widget(area: str = "(0, 9999, 0, 9999)"):
    pass


@magic_factory(call_button=False,
               dim={"choices": [2, 3]},
               weight_func={"choices": ['HuberT', 'Hammel', 'None']})
def bkg_removal_widget(dim: int = 3,
                       poly_basis: str = "",
                       orders: str = "[1, 2, 1]",
                       cross_terms: bool = True,
                       skip_factors: str = "[10, 10, 10]",
                       threshold_min: str = "",
                       threshold_max: str = "",
                       weight_func: str = 'HuberT',
                       preserve_avg: bool = False,
                       ):
    pass


@magic_factory(call_button=False)
def intensity_rescaling_widget(nbins: int = 256,
                               range_bins: str = "",
                               filter_size: int = -1,
                               ):
    pass


def on_init_destriping(widget):
    layout = widget.native.layout()
    widget._filters_widget = FilterTableWidget(widget)
    layout.addWidget(widget._filters_widget)


@magic_factory(widget_init=on_init_destriping, call_button=False,
               filters={"visible": False})
def destriping_widget(maxit: int = 200,
                      cvg_threshold: float = 1e-2,
                      filters: str = str(FILTER_DEFAULT)
                      ):
    pass


@magic_factory(call_button=False,
               transformation={
                   "choices": ['TRANSLATION', 'RIGID_BODY', 'SCALED_ROTATION', 'AFFINE']})
def registration_calculation_widget(area: str = "",
                                    threshold: str = "",
                                    nb_blocks: str = "[1, 1]",
                                    transformation: str = "TRANSLATION",
                                    ):
    pass


@magic_factory(call_button=False,
               mode={"choices": ['constant', 'edge', 'symmetric', 'reflect', 'wrap']})
def registration_transformation_widget(constant_drift: str = "",
                                       box_size_averaging: str = "",
                                       subpixel: bool = True,
                                       mode: str = "edge",
                                       cropping: bool = False,
                                       ):
    pass


@magic_factory(call_button=False)
def resampling_widget(policy: str = "slice_{slice_nb}_z={z_coord}um.tif",
                      dz: float = 0.01,
                      ):
    pass


def on_init_cropping_final(widget):
    layout = widget.native.layout()
    layout.addWidget(CroppingPreview(widget, is_final=True))


@magic_factory(widget_init=on_init_cropping_final, call_button=False)
def cropping_final_widget(area: str = "(0, 9999, 0, 9999)"):
    pass


def launch(project_dir=None, fname_toml=None):
    """ Launch Napari with the 'drift_correction' pluggin """
    stack_napari = PyStack3dNapari(project_dir=project_dir, fname_toml=fname_toml)
    stack_napari.project_dir = project_dir
    stack_napari.fname_toml = fname_toml
    widgets = stack_napari.create_widgets()
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(widgets(), area="right", name='pystack3d')
    viewer.window._qt_window.resize(1200, 850)
    viewer.window._qt_viewer.viewerButtons.ndisplayButton.setEnabled(False)
    napari.run()


if __name__ == "__main__":
    launch()
