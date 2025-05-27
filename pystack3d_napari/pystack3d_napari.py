"""
Main functions dedicated to pystack3D processing
"""
import ast
from pathlib import Path
from functools import wraps
import napari
from magicgui import magic_factory, magicgui
from qtpy.QtWidgets import QWidget, QVBoxLayout

from pystack3d import Stack3d
from pystack3d.stack3d import PROCESS_STEPS

from utils import DragDropContainer, CollapsibleSection, get_stack


def on_init(widget):
    layout = widget.native.layout()
    process_container = DragDropContainer()
    for process in PROCESS_STEPS[:2]:
        widget = eval(f"{process}_widget()")
        section = CollapsibleSection(process, widget)
        section.add_widget(widget.native)
        process_container.add_section(section)
    layout.addWidget(process_container)


@magic_factory(widget_init=on_init,
               call_button="INIT",
               input_stack={"label": "Input Stack"})
def napari_widget(input_stack: 'napari.layers.Image',
                  index_min: int = 0,
                  index_max: int = 9999):
    if hasattr(input_stack, 'source') and input_stack.source.path is not None:
        dirname = Path(input_stack.source.path)
    else:
        dirname = Path.cwd()

    global stack
    stack = Stack3d(input_name=dirname, ignore_error=True)
    stack.params['ind_min'] = index_min
    stack.params['ind_max'] = index_max


def process_widget(process_name, **kwargs):
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

    print(process_name)
    print('params', params)

    try:
        global stack
        stack.params[process_name] = params
        stack.eval(process_name)
        return get_stack(dirname=stack.pathdir / 'process' / process_name)
    except:
        return None


@magic_factory(call_button=False)
def cropping_widget(area: str = "(0, 9999, 0, 9999)"):
    pass


@magic_factory(call_button=False,
               dim={"choices": [2, 3]},
               # orders_poly_basis={"label": 'Orders or Poly basis'},
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


def launch():
    """ Launch Napari with the 'drift_correction' pluggin """
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(napari_widget(), area="right")
    napari.run()


if __name__ == "__main__":
    launch()
