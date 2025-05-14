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
def drift_correction(input_stack: 'napari.layers.Image',
                     index_min: int = 10,
                     index_max: int = 20,
                     save_tmat: bool = True) -> 'napari.layers.Image':
    global widget_
    widget = widget_

    pathname = Path(input_stack.source.path)
    dirname = pathname.parent

    with TemporaryDirectory() as tmpdir:
        tmpdir = Path(r"C:\Users\PQ177701\AppData\Local\pystack3d_napari")
        # tmpdir = Path(tmpdir)
        dirname_img = tmpdir / "images"
        dirname_img.mkdir(exist_ok=True)
        # dirname_out = tmpdir / "process" / "outputs"
        # dirname_out.mkdir(parents=True, exist_ok=True)

        for i, img in enumerate(input_stack.data):
            imwrite(dirname_img / f"img_{i:03d}.tif", img)

        fnames = list(dirname_img.glob('img_*.tif'))[index_min:index_max + 1]
        nslices = len(fnames)
        shape = img.shape
        arr = np.zeros((nslices, shape[0], shape[1]))

        shifts = []
        for k, fname in enumerate(fnames):
            img = dip.ImageRead(str(fname))

            if k > 0:

                # shift calculation
                shift = np.asarray(dip.FindShift(ref, img))
                shift_cumul += shift

                # cumulative shift application
                img_reg = dip.Shift(img, -shift_cumul, interpolationMethod='linear')
                arr[k] = np.asarray(img_reg)

            else:

                shift = np.array([0., 0.])
                shift_cumul = np.array([0., 0.])
                arr[0] = np.asarray(img)

            ref = img
            shifts.append(shift)
            widget._progress_bar.setValue(int(100 * (k + 1) / nslices))
            QApplication.processEvents()

        shifts = np.asarray(shifts)
        shifts_cumul = np.cumsum(shifts, axis=0)

        dx, dy = shifts_cumul[:, 0], shifts_cumul[:, 1]
        imin = max(0, -int(np.ceil(dy.min())))
        imax = min(shape[0], shape[0] - int(np.floor(dy.max())))
        jmin = max(0, -int(np.ceil(dx.min())))
        jmax = min(shape[1], shape[1] - int(np.floor(dx.max())))

        arr_crop = arr[:, imin:imax, jmin:jmax]

        if save_tmat:
            plot(shifts, dirname / "tmats.png")
            plot(shifts_cumul, dirname / "tmats_cumul.png")
            np.savetxt(dirname / "tmats.txt", shifts)
            np.savetxt(dirname / "tmats_cumul.txt", shifts_cumul)

        # with TiffWriter(dirname / (pathname.stem + "_ALIGNED.tif"), bigtiff=True) as tiff_out:
        #     tiff_out.write(arr_crop)

        return napari.layers.Image(arr_crop, name=input_stack.name + " ALIGNED")


def launch():
    viewer = napari.Viewer()
    viewer.window.add_dock_widget(drift_correction(), area="right")
    napari.run()


if __name__ == "__main__":
    launch()
