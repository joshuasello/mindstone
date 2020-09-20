# -*- coding: utf-8 -*-
""" Pose middleware.

"""

import json
import math
from collections.abc import Hashable
from typing import Dict, Tuple, Iterable

import numpy as np

from . import _graph
from ._utils import get_x_rotation_matrix, get_z_rotation_matrix, get_y_rotation_matrix, unit_vector
from .controller import ObserverMiddlewareABC
from .plot import Plotter, PlotHandlerABC


class PoseMiddleware(ObserverMiddlewareABC, dict, PlotHandlerABC):
    def __init__(self, arm_details: Dict[Hashable, Tuple[float, float, float]] = None,
                 joints: Iterable[Tuple[str, str]] = None, in_degrees: bool = True,
                 reference_position: Iterable[float] = (0, 0, 0),
                 reference_orientation_angles: Tuple[float, float, float] = (0, 0, 0)):
        super().__init__()
        self.arms: Dict[Hashable, np.ndarray] = {}
        self.reference_orientation_angles: Tuple[float, float, float] = reference_orientation_angles
        self.reference_position = np.array(reference_position)
        self._in_degrees = in_degrees
        if arm_details:
            self.add_arms_from_dict(arm_details)
        if joints:
            self.add_joints_from_iterable(joints)

    @property
    def orientation(self) -> np.ndarray:
        x_angle, y_angle, z_angle = self.reference_orientation_angles
        return get_x_rotation_matrix(x_angle) * get_y_rotation_matrix(y_angle) * get_z_rotation_matrix(z_angle)

    def setup_from_json_file(self, file_path: str) -> None:
        with open(file_path, "r") as file:
            saved_data: dict = json.load(file)
        field_handlers = {
            "arms": self.add_arms_from_dict,
            "joints": self.add_joints_from_iterable
        }
        for field, handler in field_handlers.items():
            if field in saved_data:
                handler(saved_data[field])

    def handle_observation(self, tag: Hashable, parameter: str, observed_value: float) -> None:
        value = math.radians(observed_value) if parameter in _angle_parameters and self._in_degrees else observed_value
        _arm_setters[parameter](self.arms[tag], value)

    def add_arm(self, tag: Hashable, x: float, y: float, z: float) -> None:
        if x == y == z == 0:
            raise ValueError("All arm components can't be 0")
        _graph.add_node(self, tag)
        self.arms[tag] = np.array([x, y, z])

    def remove_arm(self, tag: Hashable) -> None:
        _graph.remove_node(self, tag)
        if tag in self.arms:
            del self.arms[tag]

    def add_arms_from_dict(self, arm_details: Dict[Hashable, Tuple[float, float, float]]) -> None:
        for tag, coordinates in arm_details.items():
            x, y, z = coordinates
            self.add_arm(tag, x, y, z)

    def get_arm_state(self, tag: Hashable, state_type: str) -> float:
        return _arm_getters[state_type](self.arms[tag])

    def join_arms(self, from_tag: Hashable, to_tag: Hashable) -> None:
        _graph.add_edge(self, from_tag, to_tag)
        if not _graph.is_acyclic(self):
            raise RuntimeError("The joint '{}' to '{}' creates a cycle in the body's model.".format(from_tag, to_tag))

    def add_joints_from_iterable(self, joints: Iterable[Tuple[str, str]]) -> None:
        for from_tag, to_tag in joints:
            self.join_arms(from_tag, to_tag)

    def remove_joint(self, from_tag: Hashable, to_tag: Hashable) -> None:
        _graph.remove_edge(self, from_tag, to_tag)

    def set_reference_position(self, x: float, y: float, z: float) -> None:
        self.reference_position = np.array([x, y, z])

    def set_orientation_angles(self, x_angle: float = None, y_angle: float = None, z_angle: float = None) -> None:
        current_x_angle, current_y_angle, current_z_angle = self.reference_orientation_angles
        self.reference_position = \
            current_x_angle if x_angle is None else x_angle, \
            current_y_angle if y_angle is None else y_angle, \
            current_z_angle if z_angle is None else z_angle

    def get_arm_absolute_position(self, tag: Hashable) -> Tuple[float, float, float]:
        return tuple(self.orientation.dot(self._get_arm_absolute_position_util(tag, self.reference_position.copy())))

    def get_all_arm_absolute_positions(self) -> Dict[Hashable, Tuple[float, float, float]]:
        return {tag: self.get_arm_absolute_position(tag) for tag in self.keys()}

    def add_to_plot(self, plot: Plotter) -> None:
        fig_fill = "#0F0"
        ref_tag = "REF."
        points = self.get_all_arm_absolute_positions()
        points[ref_tag] = tuple(self.orientation.dot(self.reference_position))
        source = _graph.get_sources(self).pop()  # there should only be one source for this graph
        edges = _graph.get_edges(self) + [(ref_tag, source)]
        for tag, point in points.items():
            plot.add_point(point, tag, show_tag=True, fill=fig_fill)
        for from_tag, to_tag in edges:
            plot.add_edge(from_tag, to_tag, fill=fig_fill)

    def _get_arm_absolute_position_util(self, tag: Hashable, reference: np.ndarray) -> np.ndarray:
        parents = _graph.get_in_neighbors(self, tag)
        abs_position = self.arms[tag].copy() + reference
        if not parents:
            return abs_position
        return self._get_arm_absolute_position_util(parents.pop(), abs_position)


def cartesian_to_spherical(x: float, y: float, z: float) -> tuple:
    if x == y == z == 0:
        return 0, 0, 0
    radius = math.sqrt(x ** 2 + y ** 2 + z ** 2)
    azimuthal = math.atan(y / x)
    # had to round to mitigate domain errors e.g. 1.00000000002
    polar = math.acos(round(z / radius, 5))
    return radius, polar, azimuthal


def spherical_to_cartesian(radius: float, polar: float, azimuthal: float) -> tuple:
    return radius * math.sin(polar) * math.cos(azimuthal), radius * math.sin(polar) * math.sin(azimuthal), \
           radius * math.cos(polar)


def _set_arm_yaw(v: np.ndarray, angle: float) -> None:
    r, yaw, pitch = cartesian_to_spherical(*v)
    v.put([0, 1, 2], spherical_to_cartesian(r, angle, pitch))


def _set_arm_pitch(v: np.ndarray, angle: float) -> None:
    r, yaw, pitch = cartesian_to_spherical(*v)
    v.put([0, 1, 2], spherical_to_cartesian(r, yaw, angle))


def _set_arm_length(v: np.ndarray, length: float) -> None:
    v.put([0, 1, 2], unit_vector(v) * length)


_arm_setters = {
    "pos_x": lambda v, value: v.__setitem__(0, value),
    "pos_y": lambda v, value: v.__setitem__(1, value),
    "pos_z": lambda v, value: v.__setitem__(2, value),
    "yaw": _set_arm_yaw,
    "pitch": _set_arm_pitch,
    "len": lambda v, value: v.put([0, 1, 2], unit_vector(v) * value)
}

_arm_getters = {
    "pos_x": lambda v: v[0],
    "pos_y": lambda v: v[1],
    "pos_z": lambda v: v[2],
    "yaw": lambda v: cartesian_to_spherical(*v)[1],  # TODO: Check that this angle produce real results
    "pitch": lambda v: cartesian_to_spherical(*v)[2],  # TODO: Check that this angle produce real results
    "len": np.linalg.norm
}

_angle_parameters = {"yaw", "pitch"}

# make sure that every arm getter has a setter
assert _arm_setters.keys() == _arm_getters.keys(), "Arm setters don't match arm getters."
