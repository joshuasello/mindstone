# -*- coding: utf-8 -*-
""" Connection definition.

The connection module is used to allow for communication between a controller and a worker. The way communication works
is that a controller will send a request to an active worker, with the request containing a list of instructions for the
worker to execute. Once received, the worker will process those instructions and build a response. after which it will
send the response to the controller. The controller can do what it likes with the response.

"""

import socket
import socketserver
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, is_dataclass
from typing import Tuple, Dict, Callable, List, Union

# To encode and decode messages, msgpack (https://github.com/msgpack/msgpack-python)
# is used instead of JSON, because of its memory efficiency and speed.
import msgpack


class WorkerABC(ABC):
    @abstractmethod
    def add_platform(self, type: str) -> None:
        pass

    @abstractmethod
    def add_routine(self, key: str, interval: float, executor: str, operation: str, kwargs: dict) -> None:
        pass

    @abstractmethod
    def add_component(self, key: str, type: str, setup=None) -> None:
        pass

    @abstractmethod
    def remove_platform(self) -> None:
        pass

    @abstractmethod
    def remove_routine(self, key: str) -> None:
        pass

    @abstractmethod
    def remove_component(self, key: str) -> None:
        pass

    @abstractmethod
    def execute_component(self, key: str, operation: str, kwargs=None) -> None:
        pass

    @abstractmethod
    def get_observations(self, selected: list = None):
        pass

    @abstractmethod
    def get_components(self):
        pass

    @abstractmethod
    def get_routines(self):
        pass


@dataclass
class Request:
    sent_time: float
    items: list


@dataclass
class Response:
    received_time: float
    sent_time: float
    feedback: dict = None
    error: str = None

    @property
    def error_occurred(self) -> bool:
        return self.error is not None

    @property
    def time_interval(self) -> float:
        return self.sent_time - self.received_time

    @property
    def observations(self) -> Union[dict, None]:
        try:
            return self.feedback["get"]["observations"]
        except KeyError:
            pass


@dataclass
class ClientABC(ABC):
    target_hostname: str
    target_port: int

    @property
    def target_address(self) -> Tuple[str, int]:
        return self.target_hostname, self.target_port

    @abstractmethod
    def send_and_receive(self, to_send: bytes) -> bytes:
        pass

    def send_request(self, items: List[Tuple[str, dict]]) -> Response:
        received = self.send_and_receive(encode_transaction({
            "sent_time": time.time(),
            "items": items
        }))
        return decode_response(received)


class ServerABC(ABC):
    @staticmethod
    @abstractmethod
    def serve(hostname: str, port: int, on_receive: Callable) -> None:
        pass


class _TCPRequestHandler(socketserver.BaseRequestHandler):
    request_handler: Callable = None

    def handle(self) -> None:
        # 1. receive the data from the client
        # self.request is the TCP socket connected to the client
        received = self.request.recv(1024).strip()
        # 2. using the request handler callable, process that data
        # and retrieve the data that should be sent back to the client
        to_send = _TCPRequestHandler.request_handler(received, self.client_address)
        # 3. finally, request the data back to the client.
        self.request.sendall(to_send)


class TCPServer(ServerABC):
    @staticmethod
    def serve(hostname: str, port: int, on_receive: Callable) -> None:
        _TCPRequestHandler.request_handler = on_receive
        with socketserver.TCPServer((hostname, port), _TCPRequestHandler) as server:
            # Activate the server; this will keep running until the user
            # interrupts the program with Ctrl-C
            server.serve_forever()


class TCPClient(ClientABC):
    def send_and_receive(self, to_send: bytes) -> bytes:
        # 1. create a socket (SOCK_STREAM means a TCP socket)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            # 2. connect to server and request data
            sock.connect((self.target_hostname, self.target_port))
            sock.send(to_send)
            # 3. receive data from the server and shut down
            received = sock.recv(1024)
        return received


def encode_transaction(to_encode: dict) -> bytes:
    return msgpack.dumps(to_encode.copy())


def decode_request(to_decode: bytes) -> Request:
    return _decode_transaction(Request, to_decode)


def decode_response(to_decode: bytes) -> Response:
    return _decode_transaction(Response, to_decode)


def get_host_ip() -> str:
    return socket.gethostbyname(get_hostname())


def _decode_transaction(datacls, to_decode: bytes):
    # check if the provided object is a dataclass
    if not is_dataclass(datacls):
        raise ValueError("Object provided is not a dataclass.")
    # decode the message
    decoded: dict = msgpack.loads(to_decode)
    # check the validity of the message
    unsatisfied = _get_unsatisfied_fields(datacls, decoded)
    if len(unsatisfied):
        raise ValueError("Received does not satisfy the following fields: {}".format(", ".join(unsatisfied)))
    return datacls(**decoded)


def _get_unsatisfied_fields(datacls, mapping: dict) -> set:
    # check if the provided object is a dataclass
    if not is_dataclass(datacls):
        raise ValueError("Object provided is not a dataclass.")
    return {field for field, field_type in datacls.__dict__["__annotations__"].items()
            if not isinstance(mapping.get(field, None), field_type) and getattr(datacls, field) is not None}


get_hostname: Callable = socket.gethostname

# prevents OSError: [Errno 98] Address already in use
# This error usually occurs when you quit the server on a device and restart it over a short period of time.
# This is very annoying.
socketserver.TCPServer.allow_reuse_address = True

client_types: Dict[str, type(ClientABC)] = {
    "tcp": TCPClient
}
server_types: Dict[str, type(ServerABC)] = {
    "tcp": TCPServer
}

# a connection type should have both an implementation as a sever and an implementation as a client,
# therefore make sure that each client type corresponds to a server implementation and vice verse...
assert client_types.keys() == server_types.keys(), "client-server implementation entries don't match."
