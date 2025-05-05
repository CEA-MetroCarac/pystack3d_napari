from pathlib import Path
import numpy as np
import diplib as dip
import napari
from magicgui import magic_factory
from magicgui.widgets import ProgressBar
from tempfile import TemporaryDirectory
from tifffile import imwrite, TiffWriter
from qtpy.QtWidgets import QProgressBar
from qtpy.QtWidgets import QApplication

from utils import plot_and_save, find_max_inner_rectangle


def on_init(widget):
    widget.native.setStyleSheet("QWidget{font-size: 12pt;}")
    # widget.native.layout().addStretch()

    global widget_
    widget_ = widget

    widget._progress_bar = QProgressBar()
    widget._progress_bar.setValue(0)
    widget.native.layout().addWidget(widget._progress_bar)


@magic_factory(widget_init=on_init, layout='vertical', call_button="Align images")
def drift_correction(input_stack: 'napari.layers.Image') -> 'napari.layers.Image':
    global widget_
    widget = widget_

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(r"C:\Users\PQ177701\AppData\Local\pystack3d_napari")
        # tmpdir = Path(tmpdir)
        dirname = tmpdir / "images"
        dirname_out = tmpdir / "process" / "outputs"
        dirname.mkdir(exist_ok=True)
        dirname_out.mkdir(parents=True, exist_ok=True)

        for i, img in enumerate(input_stack.data):
            imwrite(dirname / f"img_{i:03d}.tif", img)

        fnames = list(dirname.glob('img_*.tif'))
        shape = input_stack.data.shape
        shape2d = (shape[1], shape[2])
        arr = np.zeros(shape)
        nslices = shape[0]

        kmax = 400

        shifts = [np.array([0, 0])]
        for k, fname in enumerate(fnames):
            img = dip.ImageRead(str(fname))
            if k > 0:
                shift = dip.FindShift(ref, img)
                shifts.append(np.array(shift))
            ref = img
            widget._progress_bar.setValue(int(100 * (k + 1) / (2 * nslices)))
            QApplication.processEvents()
            if k == kmax:
                break

        shifts = np.asarray(shifts)
        shifts_cumul = np.cumsum(shifts, axis=0)

        plot_and_save(shifts, dirname_out / "tmats.png")
        plot_and_save(shifts_cumul, dirname_out / "tmats_cumul.png")

        reg_cumul = np.ones(shape2d)
        for k, fname in enumerate(fnames):
            img = dip.ImageRead(str(fname))
            img = dip.Shift(img, -shifts_cumul[k])
            img_ref = dip.Image(np.ones(shape2d))
            reg = np.asarray(dip.Shift(img_ref, -shifts_cumul[k],
                                       interpolationMethod='linear',
                                       boundaryCondition=['add zeros']))
            reg_cumul[reg == 0] = 0
            arr[k] = np.asarray(img)
            widget._progress_bar.setValue(int(100 * (k + 1 + nslices) / (2 * nslices)))
            QApplication.processEvents()
            if k == kmax:
                break

        imin, imax, jmin, jmax = find_max_inner_rectangle(reg_cumul, value=1)
        arr_crop = arr[:, imin:imax, jmin:jmax]

        fname_out = dirname_out / "concatenated.tif"
        with TiffWriter(fname_out, bigtiff=True) as tiff_out:
            tiff_out.write(arr_crop)

        return napari.layers.Image(arr_crop, name=input_stack.name + " ALIGNED")


if __name__ == "__main__":
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(drift_correction(), area="right")
    napari.run()
