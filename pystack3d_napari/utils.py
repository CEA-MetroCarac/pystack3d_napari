import re
import shutil
import ast
import time
import queue
import numpy as np
from tifffile import imread
import psutil
import dask.array as da
import dask


def hsorted(list_):
    """ Sort the given list in the way that humans expect """
    list_ = [str(x) for x in list_]
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(list_, key=alphanum_key)


def convert_params(kwargs):
    params = {}
    for arg, value in kwargs.items():
        if isinstance(value, str):
            if value == '':
                value = None
            elif '[' in value or '(' in value:
                value = ast.literal_eval(value)
            else:
                try:
                    value = float(value)
                except:
                    pass
        params[arg] = value
    return params


def update_widgets_params(data, init_widget, process_container):
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        if hasattr(init_widget, key):
            try:
                getattr(init_widget, key).value = value
            except Exception as e:
                print(f"[init_widget] Error with '{key}': {e}")
        if key == 'process_steps':
            process_container.reorder_widgets(value)

    # update 'process'_widget parameters
    for section in process_container.widgets():
        section_name = section.process_name
        widget = section.widget
        if section_name in data:
            section_data = data[section_name]
            for key, value in section_data.items():
                try:
                    attr = getattr(widget, key)
                    attr.value = value
                    if key == "filters" and hasattr(widget, "_filters_widget"):
                        widget._filters_widget.set_filters(value)
                except Exception as e:
                    print(f"[{section_name}] Error with '{key}': {e}")


def get_params(widget, keep_null_string=True):
    params = {}
    for name in widget._function.__annotations__:
        if hasattr(widget, name):
            value = getattr(widget, name).value
            try:
                value = ast.literal_eval(value)
            except:
                pass
            if keep_null_string or value != "":
                params.update({name: value})
    return params


def get_layers(dirname, channels, ind_min=0, ind_max=99999, is_init=False):
    layers = []
    for channel in channels:
        channel_dir = dirname / channel
        fnames = hsorted(channel_dir.glob("*.tif"))[ind_min:ind_max + 1]
        name_process = dirname.name.upper() + (len(channels) > 1) * f" ({channel})"
        if len(fnames) > 0:
            img0 = imread(fnames[0])
            lazy_arrays = [da.from_delayed(dask.delayed(imread)(str(fname)),
                                           shape=img0.shape, dtype=img0.dtype) for fname in fnames]
            stack = da.stack(lazy_arrays, axis=0)
            name = channel_dir.name if is_init else name_process
            layers.append(((stack, {"name": name}, "image")))

    return layers


def update_progress(nchannels, nproc, queue_incr, pbar_signal):
    count = 0
    finished = 0
    ntot = None  # set by the 1rst emit via queue_incr in stack.eval()
    channel = 1
    while True:
        try:
            val = queue_incr.get_nowait()
            if val == "finished":
                finished += 1
            else:
                if ntot:
                    count += val
                    pbar_signal.emit(int(100 * count / (nchannels * ntot)))
                else:
                    ntot = val
            if finished == nproc:
                channel += 1
                if channel <= nchannels:
                    finished = 0
                    ntot = None  # continue with the next channel
                else:
                    break
        except queue.Empty:
            time.sleep(0.01)


def get_disk_info():
    usage = shutil.disk_usage(".")
    return usage.total, usage.used, usage.free


def get_ram_info():
    mem = psutil.virtual_memory()
    return mem.total, mem.used, mem.available
