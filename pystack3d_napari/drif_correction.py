import sys
from pathlib import Path
import time
import numpy as np
import diplib as dip
import napari
from magicgui import magic_factory
from magicgui.widgets import ProgressBar
from tempfile import TemporaryDirectory
from tifffile import imwrite, TiffWriter
from qtpy.QtWidgets import QProgressBar
from qtpy.QtWidgets import QApplication

from utils import plot


def on_init(widget):
    widget.native.setStyleSheet("QWidget{font-size: 12pt;}")
    # widget.native.layout().addStretch()

    global widget_
    widget_ = widget

    widget._progress_bar = QProgressBar()
    widget._progress_bar.setValue(0)
    widget.native.layout().addWidget(widget._progress_bar)


@magic_factory(widget_init=on_init, layout='vertical',
               save_tmat={"widget_type": "CheckBox", "label": "plot and save shifts"},
               call_button="ALIGN FRAMES")
def napari_widget(input_stack: 'napari.layers.Image',
                  index_min: int = 10,
                  index_max: int = 20,
                  save_tmat: bool = True) -> 'napari.layers.Image':
    global widget_
    widget = widget_

    dirname = Path(input_stack.source.path).parent if save_tmat else None

    def pbar_update(k, nframes):
        widget._progress_bar.setValue(int(100 * (k + 1) / nframes))
        QApplication.processEvents()

    arr_aligned = process(input_stack.data,
                          ind_min=index_min, ind_max=index_max, pbar_update=pbar_update,
                          dirname=dirname)

    return napari.layers.Image(arr_aligned, name=input_stack.name + " ALIGNED")


def process(arr,
            ind_min=0, ind_max=9999, pbar_update=None,
            dirname=None, fname_aligned=None):
    """
    Drift correction processing

    Parameters
    ----------
    arr: numpy.ndarray((nframes, ny, nx))
        Image stack
    ind_min: int, optional
        Index related to the first frame to handle
    ind_max: int, optional
        Index related to the last frame to handle
    pbar_update: fun, optional
        Progress bar updating function with arguments the current index and
        the total number of frames to process ('nframes')
    dirname: str, optional
        Dirname where to save the shifts values (.txt) and the related plot
    fname_aligned: str, optional
        Pathname for saving the aligned stack (.tif)

    Returns
    -------
    arr_aligned: numpy.ndarray((nframes, my, mx))
        The aligned and cropped image stack. (The cropping area is related to the 'valid' one)
    """
    assert arr.ndim == 3

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(r"C:\Users\PQ177701\AppData\Local\pystack3d_napari")
        # tmpdir = Path(tmpdir)
        dirname_img = tmpdir / "images"
        dirname_img.mkdir(exist_ok=True)

        for i, img in enumerate(arr):
            imwrite(dirname_img / f"img_{i:03d}.tif", img)

        fnames = list(dirname_img.glob('img_*.tif'))[ind_min:ind_max + 1]
        nframes = len(fnames)
        shape = img.shape
        arr_aligned = np.zeros((nframes, shape[0], shape[1]))

        shifts = []
        for k, fname in enumerate(fnames):
            img = dip.ImageRead(str(fname))

            if k > 0:

                # shift calculation
                shift = np.asarray(dip.FindShift(ref, img))
                shift_cumul += shift

                # cumulative shift application
                img_reg = dip.Shift(img, -shift_cumul, interpolationMethod='linear')
                arr_aligned[k] = np.asarray(img_reg)

            else:

                shift = np.array([0., 0.])
                shift_cumul = np.array([0., 0.])
                arr_aligned[0] = np.asarray(img)

            ref = img
            shifts.append(shift)
            pbar_stdout_update(k, nframes)
            if pbar_update:
                pbar_update(k, nframes)

        shifts = np.asarray(shifts)
        shifts_cumul = np.cumsum(shifts, axis=0)

        # 'valid' area determination
        dx, dy = shifts_cumul[:, 0], shifts_cumul[:, 1]
        imin = max(0, -int(np.ceil(dy.min())))
        imax = min(shape[0], shape[0] - int(np.floor(dy.max())))
        jmin = max(0, -int(np.ceil(dx.min())))
        jmax = min(shape[1], shape[1] - int(np.floor(dx.max())))

        arr_aligned = arr_aligned[:, imin:imax, jmin:jmax]

        if dirname:
            plot(shifts, dirname / "tmats.png")
            plot(shifts_cumul, dirname / "tmats_cumul.png")
            np.savetxt(dirname / "tmats.txt", shifts)
            np.savetxt(dirname / "tmats_cumul.txt", shifts_cumul)

        if fname_aligned:
            with TiffWriter(fname_aligned, bigtiff=True) as tiff_out:
                tiff_out.write(arr_aligned)

        return arr_aligned


def pbar_stdout_update(k, nframes):
    global t0
    if k == 0:
        t0 = time.time()

    pbar = "\r[{:50}] {:.0f}% {:.0f}/{} {:.2f}s"
    percent = 100 * (k + 1) / nframes
    cursor = "*" * int(percent / 2)
    exec_time = time.time() - t0
    sys.stdout.write(pbar.format(cursor, percent, k + 1, nframes, exec_time))
    if k == nframes:
        print()


def launch():
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(napari_widget(), area="right")
    napari.run()


if __name__ == "__main__":
    # launch()

    from utils import read_dm

    dirname = Path(r"C:\Users\PQ177701\Desktop\DATA\HAADF\HAADF_Test_Images\2µs-x10M-i5pA")
    fname = dirname / "2µs-x10M-i5pA.dm4"
    arr = read_dm(fname)[0][0]
    process(arr, ind_min=10, ind_max=20,
            dirname=dirname, fname_aligned=dirname / "test.tif")
