from pathlib import Path
import numpy as np
import tifffile

from qtpy.QtWidgets import QMessageBox


def error(message):
    """
    Shows a pop up with the given error message.
    """
    e = QMessageBox()
    print("ERROR: ", message)
    e.setText(message)
    e.setIcon(QMessageBox.Critical)
    e.setWindowTitle("Error")
    e.show()
    return e


def get_reader(path):
    if isinstance(path, str) and path.endswith(('.tif', '.tiff')):
        return read_tif
    return None


def read_tif(path):
    with tifffile.TiffFile(path) as tif:
        arr = np.array([page.asarray() for i, page in enumerate(tif.pages)])
        return [(arr.astype(np.float32), {"name": Path(path).name})]
