"""
Main functions dedicated to pystack3D processing
"""
import napari
from magicgui import magic_factory, magicgui
from qtpy.QtWidgets import QWidget, QVBoxLayout

from pystack3d import Stack3d
from pystack3d.stack3d import PROCESS_STEPS

from utils import DragDropContainer, CollapsibleSection


def napari_widget():
    container = QWidget()
    layout = QVBoxLayout(container)

    layout.addWidget(params_widget.native)

    process_container = DragDropContainer()
    for process in PROCESS_STEPS[:2]:
        section = CollapsibleSection(process)
        widget = eval(f"{process}_widget()")
        section.add_widget(widget.native)
        process_container.add_section(section)

    layout.addWidget(process_container)

    return container


@magicgui(call_button="RUN ALL", input_stack={"label": "Input Stack"})
def params_widget(input_stack: 'napari.layers.Image',
                  index_min: int = 0,
                  index_max: int = 9999):
    pass


@magic_factory(call_button=False)
def cropping_widget(area: str = "(0, 9999, 0, 9999)"):
    return


@magic_factory(call_button=False,
               dim={"choices": [2, 3]},
               orders_poly_basis={"label": 'Orders or Poly basis'},
               weight_func={"choices": ['HuberT', 'Hammel', 'Leastsq']})
def bkg_removal_widget(dim: int = 3,
                       orders_poly_basis: str = "[1, 2, 1]",
                       cross_terms: bool = True,
                       skip_factors: str = "[10, 10, 10]",
                       threshold_min: float = 0,
                       threshold_max: float = 9999.,
                       weight_func: str = 'HuberT',
                       preserve_avg: bool = True,
                       ):
    return


def launch():
    """ Launch Napari with the 'drift_correction' pluggin """
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(napari_widget(), area="right")
    napari.run()


if __name__ == "__main__":
    launch()
