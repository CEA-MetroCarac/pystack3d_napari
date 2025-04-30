from tempfile import TemporaryDirectory
from magicgui import magic_factory
from pathlib import Path
import numpy as np
import tifffile
import napari
from pystack3d import Stack3d

import pystack3d_napari.utils as utils

TRANSFOS = ['TRANSLATION', 'RIGID_BODY', 'SCALED_ROTATION', 'AFFINE']


def on_init(widget):
    """
    Initializes widget layout.
    Updates widget layout according to user input.
    """
    widget.native.setStyleSheet("QWidget{font-size: 12pt;}")

    # for x in ['crop']:
    #     setattr(getattr(widget, x), 'visible', False)

    # @widget.values.changed.connect
    # def toggle_values_widgets(value):
    #     for x in ['crop']:
    #         setattr(getattr(widget, x), 'visible', value)

    widget.native.layout().addStretch()


@magic_factory(widget_init=on_init, layout='vertical', call_button="register",
               transformation={"choices": TRANSFOS}, nproc={"label": "Nbr processors"})
def pystack3d_registration(input_stack: 'napari.layers.Image',
                           transformation: str,
                           nproc: int = 1,
                           crop: bool = True) -> 'napari.layers.Image':
    """
    Takes user input and calls pystack3d' registration function in itkpystack3d.
    """
    if input_stack is None:
        return utils.error("No input stack selected for registration.")

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(r"C:\Users\PQ177701\AppData\Local\pystack3d_napari")

        # tmpdir = Path(tmpdir)
        dirname = tmpdir / "images"
        fname = tmpdir / "params.toml"
        dirname.mkdir(exist_ok=True)
        with open(fname, 'w') as fid:
            fid.write('channels = ""')

        for i, img in enumerate(input_stack.data[:]):
            tifffile.imwrite(dirname / f"img_{i:03d}.tif", img)

        stack = Stack3d(input_name=tmpdir)
        stack.pathdir = stack.last_step_dir = fname.parent
        stack.last_step_dir = fname.parent
        stack.params = {'history': [], 'ind_min': 0, 'ind_max': 9999, 'channels': ['images']}

        stack.params['registration_calculation'] = {'transformation': transformation,
                                                    'nb_blocks': (1, 1)}
        stack.eval(process_steps='registration_calculation', nproc=nproc)

        stack.params['registration_transformation'] = {'subpixel': True, 'cropping': True}
        stack.eval(process_steps='registration_transformation', nproc=nproc)

        stack.concatenate_tif(process_step='registration_transformation',
                              name_out='concatenated.tif')

        dirname_out = tmpdir / "process" / "registration_transformation" / "images"
        fname_out = dirname_out / "concatenated.tif"

        with tifffile.TiffFile(fname_out) as tif:
            arr = np.array([page.asarray() for i, page in enumerate(tif.pages)])
            print(arr.shape)

        return napari.layers.Image(arr, name=input_stack.name + " ALIGNED")


def launcher(fname=None):
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(pystack3d_registration(), area='right')
    if fname:
        viewer.open(fname)
    napari.run()


if __name__ == '__main__':
    from pathlib import Path

    dirname = Path(r"C:\Users\PQ177701\Desktop\DATA\HAADF\HAADF_Test_Images\2µs-x10M-i5pA")
    fname = dirname / "2µs-x10M-i5pA.dm4"
    launcher(fname=fname)
