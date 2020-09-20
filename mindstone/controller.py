# -*- coding: utf-8 -*-
""" Controller definition.

Module Structure:
~~~~~~~~~~~~~~~~~
1. Middleware
2. Controller
3. Ensemble controller

"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, List, Union, Iterable, Hashable, Callable

from ._utils import get_nested
from .connection import client_types, ClientABC, Response, WorkerABC
from .worker import get_available_platforms, get_available_platform_components, \
    get_available_platform_component_required_setup_args
from .plot import Plotter, PlotHandlerABC


# Middleware
# ~~~~~~~~~~
class MiddlewareABC(ABC):
    """ Middleware class.

    Every time a new response is received by the controller, middleware are used to process a response before it is
    handled by the controller.
    """

    @abstractmethod
    def handle(self, response: Response) -> None:
        """ Handle (process) a given response.

        :param response: Reference to a response that should be handled by this middleware instance.
        :return: None.
        """
        pass


class ObserverMiddlewareABC(MiddlewareABC):
    def __init__(self):
        self._observables: Dict[Hashable, tuple] = {}

    @abstractmethod
    def handle_observation(self, tag: Hashable, parameter: str, observed_value: float) -> None:
        pass

    def add_observable(self, tag: Hashable, parameter: str, component: str, field: str,
                       transformer: Callable = lambda x: x) -> None:
        self._observables[(tag, parameter)] = component + "." + field, transformer

    def remove_observable(self, tag: Hashable, parameter: str) -> None:
        observable = tag, parameter
        if observable in self._observables:
            del self._observables[observable]

    def handle(self, response: Response) -> None:
        observations = response.observations
        if observations is not None:
            for observable, config in self._observables.items():
                tag, parameter = observable
                key, transformer = config
                observed_value = get_nested(key, observations, delimiter=".")
                # skip this observable if it does not exist in the current observations
                if observed_value is not None:
                    self.handle_observation(tag, parameter, transformer(observed_value))


# Controller
# ~~~~~~~~~~
class ControllerABC(WorkerABC, ABC):
    def __init__(self, client_details: Tuple[str, int, str] = None):
        self.client: Union[ClientABC, None] = None
        self.middleware: Dict[str, MiddlewareABC] = {}
        self._request_items: List[tuple] = []
        self._platform_type_key = None
        if client_details is not None:
            client_target_host, client_target_port, client_type = client_details
            self.set_client(client_target_host, client_target_port, client_type)

    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    @property
    def client_is_set(self) -> bool:
        return self.client is not None

    @property
    def request_items_stored(self) -> bool:
        return bool(self._request_items)

    def add_platform(self, type: str) -> None:
        _check_resource_type("platform", type, get_available_platforms())
        self._platform_type_key = type
        self.add_request_item("add", "platform", {"type": type})

    def add_component(self, key: str, type: str, **setup) -> None:
        self._check_platform_is_set()
        _check_resource_type("component", type, get_available_platform_components(self._platform_type_key))
        self.add_request_item("add", "component", {"key": key, "type": type, "setup": setup})

    def add_routine(self, key: str, interval: float, executor: str, operation: str, **kwargs) -> None:
        self._check_platform_is_set()
        self.add_request_item("add", "routine", {
            "key": key, "interval": interval, "executor": executor, "operation": operation, "kwargs": kwargs
        })

    def remove_platform(self) -> None:
        # Note that removing a platform even though one wan't set wont do anything
        self.add_request_item("remove", "platform", {})

    def remove_component(self, key: str) -> None:
        self._check_platform_is_set()
        self.add_request_item("remove", "component", {"key": key})

    def remove_routine(self, key: str) -> None:
        self._check_platform_is_set()
        self.add_request_item("remove", "routine", {"key": key})

    def execute_component(self, key: str, operation: str, **kwargs) -> None:
        self._check_platform_is_set()
        self.add_request_item("execute", "component", {"key": key, "operation": operation, "kwargs": kwargs})

    def get_observations(self, selected: list = None) -> None:
        self._check_platform_is_set()
        self.add_request_item("get", "observations", {"selected": selected})

    def get_components(self) -> None:
        self._check_platform_is_set()
        self.add_request_item("get", "components", {})

    def get_routines(self) -> None:
        self._check_platform_is_set()
        self.add_request_item("get", "routines", {})

    def add_request_item(self, method: str, resource: str, kwargs) -> None:
        # check if a client is set; throw an error, otherwise
        if not self.client_is_set:
            raise NotImplementedError("Can't submit request as a client has not been set.")
        self._request_items.append((method.lower().strip(), resource.lower().strip(), kwargs))

    def request_items_from_iterable(self, iterable: Iterable):
        for method, kwargs in iterable:
            self.add_request_item(method, **kwargs)

    def set_client(self, target_hostname: str, target_port: int, type: str = "tcp") -> None:
        """ Sets a new client for this controller

        :param target_hostname: Target hostname.
        :param target_port: Target port.
        :param type: Type of connection used by the client.
        :return: None.
        """
        self.client: ClientABC = client_types[type](target_hostname, target_port)

    def remove_client(self) -> None:
        """ Delete the connection client from this controller, if it has one."""
        self.client = None

    def add_middleware(self, label: str, obj: MiddlewareABC) -> None:
        self.middleware[label] = obj

    def remove_middleware(self, label: str) -> None:
        if label in self.middleware:
            del self.middleware[label]

    def send_request(self) -> Response:
        # make sure that a client is registered for this controller
        if not self.client_is_set:
            raise NotImplementedError("Controller requires a client in order to send a request.")
        # get the received response
        response = self.client.send_request(self._request_items)
        self._request_items.clear()
        # pass the response through the registered middleware
        for label, middleware in self.middleware.items():
            middleware.handle(response)
        # return the response
        return response

    def plot(self):
        plotter = Plotter()
        for middleware in self.middleware.values():
            if isinstance(middleware, PlotHandlerABC):
                middleware.add_to_plot(plotter)
        plotter.plot()

    def _check_platform_is_set(self) -> None:
        if self._platform_type_key is None:
            raise NotImplementedError("A platform has not been set.")


def _check_resource_type(resource: str, key: str, available: set):
    if key not in available:
        raise ValueError("{} key '{}' is invalid. Try: {}".format(resource.title(), key, ", ".join(available)))


# Ensemble controller
# ~~~~~~~~~~~~~~~~~~~
class ControllerEnsembleABC(dict, ABC):
    """ Controller ensemble abstract base class.

    Definition: A controller ensemble is a controller made up of one or many sub-controllers.

    sub-controllers ore units are stored as values of items in a dictionary where the keys of each item
    are the tags given to each unit.
    """

    def __init__(self, client_details: Dict[Hashable, Tuple[str, int, str]] = None,
                 middleware_details: Dict[str, MiddlewareABC] = None):
        super().__init__()
        # stores all the clients used by the units. note that when a client is added to a unit,
        # it is only a REFERENCE to a client this dict. not a new client instance. The same goes for
        # added middleware
        self._clients: Dict[Hashable, ClientABC] = {}
        self._registered_middleware: Dict[str, MiddlewareABC] = {}
        # add passed in clients
        if client_details is not None:
            self.add_clients_from_dict(client_details)
        if middleware_details is not None:
            self.add_middleware_from_dict(middleware_details)

    @abstractmethod
    def run(self, *args, **kwargs):
        pass

    def get_unit(self, tag: Hashable) -> ControllerABC:
        return self[tag]

    def add_client(self, client_label: Hashable, target_hostname: str, target_port: int,
                   client_type: str = "tcp") -> None:
        self._clients[client_label] = client_types[client_type](target_hostname, target_port)

    def remove_client(self, client_label: Hashable) -> None:
        if client_label in self._clients:
            # ~ remove all references to the added client from all the units it was added to.
            for tag in self.keys():
                self.remove_client_from_unit(client_label, tag)
            # THEN remove the client object
            del self._clients[client_label]

    def add_clients_from_dict(self, client_details: Dict[Hashable, Tuple[str, int, str]]) -> None:
        for client_label, details in client_details.items():
            target_hostname, target_port, client_type = details
            self.add_client(client_label, target_hostname, target_port, client_type)

    def add_client_to_unit(self, client_label: Hashable, tag: Hashable) -> None:
        self.get_unit(tag).client = self._clients[client_label]

    def remove_client_from_unit(self, client_label: Hashable, tag: Hashable) -> None:
        if self.get_unit(tag).client is self._clients[client_label]:
            self.get_unit(tag).remove_client()

    def add_middleware(self, middleware_label: str, middleware_obj: MiddlewareABC) -> None:
        self._registered_middleware[middleware_label] = middleware_obj

    def remove_middleware(self, middleware_label: str) -> None:
        if middleware_label in self._registered_middleware:
            # ~ remove all references to the added middleware from all the units it was added to.
            for tag in self.keys():
                self.remove_middleware_from_unit(middleware_label, tag)
            # THEN remove the client middleware
            del self._registered_middleware[middleware_label]

    def add_middleware_from_dict(self, middleware: Dict[str, MiddlewareABC]) -> None:
        for label, obj in middleware.items():
            self.add_middleware(label, obj)

    def add_middleware_to_unit(self, middleware_label: str, tag: Hashable) -> None:
        self.get_unit(tag).add_middleware(middleware_label, self._registered_middleware[middleware_label])

    def remove_middleware_from_unit(self, middleware_label: str, tag: Hashable):
        if self.get_unit(tag).middleware[middleware_label] is self._registered_middleware[middleware_label]:
            self.get_unit(tag).remove_middleware(middleware_label)

    def plot(self):
        plotter = Plotter()
        for middleware in self._registered_middleware.values():
            if isinstance(middleware, PlotHandlerABC):
                middleware.add_to_plot(plotter)
        plotter.plot()
