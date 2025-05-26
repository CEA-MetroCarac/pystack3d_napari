"""
Main functions dedicated to pystack3D processing
"""
import napari
from magicgui import magic_factory

from pystack3d import Stack3d

from utils import DragDropContainer, CollapsibleSection


def napari_widget():
    container = DragDropContainer()

    crop = cropping_widget()
    bkg = bkg_removal_widget()

    cropping_section = CollapsibleSection("Cropping")
    cropping_section.add_widget(crop.native)

    bkg_removal_section = CollapsibleSection("Background_removal")
    bkg_removal_section.add_widget(bkg.native)

    container.add_section(cropping_section)
    container.add_section(bkg_removal_section)

    return container


@magic_factory(call_button=False)
def cropping_widget(area: str = "(0, 9999, 0, 9999)"):
    return


@magic_factory(call_button=False)
def bkg_removal_widget(dim: int = 3,
                       poly_basis: str = "",
                       orders: str = "[1, 2, 1]",
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
