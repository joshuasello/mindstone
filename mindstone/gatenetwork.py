# -*- coding: utf-8 -*-
""" Gate Network Implementation.

A gate network interface implements a control system by connecting
what are called gates to each other to form a network of gates. When the
controller is activated, these connected gates can perform operations like
processing data or deciding where to send or redirect data to. Gates also
have the ability to act as a interface between controller and the driver
by sending and receiving data during the runtime of the controller.

More generally, a gate network controller is a directed graph where its nodes (the controller's gates)
are unit operations that perform specific tasks. An edge (or connection) between
two nodes represents the flow of data from one node to another. This makes it easy to
define, represent, and implement different types of control systems that may
suit different requirements.

"""

import warnings
from abc import ABC, abstractmethod
from typing import Tuple, Callable, Hashable, Dict, Iterable, Any

import requests

from . import _graph
from ._utils import get_required_args, get_nested, inner_merge
from .controller import ControllerABC, ControllerEnsembleABC, MiddlewareABC


class Gate(ControllerABC, set):
    def __init__(self, procedure: Callable, client_details: Tuple[str, int, str] = None):
        super().__init__(client_details)
        self.feed = None
        self._procedure = procedure

    def __call__(self, feed=None):
        return self.run(feed)

    def run(self, feed=None):
        # add the feed to the gate so that it can be used within a the procedure.
        self.feed = feed
        if get_required_args(self._procedure):
            # This means that there are arguments provided and these arguments should be filled with this gate.
            result = self._procedure(self)
        else:
            result = self._procedure()
        # clear the stored field once it is used (there's no point in keeping it around).
        self.feed = None
        # if a client is set for this gate and there is a request to be sent, send that request.
        if self.client_is_set and self.request_items_stored:
            self.send_request()
        return result


class GateNetwork(ControllerEnsembleABC):
    def __init__(self, max_epochs: int = None, gates: dict = None, edges: Iterable[Tuple[Hashable, Hashable]] = None,
                 client_details: Dict[Hashable, Tuple[str, int, str]] = None,
                 middleware_details: Dict[str, MiddlewareABC] = None):
        super().__init__(client_details, middleware_details)
        self.epoch_count = 0
        self._max_epochs = None
        # dict: stores all the conditional edges where a key is a edge tuple and a value
        # is a condition tuple of the form (key, evaluation, value)
        self._conditional_edges: Dict[Tuple[Hashable, Hashable], Tuple[str, Callable, Any]] = {}
        # set the max epochs given
        if max_epochs is not None:
            self.set_max_epochs(max_epochs)
        # add the gates to the network
        if gates is not None:
            self.add_clients_from_dict(gates)
        # add the edges the the network
        if edges is not None:
            self.add_edges_from_iterable(edges)

    def run(self, starting_tag: Hashable, feed=None):
        # ~ check if anny gates have no other gates connected to it
        # and warn the user if there are more than one gates.
        # this is useful for finding gates that we redundantly added.
        isolated = _graph.get_isolated(self)
        if len(isolated) and len(self) > 1:
            warnings.warn("Isolated: {}".format(', '.join(isolated)))
        # ~ finally, run the network and return the result
        return self._resolve_all(starting_tag, feed)

    def set_max_epochs(self, n: int) -> None:
        if n < 1:
            raise ValueError("The max epochs can't be less than 1.")
        self._max_epochs = n

    def get_max_epochs(self):
        return self._max_epochs

    def gate_procedure(self, tag: Hashable, client_label: str = None,
                       middleware_labels: Iterable[str] = None) -> Callable:
        def decorator_repeat(func):
            self.add_gate(tag, func, client_label, middleware_labels)

        return decorator_repeat

    def add_gate(self, tag: Hashable, procedure: Callable, client_label: str = None,
                 middleware_labels: Iterable[str] = None) -> None:
        gate = Gate(procedure)
        _graph.add_node(self, tag, gate)
        # prime the gate for use
        # - if one is provided, add a client to the gate
        if client_label is not None:
            self.add_client_to_unit(client_label, tag)
        if middleware_labels is not None:
            for label in middleware_labels:
                self.add_middleware_to_unit(label, tag)

    def remove_gate(self, tag: Hashable) -> None:
        _graph.remove_node(self, tag)

    def add_gates_from_dict(self, gate_details: Dict[Hashable, Tuple]):
        for tag, details in gate_details.items():
            procedure, client_label = details[0], None
            if len(details) <= 2:
                client_label = details[1]
            else:
                raise ValueError("Gate details are invalid.")
            self.add_gate(tag, procedure, client_label)

    def add_edge(self, from_tag: Hashable, to_tag: Hashable) -> None:
        _graph.add_edge(self, from_tag, to_tag)

    def remove_edge(self, from_tag: Hashable, to_tag: Hashable) -> None:
        _graph.remove_edge(self, from_tag, to_tag)

    def add_edges_from_iterable(self, edges: Iterable[Tuple[Hashable, Hashable]]):
        for edge in edges:
            from_tag, to_tag = edge
            self.add_edge(from_tag, to_tag)

    def add_conditional_edge(self, from_tag: Hashable, to_tag: Hashable, target, path: str,
                             evaluator: Callable = lambda a, b: a == b, fallback_tag: Hashable = None) -> None:
        """ Creates a conditional connection from one gate to another.

        The first parameter of the evaluator is the value that is to be compared and the second
        is the target value.

        :param from_tag: Parent gate.
        :param to_tag: Child gate.
        :param path: Locates the value in the input data when the `to_tag` gate is activated
        :param target: Value that is compared against that key-value
        :param evaluator: Binary comparison function that returns a boolean value.
        :param fallback_tag: The fallback gate tag in the case that the condition evaluates to false
        :return: None
        """
        self._conditional_edges[(from_tag, to_tag)] = (path, evaluator, target)
        self.add_edge(from_tag, to_tag)
        if fallback_tag is not None:
            # create the compliment conditional edge with a a connection from the from tag to the fallback tag,
            # if a fallback is set
            self.add_conditional_edge(from_tag, fallback_tag, target, path, lambda a, b: not evaluator(a, b))

    def remove_conditional_edge(self, from_tag: Hashable, to_tag: Hashable) -> None:
        edge = (from_tag, to_tag)
        if edge in self._conditional_edges:
            del self._conditional_edges[edge]
        self.remove_edge(from_tag, to_tag)

    def _resolve_all(self, starting_tag: Hashable, initial_feed=None):
        current_generation = {starting_tag: self[starting_tag].run(initial_feed)}
        # unsatisfied stores the tags and activation results of the gates that still expect to be used
        # later on in the network
        unsatisfied = {}
        # a gate is resolved if it is activated and has no descendant connections.
        resolved = {}
        self.epoch_count = 0
        while True:
            to_be_evaluated = {}
            current_generation_copy = current_generation.copy()
            for current_tag, current_result in current_generation_copy.items():
                current_gate: Gate = self[current_tag]
                # if the gate has no children, add it the resolved stack as it wont be needed later on in the
                # evolution of the network.
                if not len(current_gate):
                    resolved[current_tag] = current_generation.pop(current_tag)
                    continue
                # prime next generation
                for child_tag in current_gate:
                    # evaluate the conditional edge case
                    conditional_edge = self._conditional_edges.get((current_tag, child_tag), None)
                    unconditional_parents = {current_tag}
                    if conditional_edge is not None:
                        if not isinstance(current_result, dict):
                            continue
                        location, evaluator, target = conditional_edge
                        # weed out all the failed conditional edges i.e. don't evaluate the nodes where the condition
                        # came out to false
                        if not evaluator(get_nested(location, current_result), target):
                            continue
                    else:
                        unconditional_parents = {parent_tag for parent_tag in _graph.get_in_neighbors(self, child_tag)
                                                 if (parent_tag, child_tag) not in self._conditional_edges}
                    # make sure to check against the copy because the generation changes with each child
                    descendants = unsatisfied.pop(child_tag, {})
                    descendants.update(current_generation_copy)
                    if unconditional_parents.issubset(descendants):
                        super_result = {}
                        for parent_tag in unconditional_parents:
                            # remove parents from the generation
                            current_generation.pop(parent_tag, None)
                            super_result.update(descendants[parent_tag] if descendants[parent_tag] is not None else {})
                        inner_merge(to_be_evaluated, child_tag, super_result)
                    else:
                        # if the gate needs to evaluated at a late stage, ensure that the preceding gate
                        # is around when that evaluation takes place by adding it back into the generation
                        inner_merge(unsatisfied, child_tag, {current_tag: current_result})
            # replace the current generation with its copy.
            current_generation.update({next_tag: self[next_tag].run(next_feed)
                                       for next_tag, next_feed in to_be_evaluated.items()})
            self.epoch_count += 1
            # if all the gates in this generation have been resolve, stop the main loop and return the resolve
            if not len(current_generation) or self.epoch_count == self._max_epochs:
                return resolved


class GateProcedureABC(ABC):
    @abstractmethod
    def __call__(self, gate: Gate):
        pass


class HTTPRequesProcedure(GateProcedureABC):
    _http_method_handlers = {
        "GET": lambda url, data: requests.get(url=url, params=data),
        "POST": lambda url, data: requests.post(url=url, data=data)
    }

    _response_formatters = {
        "json": lambda response: response.json()
    }

    def __init__(self, url: str, request_method: str = "GET", response_format: str = "json"):
        super().__init__()
        self._url = url
        self._method = request_method.upper().strip()
        self._format = response_format.lower().strip()

    def __call__(self, gate: Gate):
        return self._response_formatters[self._format](self._http_method_handlers[self._method](
            self._url, {} if gate.feed is None else gate.feed))


class InjectionHandler(dict, GateProcedureABC):
    def __call__(self, gate: Gate):
        result = {} if gate.feed is None else gate.feed
        result.update(self)
        return result
