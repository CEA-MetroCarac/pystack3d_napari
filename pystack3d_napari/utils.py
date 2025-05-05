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


def find_max_inner_rectangle(arr, value=0):
    """
    Returns coordinates of the largest rectangle containing the 'value'.
    From : https://stackoverflow.com/questions/2478447

    Parameters
    ----------
    arr: numpy.ndarray((m, n), dtype=int)
        2D array to work with
    value: int, optional
        Reference value associated to the area of the largest rectangle

    Returns
    -------
    imin, imax, jmin, jmax: ints
        indices associated to the largest rectangle
    """
    Info = namedtuple('Info', 'start height')

    def rect_max_size(histogram):
        stack = []
        top = lambda: stack[-1]
        max_size = (0, 0, 0)  # height, width and start position of the max rect
        pos = 0  # current position in the histogram
        for pos, height in enumerate(histogram):
            start = pos  # position where rectangle starts
            while True:
                if not stack or height > top().height:
                    stack.append(Info(start, height))  # push
                elif stack and height < top().height:
                    tmp = (top().height, pos - top().start, top().start)
                    max_size = max(max_size, tmp, key=area)
                    start, _ = stack.pop()
                    continue
                break  # height == top().height goes here

        pos += 1
        for start, height in stack:
            max_size = max(max_size, (height, (pos - start), start), key=area)

        return max_size

    def area(size):
        return size[0] * size[1]

    iterator = iter(arr)
    hist = [(el == value) for el in next(iterator, [])]
    max_rect = rect_max_size(hist) + (0,)
    for irow, row in enumerate(iterator):
        hist = [(1 + h) if el == value else 0 for h, el in zip(hist, row)]
        max_rect = max(max_rect, rect_max_size(hist) + (irow + 1,), key=area)

    imax = int(max_rect[3] + 1)
    imin = int(imax - max_rect[0])
    jmin = int(max_rect[2])
    jmax = int(jmin + max_rect[1])

    return imin, imax, jmin, jmax
