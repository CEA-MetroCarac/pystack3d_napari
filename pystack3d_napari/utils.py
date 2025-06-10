import re
import ast
import time
from pathlib import Path
import numpy as np
from tifffile import imread


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


def get_stacks(dirname, channels):
    images = []
    for channel in channels:
        fnames = hsorted((dirname / channel).glob("*.tif"))
        if len(fnames) > 0:
            stack = [imread(fname) for fname in fnames]
            stack = np.stack(stack, axis=0)
            name = dirname.name.upper() + (len(channels) > 1) * f" ({channel})"
            images.append([(stack, {"name": name}, "image")])
    return images


def update_progress(queue_incr, pbar_signal, finish_signal):
    count = 0
    ntot = None
    while True:
        if not queue_incr.empty():
            val = queue_incr.get_nowait()
            if val != "finished":
                if ntot:
                    count += val
                    pbar_signal.emit(int(100 * count / ntot))
                else:
                    ntot = val
            if count == ntot:
                finish_signal.emit()
                break
