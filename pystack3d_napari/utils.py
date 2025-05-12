from pathlib import Path
import numpy as np
import tifffile
import dm3_lib as dm3
from collections import namedtuple
import matplotlib.pyplot as plt

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
    if isinstance(path, str):
        if path.endswith(('.tif', '.tiff')):
            return read_tif
        elif path.endswith(('.dm3', '.dm4')):
            return read_dm
    return None


def read_tif(path):
    with tifffile.TiffFile(path) as tif:
        arr = np.array([page.asarray() for i, page in enumerate(tif.pages)])
        return [(arr.astype(np.float32), {"name": Path(path).name})]


def read_dm(path):
    arr = dm3.DM3(path).imagedata
    return [(arr.astype(np.float32), {"name": Path(path).name})]


def plot_and_save(shifts, fname):
    fig, ax = plt.subplots()
    ax.plot(shifts[:, 0], label="transl_x")
    ax.plot(shifts[:, 1], label="transl_y")
    ax.set_xlabel('# Frames')
    ax.legend()
    plt.savefig(fname)
    np.save(fname.with_suffix(".npy"), shifts)
