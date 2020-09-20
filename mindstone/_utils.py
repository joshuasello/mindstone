# -*- coding: utf-8 -*-
""" Utils module.
The utilities module holds frequently used coding patterns (in the form of functions or classes)
that can be used by other modules in the package.

Module Structure:
~~~~~~~~~~~~~~~~~
1. Callable utils
2. Dictionary utils
3. Math utils

"""

import inspect
import math
import time
from typing import Callable, Hashable

import numpy as np


class TerminalColors:
    """ Terminal Colors class.

        Source:
            - https://svn.blender.org/svnroot/bf-blender/trunk/blender/build_files/scons/tools/bcolors.py

        Example:
            print(bcolors.WARNING + "Warning: No active frommets remain. Continue?" + bcolors.ENDC)
            print(f"{bcolors.WARNING}Warning: No active frommets remain. Continue?{bcolors.ENDC}")

    """
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

    def disable(self):
        self.HEADER = ''
        self.OKBLUE = ''
        self.OKGREEN = ''
        self.WARNING = ''
        self.FAIL = ''
        self.ENDC = ''


# Callable utils
# ~~~~~~~~~~~~~~
def get_args(func: Callable) -> set:
    """ Get the arguments for a function.

    :param func: Function under inspection.
    :return: Set of arguments.
    """
    return set(inspect.getfullargspec(func)[0])


def get_required_args(func: Callable) -> set:
    """ Get the required (non-default) arguments for a function.

    source: https://stackoverflow.com/questions/196960/can-you-list-the-keyword-arguments-a-function-receives

    :param func: Function under inspection.
    :return: Set of required arguments.
    """
    args, varargs, varkw, defaults, kwonlyargs, kwonlydefaults, annotations = inspect.getfullargspec(func)
    return set(args[:-len(defaults)] if defaults else args)  # *args and **kwargs are not required, so ignore them.


def time_function(function):
    """ A decorator that will print out how long a function took to execute.

    :param function: Function to time.
    :return: Whatever the function returns.
    """

    def timed(*args, **kwargs):
        ts = time.perf_counter()
        result = function(*args, **kwargs)
        te = time.perf_counter()
        if 'log_time' in kwargs:
            name = kwargs.get('log_name', function.__name__.upper())
            kwargs['log_time'][name] = int((te - ts) * 1000)
        else:
            print('%r  %2.2f ms' % (function.__name__, (te - ts) * 1000))
        return result

    return timed


# Dictionary utils
# ~~~~~~~~~~~~~~~~
def intersect_update(a: dict, b: dict) -> dict:
    """ Returns a new dictionary with all items in a dictionary a updated by their corresponding values in dictionary b.
        If an item in a does not have a corresponding value in dictionary b, add the item to the new dictionary without
        updating it.
    """
    return {k: default if k not in b else b[k] for k, default in a.items()}


def inner_merge(to_update: dict, key: Hashable, mapping: dict) -> dict:
    """ Update a item of a dictionary that is also a dictionary. If this item to update is not a dictionary or doesn't
    exist, it is replaced with the updating dictionary.

    :param to_update: The container dictionary.
    :param key: Key of the updatable item.
    :param mapping: The value to update the item with.
    :return: mapping
    """
    if isinstance(to_update.get(key, None), dict):
        to_update[key].update(mapping)
    else:
        to_update[key] = mapping
    return to_update


def get_nested(keys: str, mapping: dict, delimiter: str = "."):
    """ Gets a nested item value from a dictionary that can be located by a string of keys separated by some other
    string (delimiter).

    If the item can't be found, a None value is returned.

    :param keys: String of keys separated by a delimiter
    :param mapping: Dictionary to be searched.
    :param delimiter: Delimiter separating the keys.
    :return: The value of the item identified or None, if the value can't be found.
    """
    return _get_nested_util(keys.split(delimiter), mapping)


def _get_nested_util(route: list, mapping: dict = None):
    key = route.pop(0)
    if mapping is None or key not in mapping:
        return None
    mapping = mapping[key]
    return mapping if not len(route) else _get_nested_util(route, mapping)


# Mathematics utils
# ~~~~~~~~~~~~~~~~~
def unit_vector(v: np.ndarray) -> np.ndarray:
    """ Gets the unit vector of a numpy defined vector. """
    return v / np.linalg.norm(v)


def get_x_rotation_matrix(angle_in_radians: float) -> np.ndarray:
    """ Gets the rotation matrix about the x-axis in the form of a numpy defined matrix. """
    return np.array([
        [1, 0, 0],
        [0, math.cos(angle_in_radians), - math.sin(angle_in_radians)],
        [0, math.sin(angle_in_radians), math.cos(angle_in_radians)]
    ])


def get_y_rotation_matrix(angle_in_radians: float) -> np.ndarray:
    """ Gets the rotation matrix about the y-axis in the form of a numpy defined matrix. """
    return np.array([
        [math.cos(angle_in_radians), 0, math.sin(angle_in_radians)],
        [0, 1, 0],
        [-math.sin(angle_in_radians), 0, math.cos(angle_in_radians)]
    ])


def get_z_rotation_matrix(angle_in_radians: float) -> np.ndarray:
    """ Gets the rotation matrix about the z-axis in the form of a numpy defined matrix. """
    return np.array([
        [math.cos(angle_in_radians), -math.sin(angle_in_radians), 0],
        [math.sin(angle_in_radians), math.cos(angle_in_radians), 0],
        [0, 0, 1]
    ])
