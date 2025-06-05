import re
import ast
from pathlib import Path
from tomlkit import table, document, inline_table, array
import numpy as np
from tifffile import imread


# import os
# from typing import List, Union
# from napari.layers import Image


# def error(message):
#     """
#     Shows a pop up with the given error message.
#     """
#     e = QMessageBox()
#     print("ERROR: ", message)
#     e.setText(message)
#     e.setIcon(QMessageBox.Critical)
#     e.setWindowTitle("Error")
#     e.show()
#     return e


def hsorted(list_):
    """ Sort the given list in the way that humans expect """
    list_ = [str(x) for x in list_]
    convert = lambda text: int(text) if text.isdigit() else text
    alphanum_key = lambda key: [convert(c) for c in re.split('([0-9]+)', key)]
    return sorted(list_, key=alphanum_key)


# def get_reader(path: Union[str, List[str]]):
#     # This is where we actually load the data
#     print(1, path)
#     if True:
#         if os.path.isdir(path):
#             files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.tif')]
#         else:
#             files = [f for f in path if f.endswith('.tif')]
#
#         stack = [imread(p) for p in hsorted(files)]
#         stack = np.stack(stack, axis=0)  # 3D stack
#
#         return [(stack, {"name": "Images Stack"}, "image")]
#     else:
#         return None

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


def reformat_params(params):
    doc = document()
    for section_name, section_data in params.items():
        if isinstance(section_data, dict):
            section = table()
            for key, value in section_data.items():
                if section_name == "destriping" and key == "filters":
                    inline_array = array()
                    inline_array.multiline(False)
                    for filt in value:
                        t = inline_table()
                        t.update(filt)
                        inline_array.append(t)
                    section[key] = inline_array
                else:
                    section[key] = value
            doc[section_name] = section
        else:
            doc[section_name] = section_data
    return doc


def update_widgets_params(data, init_widget, process_container):
    for key, value in data.items():
        if isinstance(value, dict):
            continue
        if hasattr(init_widget, key):
            try:
                setattr(init_widget, key, value)
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


def get_stack(dirname):
    fnames = hsorted(Path(dirname).glob("*.tif"))
    stack = [imread(fname) for fname in fnames]
    stack = np.stack(stack, axis=0)
    print("get_stack", stack.shape)
    return [(stack, {"name": dirname.name.upper()}, "image")]


def process(stack, process_name):
    stack.eval(process_steps=process_name, show_pbar=False, pbar_init=True)
