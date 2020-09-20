# -*- coding: utf-8 -*-
""" mindstone.

The main aim of this project is to create a generalized toolset for creating, testing, and deploying agents that control
robots or any other automated system.

TODO: Add logging for worker and controller
TODO: Add authentication to controller-worker communication.
TODO: Improve error handling mechanism.
"""

__version__ = "0.1"
__author__ = "Joshua Sello"

# import controllers
from .gatenetwork import Gate, GateNetwork
# import middleware
from .mapping import MappingMiddleware
# import front-end utilities
from .plot import Plotter
from .pose import PoseMiddleware
# import worker
from .worker import Worker
