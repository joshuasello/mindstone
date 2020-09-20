# -*- coding: utf-8 -*-
""" Graph module.

This module holds a collection of functions that can be used for handling graph data structures. Note,
that this implementation is not meant to be a complete toolset for graphs and networks, and only caters
for directed graphs.

Implementing a graph instance:
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
In order to use the functions in this module, you should construct your graph as a dictionary where the key
of an item in the dictionary is a label given to a node/vertex in the graph, and the values of the item is a
set containing the children (or the endpoints of the outgoing edges) connected to that node.

More formally, a directed graph is a labelled collection of sets
    G=<g1, g2, ..., gn>
where
    gi is a subset of {x|1 <= x <= ord(G) and x is not equal to i}

A node a is connected to another node b if
    b in ga

Note that, in this case, the order the set gi are listed in, identifies them.
"""

import warnings
from collections import Hashable, Iterable


def add_node(graph: dict, key: Hashable, container: set = None) -> None:
    graph[key] = set() if container is None else container


def remove_node(graph: dict, key: Hashable) -> None:
    if key in graph:
        del graph[key]
        # remove inbound connections to the node from other nodes in the graph
        for node_key in graph.keys():
            if key in graph[node_key]:
                graph[node_key].remove(key)


def add_edge(graph: dict, from_key: Hashable, to_key: Hashable) -> None:
    if from_key == to_key:
        raise ValueError("A node cannot be connected to itself")
    graph[from_key].add(to_key)


def add_edges_from_iterable(graph: dict, iterable: Iterable):
    for edge_definition in iterable:
        add_edge(graph, *edge_definition)


def remove_edge(graph: dict, from_key: Hashable, to_key: Hashable):
    graph[from_key].remove(to_key)


def get_edges(graph: dict) -> list:
    return [[from_key, to_key] for from_key, node in graph.items() for to_key in node]


def is_acyclic(graph: dict) -> bool:
    for path in get_all_complete_paths(graph):
        if path[0] == path[-1]:
            return False
    return True


def get_in_neighbors(graph: dict, key: Hashable) -> set:
    return set([k for k, n in graph.items() if key in n])


def get_out_neighbors(graph: dict, key: Hashable) -> set:
    return set(graph[key])


def get_in_degree(graph: dict, key: Hashable) -> int:
    return len(get_in_neighbors(graph, key))


def get_out_degree(graph: dict, key: Hashable) -> int:
    return len(get_out_neighbors(graph, key))


def in_degree(graph: dict, key: Hashable) -> int:
    return len(get_in_neighbors(graph, key))


def out_degree(graph: dict, key: Hashable) -> int:
    return len(get_out_neighbors(graph, key))


def get_complete_paths(graph: dict, key: Hashable, sort: bool = False) -> list:
    paths = []
    _get_paths_util(graph, key, paths, [])
    return sorted(paths, key=lambda x: len(x)) if sort else paths


def get_all_complete_paths(graph: dict) -> list:
    paths = []
    for key in graph.keys():
        paths += get_complete_paths(graph, key)
    return paths


def get_isolated(graph: dict) -> set:
    return {key for key in graph.keys() if get_in_degree(graph, key) == get_out_degree(graph, key) == 0}


def get_sources(graph: dict) -> set:
    return {key for key in graph.keys() if is_source(graph, key)}


def is_isolated(graph: dict, key: Hashable) -> bool:
    return key in get_isolated(graph)


def is_source(graph: dict, key: Hashable) -> bool:
    return not in_degree(graph, key)


def is_sink(graph: dict, key: Hashable) -> bool:
    return not out_degree(graph, key)


def merge(graph: dict, to_merge: dict, new_edges: Iterable = None):
    if not graph.keys().isdisjoint(to_merge.keys()):
        warnings.warn("There are some key naming conflicts between the two graphs.")
    # ~ combine the two graph's nodes
    graph.update(to_merge)
    # ~ add any additional communication if implemented
    if new_edges is not None:
        add_edges_from_iterable(graph, new_edges)


def _get_paths_util(graph: dict, key: Hashable, paths: list, prepended: list, start: Hashable = None):
    prepended += [key]
    out_neighbors = get_out_neighbors(graph, key)

    if not out_neighbors or key == start:
        return prepended

    start = key if start is None else start

    for child in out_neighbors:
        new_path = _get_paths_util(graph, child, paths, list(prepended), start)
        if new_path:
            paths.append(new_path)
