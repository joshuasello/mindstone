# -*- coding: utf-8 -*-
""" Environment mapping middleware.

TODO: Add circular and rectangular fitting of points in the environment.
TODO: Add point cluster classification

"""

from typing import Hashable

import numpy as np

from ._utils import unit_vector
from .controller import ObserverMiddlewareABC
from .plot import Plotter, PlotHandlerABC
from .pose import PoseMiddleware


class MappingMiddleware(ObserverMiddlewareABC, list, PlotHandlerABC):
    def __init__(self, pose_obj: PoseMiddleware, accuracy: int = 3):
        super().__init__()
        self.accuracy = accuracy
        self._pose = pose_obj  # note that this should be a reference to the main pose model.
        # TODO: Add automatic clustering to observed points
        self._clusters = None
        self._measurement_handlers = {
            "raycast": self.add_raycasted_measurement
        }

    def handle_observation(self, tag: Hashable, parameter: str, observed_value: float) -> None:
        self._measurement_handlers[parameter](np.ndarray(self._pose.get_arm_absolute_position(tag)),
                                              self._pose.arms[tag], observed_value)

    def add_raycasted_measurement(self, position: np.ndarray, arm: np.ndarray, distance: float) -> None:
        # ensure that the arm vector is a unit vector
        arm = np.around(unit_vector(arm), self.accuracy)
        # remove any measured points that intersect with the line of action made by the location
        # of the measuring device and the newly measured point.
        for i, measurement_position in enumerate(self):
            if (np.around(unit_vector(measurement_position - position), self.accuracy) == arm).all():
                self.pop(i)
        self.append(position + arm * distance)

    def add_to_plot(self, plot: Plotter) -> None:
        for point in self:
            plot.add_point(tuple(point))
