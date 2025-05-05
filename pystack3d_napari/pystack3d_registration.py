from magicgui import magic_factory
from qtpy.QtWidgets import QProgressBar
from qtpy.QtCore import QTimer
from multiprocessing import Process, Queue
from tempfile import TemporaryDirectory
import tifffile
import numpy as np
import napari
from pystack3d import Stack3d

TRANSFOS = ['TRANSLATION', 'RIGID_BODY', 'SCALED_ROTATION', 'AFFINE']


def process(tmpdir, queue, transfo, nproc):
    stack = Stack3d(input_name=tmpdir)
    stack.pathdir = stack.last_step_dir = stack.last_step_dir = tmpdir
    stack.params = {'history': [], 'ind_min': 0, 'ind_max': 9999, 'channels': ['images']}
    stack.queue_incr = queue

    stack.params['registration_calculation'] = {'transformation': transfo, 'nb_blocks': (1, 1)}
    stack.eval(process_steps='registration_calculation', nproc=nproc, show_pbar=False)

    stack.params['registration_transformation'] = {'subpixel': True, 'cropping': True}
    stack.eval(process_steps='registration_transformation', nproc=nproc, show_pbar=False)

    stack.concatenate_tif(process_step='registration_transformation',
                          name_out='concatenated.tif', show_pbar=False)


def on_init(widget):
    """
    Initializes widget layout.
    Updates widget layout according to user input.
    """
    global pystack3d_registration_widget
    pystack3d_registration_widget = widget

    widget.native.setStyleSheet("QWidget{font-size: 12pt;}")
    # widget.native.layout().addStretch()

    widget._progress_bar = QProgressBar()
    widget._progress_bar.setValue(0)
    widget.native.layout().addWidget(widget._progress_bar)


def on_done(fname_out, name):
    with tifffile.TiffFile(fname_out) as tif:
        arr = np.array([page.asarray() for i, page in enumerate(tif.pages)])
    layer = napari.layers.Image(arr, name=name + " ALIGNED")
    viewer = napari.current_viewer()
    viewer.add_layer(layer)


@magic_factory(widget_init=on_init, layout='vertical', call_button="register",
               transformation={"choices": TRANSFOS}, nproc={"label": "Nbr processors"})
def pystack3d_registration(input_stack: 'napari.layers.Image',
                           transformation: str,
                           nproc: int = 1) -> 'napari.layers.Image':
    """
    Takes user input and calls pystack3d' registration function in itkpystack3d.
    """
    if input_stack is None:
        return utils.error("No input stack selected for registration.")

    global pystack3d_registration_widget
    widget = pystack3d_registration_widget

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(r"C:\Users\PQ177701\AppData\Local\pystack3d_napari")

        # tmpdir = Path(tmpdir)
        dirname = tmpdir / "images"
        fname = tmpdir / "params.toml"
        dirname.mkdir(exist_ok=True)
        with open(fname, 'w') as fid:
            fid.write('channels = ""')
        dirname_out = tmpdir / "process" / "registration_transformation" / "images"
        fname_out = dirname_out / "concatenated.tif"

        for i, img in enumerate(input_stack.data):
            tifffile.imwrite(dirname / f"img_{i:03d}.tif", img)

        queue = Queue()
        count = 0
        nslices = input_stack.data.shape[0]
        overlay = 1
        ntot = nslices + (nproc - 1) * overlay  # calculation
        ntot += nslices  # transformation
        ntot += nslices  # concatenation

        def update_progress():
            nonlocal count
            if not queue.empty():
                val = queue.get_nowait()
                if val != "finished":
                    count += val
                    percent = 100 * count / ntot
                    widget._progress_bar.setValue(int(percent))
                if count == ntot:
                    timer.stop()
                    on_done(fname_out, input_stack.name)

        timer = QTimer()
        timer.timeout.connect(update_progress)
        timer.start(200)

        Process(target=process, args=(tmpdir, queue, transformation, nproc)).start()


def launcher(fname=None):
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(pystack3d_registration(), area='right')
    if fname:
        viewer.open(fname)
    napari.run()


if __name__ == '__main__':
    from pathlib import Path

    dirname = Path(r"C:\Users\PQ177701\Desktop\DATA\HAADF\HAADF_Test_Images\2µs-x10M-i5pA\test")
    fname = dirname / "2µs-x10M-i5pA.dm4"
    launcher(fname=None)
