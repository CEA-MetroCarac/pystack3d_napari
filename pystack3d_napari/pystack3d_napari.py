"""
Main functions dedicated to pystack3D processing
"""
import ast
import os
from pathlib import Path
from tomlkit import dumps, parse
import numpy as np
import napari
from magicgui import magic_factory, magicgui
from qtpy.QtWidgets import QWidget, QHBoxLayout, QFileDialog
from qtpy.QtGui import QFont

from pystack3d import Stack3d
from pystack3d.stack3d import PROCESS_STEPS

from utils import DragDropContainer, CollapsibleSection, FilterTableWidget, CroppingPreview
from utils import reformat_params
from utils import FILTER_DEFAULT

PROCESS_STEPS.remove('intensity_rescaling_area')


class PyStack3dNapari:

    def __init__(self):
        self.input_stack = None
        self.stack = None
        self.process_container = None
        self.process_steps = PROCESS_STEPS
        self.nproc = 1

    def on_init(self, widget):
        widget.native.setFont(QFont("Segoe UI", 10))
        widget.native.setStyleSheet(""" QWidget {padding: 0px; margin: 0px;}
                                        QFormLayout {margin: 0px; spacing: 4px;} """)

        self.layout = widget.native.layout()

        self.init_widget = self.create_init_widget()
        self.layout.addWidget(self.init_widget.native)

        self.process_container = DragDropContainer(self.process_steps)
        for process_name in self.process_steps:
            process_widget = eval(f"{process_name}_widget()")
            section = CollapsibleSection(self, process_name, process_widget)
            section.add_widget(process_widget.native)
            self.process_container.add_widget(section)
        self.layout.addWidget(self.process_container)

        run_all_widget = self.create_run_all_widget()
        self.layout.addWidget(run_all_widget.native)

        load_save_widget = QWidget()
        hlayout = QHBoxLayout()
        hlayout.setSpacing(5)
        hlayout.addWidget(self.create_load_toml_widget().native)
        hlayout.addWidget(self.create_save_toml_widget().native)
        load_save_widget.setLayout(hlayout)
        self.layout.addWidget(load_save_widget)

        widget.input_stack.changed.connect(lambda val: setattr(self, 'input_stack', val))
        self.init_widget.nproc.changed.connect(lambda val: setattr(self, 'nproc', val))

    def create_widgets(self):
        @magic_factory(widget_init=self.on_init,
                       call_button=False,
                       input_stack={"label": "Input Stack"})
        def widgets(input_stack: 'napari.layers.Image'):
            pass

        return widgets

    def create_init_widget(self):
        @magicgui(call_button="(RE)INIT",
                  nproc={'min': 1, 'max': os.cpu_count()})
        def init_widget(index_min: int = 0,
                        index_max: int = 9999,
                        nproc: int = 1):

            if not self.input_stack:
                return

            if hasattr(self.input_stack, 'source') and self.input_stack.source.path is not None:
                dirname = Path(self.input_stack.source.path)
            else:
                dirname = Path.cwd()

            # remove .toml files among stack
            fnames = sorted(dirname.iterdir())
            inds = [i for i, fname in enumerate(fnames) if fname.suffix == ".toml"]
            self.input_stack.data = np.delete(self.input_stack.data, inds, axis=0)

            self.stack = Stack3d(input_name=dirname, ignore_error=True)
            self.stack.params['ind_min'] = index_min
            self.stack.params['ind_max'] = index_max
            self.stack.params['nproc'] = nproc
            self.stack.params['process_steps'] = self.process_steps

        return init_widget

    def create_run_all_widget(self):
        @magicgui(call_button="RUN ALL")
        def run_all_widget():
            for section in self.process_container.widgets():
                if section.checkbox.isChecked():
                    section.run()

        return run_all_widget

    def create_load_toml_widget(self):
        @magicgui(call_button="LOAD PARAMS")
        def load_toml_widget():
            fname_toml, _ = QFileDialog.getOpenFileName(filter="TOML files (*.toml)")
            if fname_toml:
                with open(fname_toml, 'r') as fid:
                    data = parse(fid.read())

                    for key, value in data.items():
                        if isinstance(value, dict):
                            continue
                        if hasattr(self.init_widget, key):
                            try:
                                setattr(self.init_widget, key, value)
                            except Exception as e:
                                print(f"[init_widget] Error with '{key}': {e}")
                        if key == 'process_steps':
                            self.process_container.reorder_widgets(value)

                    # update 'process'_widget parameters
                    for section in self.process_container.widgets():
                        section_name = section.process_name
                        widget = section.widget
                        if section_name in data:
                            section_data = data[section_name]
                            for key, value in section_data.items():
                                try:
                                    attr = getattr(widget, key)
                                    attr.value = value
                                    if key == "filters" and hasattr(widget, "_filters_widget"):
                                        widget._filters_widget.set_filters(value)
                                except Exception as e:
                                    print(f"[{section_name}] Error with '{key}': {e}")

        return load_toml_widget

    def create_save_toml_widget(self):
        @magicgui(call_button="SAVE PARAMS")
        def save_toml_widget():
            def get_params(widget, keep_null_string=True):
                params = {}
                for name in widget._function.__annotations__:
                    if hasattr(widget, name):
                        value = getattr(widget, name).value
                        try:
                            value = ast.literal_eval(value)
                        except:
                            pass
                        if keep_null_string or value != "":
                            params.update({name: value})
                return params

            params = get_params(self.init_widget, keep_null_string=False)
            params['process_steps'] = self.process_container.process_steps
            params['history'] = self.stack.params['history'] if self.stack else []

            for section in self.process_container.widgets():
                params[section.process_name] = get_params(section.widget, keep_null_string=False)

            print(params)

            fname_toml, _ = QFileDialog.getSaveFileName(filter="TOML files (*.toml)")
            if fname_toml:
                with open(fname_toml, 'w') as fid:
                    # dump(self.params, fid)
                    fid.write(dumps(reformat_params(params)))

        return save_toml_widget


def on_init_cropping(widget):
    layout = widget.native.layout()
    layout.addWidget(CroppingPreview(widget))


@magic_factory(widget_init=on_init_cropping, call_button=False)
def cropping_widget(area: str = "(0, 9999, 0, 9999)"):
    pass


@magic_factory(call_button=False,
               dim={"choices": [2, 3]},
               weight_func={"choices": ['HuberT', 'Hammel', 'Leastsq']})
def bkg_removal_widget(dim: int = 3,
                       poly_basis: str = "",
                       orders: str = "[1, 2, 1]",
                       cross_terms: bool = True,
                       skip_factors: str = "[10, 10, 10]",
                       threshold_min: str = "",
                       threshold_max: str = "",
                       weight_func: str = 'HuberT',
                       preserve_avg: bool = True,
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
def registration_calculation_widget(area: str = "[0, 99999, 0, 99999]",
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


@magic_factory(call_button=False)
def cropping_final_widget(area: str = "(0, 9999, 0, 9999)"):
    pass


def launch():
    """ Launch Napari with the 'drift_correction' pluggin """
    stack_napari = PyStack3dNapari()
    widgets = stack_napari.create_widgets()
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(widgets(), area="right")
    viewer.window._qt_window.adjustSize()
    viewer.window._qt_window.resize(viewer.window._qt_window.sizeHint())
    napari.run()


if __name__ == "__main__":
    launch()
