# -*- coding: utf-8 -*-
""" Plotting.

"""

import math
import tkinter as tk
import uuid
from abc import ABC, abstractmethod
from typing import Hashable, Iterable, Tuple

from . import _graph
from ._utils import intersect_update

_default_point_settings = {
    "fill": "",
    "radius": 1,
    "show_tag": False
}

_default_edge_settings = {
    "fill": "",
}


class _PointNode(set):
    def __init__(self, coordinates: Tuple[float, float, float], settings: dict = None):
        super().__init__()
        # add the point x, y, z coordinates
        self.coordinates: Tuple[float, float, float] = coordinates
        # add settings. if any invalid settings are provided, discard them.
        self.settings = intersect_update(_default_point_settings, {} if settings is None else settings)


class Plotter(dict):
    def __init__(self, canvas_size: Tuple[int, int] = (600, 500),
                 space_size: Tuple[int, int, int] = (200, 200, 200), show_axes: bool = True,
                 show_floor_grid: bool = True, viewing_angle: float = math.pi / 6, viewing_scale: float = 1):
        super().__init__()
        self.viewing_angle = viewing_angle
        self.viewing_scale = viewing_scale
        self._canvas_width, self._canvas_height = canvas_size
        self._space_size = space_size
        self._edge_settings = {}
        self._show_axis = show_axes
        self._show_floor_grid = show_floor_grid

    @staticmethod
    def _generate_unique_tag() -> Hashable:
        return str(uuid.uuid1())

    def add_point(self, coordinates: Tuple[float, float, float], tag: Hashable = None, **settings) -> None:
        tag = self._generate_unique_tag() if tag is None else tag
        # add the point node
        _graph.add_node(self, tag, container=_PointNode(coordinates, settings))

    def remove_point(self, tag: Hashable) -> None:
        _graph.remove_node(self, tag)

    def add_edge(self, from_tag: Hashable, to_tag: Hashable, **settings) -> None:
        _graph.add_edge(self, from_tag, to_tag)
        # add settings. if any invalid settings are provided, discard them.
        self._edge_settings[(from_tag, to_tag)] = intersect_update(_default_edge_settings, settings)

    def remove_edge(self, from_tag: Hashable, to_tag: Hashable) -> None:
        _graph.remove_edge(self, from_tag, to_tag)

    def plot(self, caption: str = "Plot") -> None:
        # setup window
        root = tk.Tk()
        root.title(caption)
        # setup canvas
        canvas = tk.Canvas(
            root,
            width=self._canvas_width,
            height=self._canvas_height,
            borderwidth=0,
            highlightthickness=0,
            bg="black"
        )
        canvas.pack()

        space_x_span, space_y_span, space_z_span = self._space_size
        step_size = 10

        # display flow grid
        if self._show_floor_grid:
            grid_color = "#222"
            for y in range(0, space_y_span, step_size):
                self._display_line(canvas, (0, y, 0), (space_x_span, y, 0), fill=grid_color)
            # display the line crossing the x-axis
            for x in range(0, space_x_span, step_size):
                self._display_line(canvas, (x, 0, 0), (x, space_y_span, 0), fill=grid_color)
        # display axes
        if self._show_axis:
            axes_line_color = "#fff"
            self._display_line(canvas, (0, space_x_span, 0), (space_x_span, space_x_span, 0), fill=axes_line_color)
            self._display_line(canvas, (space_x_span, 0, 0), (space_x_span, space_y_span, 0), fill=axes_line_color)
            self._display_line(canvas, (space_x_span, 0, 0), (space_x_span, 0, space_z_span), fill=axes_line_color)
            font = "Purisa", 6
            text_color = "#ccc"
            # show axes values
            for x in range(0, space_x_span, step_size * 2):
                projected_x, projected_y = self._get_canvas_placement((x + 5, space_x_span + 5, -10))
                canvas.create_text(projected_x, projected_y, text=str(x), font=font, fill=text_color)
            for y in range(0, space_y_span, step_size * 2):
                projected_x, projected_y = self._get_canvas_placement((space_x_span + 5, y + 5, -10))
                canvas.create_text(projected_x, projected_y, text=str(y), font=font, fill=text_color)
            for z in range(0, space_z_span, step_size * 2):
                projected_x, projected_y = self._get_canvas_placement((space_x_span + 10, 0, z))
                canvas.create_text(projected_x, projected_y, text=str(z), font=font, fill=text_color)
        # display points
        for tag, node in self.items():
            node: _PointNode
            self._display_point(canvas, node.coordinates, tag, **node.settings)
        # display edges
        for edge in _graph.get_edges(self):
            from_tag, to_tag = edge
            self._display_line(
                canvas, self[from_tag].coordinates, self[to_tag].coordinates, **self._edge_settings[tuple(edge)])

        root.mainloop()

    def _get_canvas_placement(self, coordinate: Tuple[float, float, float]) -> Tuple[float, float]:
        # scale and project the point
        projected_x, projected_y = project_point(scale_point(self.viewing_scale, coordinate), self.viewing_angle)
        # center the point on the canvas
        return self._canvas_width // 2 + projected_x, self._canvas_height // 2 - projected_y

    def _display_point(self, canvas: tk.Canvas, coordinates: Tuple[float, float, float], tag: str = None,
                       **settings) -> None:
        projected_x, projected_y = self._get_canvas_placement(coordinates)

        radius = settings["radius"]
        fill = settings["fill"]
        show_tag = settings["show_tag"]

        canvas.create_oval(projected_x - radius, projected_y - radius, projected_x + radius, projected_y + radius,
                           fill=fill)
        if show_tag and tag is not None:
            canvas.create_text(projected_x + radius + 2, projected_y + radius + 2, text=tag, fill=fill)

    def _display_line(self, canvas: tk.Canvas, start: Tuple[float, float, float], end: Tuple[float, float, float],
                      **settings) -> None:
        start_projected_x, start_projected_y = self._get_canvas_placement(start)
        end_projected_x, end_projected_y = self._get_canvas_placement(end)

        fill = settings.get("fill", "")

        canvas.create_line(start_projected_x, start_projected_y, end_projected_x, end_projected_y, fill=fill)


class PlotHandlerABC(ABC):
    @abstractmethod
    def add_to_plot(self, plot: Plotter) -> None:
        pass


def project_point(coordinate: Tuple[float, float, float], perspective_angle: float) -> Tuple[float, float]:
    x, y, z = coordinate
    return (y - x) * math.cos(perspective_angle), (z - math.sin(perspective_angle) * (x + y))


def scale_point(scalar: float, args: Iterable[float]) -> tuple:
    return tuple([c * scalar for c in args])
