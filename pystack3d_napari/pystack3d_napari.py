"""
Main functions dedicated to pystack3D processing
"""
from pathlib import Path
import napari
from magicgui import magic_factory, magicgui

from pystack3d import Stack3d
from pystack3d.stack3d import PROCESS_STEPS

from utils import DragDropContainer, CollapsibleSection


class PyStack3dNapari:

    def __init__(self):
        self.stack = None
        self.process_container = None

    def on_init(self, widget):
        layout = widget.native.layout()
        self.process_container = DragDropContainer()
        for process in PROCESS_STEPS[:2]:
            widget = eval(f"{process}_widget()")
            section = CollapsibleSection(self, process, widget)
            section.add_widget(widget.native)
            self.process_container.add_section(section)
        layout.addWidget(self.process_container)

    def create_widget(self):
        @magic_factory(widget_init=self.on_init,
                       call_button="INIT",
                       input_stack={"label": "Input Stack"})
        def napari_widget(input_stack: 'napari.layers.Image',
                          index_min: int = 0,
                          index_max: int = 9999):
            if hasattr(input_stack, 'source') and input_stack.source.path is not None:
                dirname = Path(input_stack.source.path)
            else:
                dirname = Path.cwd()

            self.stack = Stack3d(input_name=dirname, ignore_error=True)
            self.stack.params['ind_min'] = index_min
            self.stack.params['ind_max'] = index_max

        return napari_widget


@magic_factory(call_button=False)
def cropping_widget(area: str = "(0, 100, 0, 100)"):
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


def launch():
    """ Launch Napari with the 'drift_correction' pluggin """
    stack_napari = PyStack3dNapari()
    widget = stack_napari.create_widget()
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(widget(), area="right")
    napari.run()


if __name__ == "__main__":
    launch()
