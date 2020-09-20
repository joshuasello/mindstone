# -*- coding: utf-8 -*-
""" Worker implementation.

A worker is defined as an entity capable of interacting with objects outside the system boundaries
of an agent. That is, a worker interacts, manipulates, and handles components that are not part of
the agent.

Module Structure:
~~~~~~~~~~~~~~~~~
1. Worker
2. Components
    a. Pin Components
    b. Module Components
3. Platform
4. Debug Platform Definition
5. Raspberry Pi Platform Definition
6. Front-end utilities

"""

import threading
import time
from abc import ABC, abstractmethod
from typing import Dict, Callable, Any, Union

from ._utils import intersect_update, get_required_args, get_args, inner_merge, TerminalColors
from .connection import server_types, decode_request, encode_transaction, WorkerABC

_error_messages = {
    "component_not_found": "Component '{}' could not be found."
}


# Worker
# ~~~~~~
class Worker(WorkerABC):
    def __init__(self):
        self.method_handlers = {
            "add": {
                "component": self.add_component,
                "routine": self.add_routine,
                "platform": self.add_platform
            },
            "remove": {
                "component": self.remove_component,
                "routine": self.remove_routine,
                "platform": self.remove_platform
            },
            "execute": {
                "component": self.execute_component
            },
            "get": {
                "observations": self.get_observations,
                # make sure that get handler callees return list types otherwise there will
                # be issues encoding the data
                "components": self.get_components,
                "routines": self.get_routines
            }
        }

        self._platform: Union[PlatformABC, None] = None
        self._routines_active = False
        self._routines = {}
        self._routines_thread = threading.Thread(target=self._run_routines)

    def add_platform(self, type: str) -> None:
        """ Set a platform object to this worker.
        :param type: The type label for a specific platform.
        :return: None.
        """
        self._platform = platform_types[type]()

    def remove_platform(self) -> None:
        self._platform = None

    def add_routine(self, key: str, interval: float, executor: str, operation: str,
                    kwargs: dict) -> None:
        # check if the component that the routine acts on actually exists otherwise it may cause complications
        # when the routine is eventually run.
        if executor not in self._platform:
            raise RuntimeError(_error_messages["component_not_found"].format(executor))
        # add the new routine
        self._routines[key] = (executor, operation, kwargs, interval)

    def remove_routine(self, key: str) -> None:
        if key in self._routines:
            del self._routines[key]

    def add_component(self, key: str, type: str, setup: dict = None) -> None:
        setup = setup if setup is not None else {}
        self._platform.add_component(key, type, **setup)

    def remove_component(self, key: str) -> None:
        self._platform.remove_component(key)

    def execute_component(self, key: str, operation: str, kwargs: dict = None) -> None:
        kwargs = kwargs if kwargs is not None else {}
        # check if component with the given tag exists before executing.
        if key not in self._platform:
            raise RuntimeError(_error_messages["component_not_found"].format(key))
        # call the component function
        getattr(self._platform[key], operation)(**kwargs)

    def get_observations(self, selected: list = None) -> dict:
        to_read_from: set = set(selected) if selected else self._platform.keys()
        return {tag: component.read() for tag, component in self._platform.items()
                if hasattr(component, "read") and tag in to_read_from}

    def get_components(self) -> list:
        return list(self._platform)

    def get_routines(self) -> list:
        return list(self._routines)

    def serve(self, hostname: str = "", port: int = 50000, connection_type: str = "tcp") -> None:
        # start the routines thread
        self._routines_thread.start()

        # start the connection server so that controllers can connect to
        # this driver.
        print("{}STARTING SERVER @ ({}){}".format(TerminalColors.HEADER, port, TerminalColors.ENDC))
        print("Press CTRL+C to end the server.")
        print("-" * 50)

        server_types[connection_type].serve(hostname=hostname, port=port, on_receive=self._on_receive)

    def _on_receive(self, received: bytes, client_address: tuple = None) -> bytes:
        # ~ get the time that this request was handled
        feedback_to_send = {"received_time": time.time(), "error": None}
        try:
            print(TerminalColors.OKGREEN + "[{}] RECEIVED REQUEST from {}".format(
                time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(feedback_to_send["received_time"])),
                client_address
            ) + TerminalColors.ENDC)
            # ~ extract the data from the request.
            received_request = decode_request(received)
            # ~ handle the received data.
            feedback_to_send["feedback"] = self._process_request_items(received_request.items)
        except (RuntimeError, RuntimeWarning, ValueError) as e:
            # if the drive fails to process teh data then report the error back to the
            # controller instead of terminating the driver.
            feedback_to_send["error"] = "{}: {}".format(e.__class__.__name__, str(e))
            print(TerminalColors.FAIL + "\t!!! " + feedback_to_send["error"] + TerminalColors.ENDC)
        # ~ prepare the message to be sent
        feedback_to_send["sent_time"] = time.time()
        print(TerminalColors.OKGREEN + "[{}] RESPONSE SENT".format(
            time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(feedback_to_send["sent_time"])),
        ) + TerminalColors.ENDC)
        # ~ finally, return the result of the the processing done by the driver
        return encode_transaction(feedback_to_send)

    def _process_request_items(self, items: list) -> dict:
        response = {}
        for method, resource, kwargs in items:
            print("\tHANDLED METHOD '{}'".format(TerminalColors.OKBLUE + method + TerminalColors.ENDC))
            # display the keyword args as a list
            print("".join("\t\t" + "{}: {}\n".format(*item) for item in kwargs.items()).strip("\n"))
            if method not in self.method_handlers:
                raise RuntimeError("Received method '{}' is invalid. Try: {}".format(
                    method, ", ".join(self.method_handlers)))
            # noinspection PyNoneFunctionAssignment
            result = self.method_handlers[method][resource](**kwargs)
            if result is not None:
                inner_merge(response, method, {resource: result})
        return response

    def _run_routines(self):
        self._routines_active = True
        time.sleep(time.time() * 1000 % 1 / 1000)  # enable to sync clock
        start_time = time.time()
        to_update = {}

        while self._routines_active:
            # in case a subroutine is later on removed later on in the program
            # delete any entries from the update register that are no longer in use
            # TODO: review this nonsense????
            for key in self._routines.keys():
                if key not in self._routines.keys():
                    del to_update[key]

            for key, value in self._routines.items():
                if key not in to_update:
                    to_update[key] = False
                executor, operation, kwargs, time_interval = value
                # time should be considered accurate to the millisecond (3 decimal places)
                current_time = time.time()
                interval_mod = round((current_time - start_time) % time_interval)
                # to prevent issues with accuracies concerning time measurement, the equation
                # used is rounded to the nearest whole number. This caused another problem,
                # causing multiple updates in the time interval. This implementation makes it
                # so that the coordinator parameter_states associated with a given subroutine is only updated
                # once in the interval.
                if not to_update[key] and interval_mod == 0:
                    self.execute_component(executor, operation, kwargs)
                    to_update[key] = True
                elif interval_mod != 0:
                    to_update[key] = False
            time.sleep(.001 - time.time() * 1000 % 1 / 1000)


# Components
# ~~~~~~~~~~
class ComponentABC(ABC):
    @abstractmethod
    def cleanup(self):
        pass


# Pin Components
# ~~~~~~~~~~~~~~
class PinABC(ComponentABC, ABC):
    def __init__(self, channel_id: int, *args, **kwargs):
        self.id = channel_id


class InputPinABC(PinABC, ABC):
    @abstractmethod
    def value(self) -> bool:
        """Input value."""
        pass

    @abstractmethod
    def wait_for_edge(self, edge_type, timeout: int = None):
        """Blocks the execution of the program until an edge is detected"""
        pass

    @abstractmethod
    def event(self, edge_type, callback: Callable = None, bounce_time: int = None):
        pass

    @abstractmethod
    def remove_event(self):
        pass

    @abstractmethod
    def event_callback(self, callback: Callable, bounce_time: int = None):
        pass

    @abstractmethod
    def event_detected(self) -> bool:
        pass

    def read(self) -> dict:
        return {"is_high": self.value()}


class OutputPinABC(PinABC, ABC):
    @property
    @abstractmethod
    def state(self) -> bool:
        pass

    @abstractmethod
    def set_high(self):
        pass

    @abstractmethod
    def set_low(self):
        pass

    def read(self) -> dict:
        return {"state": self.state}

    def toggle(self) -> None:
        if self.state:
            self.set_low()
        else:
            self.set_high()


class PWMPinABC(PinABC, ABC):
    @abstractmethod
    def start(self, duty_cycle: float):
        pass

    @abstractmethod
    def stop(self):
        pass

    @abstractmethod
    def change_frequency(self, frequency: float):
        pass

    @abstractmethod
    def change_duty_cycle(self, duty_cycle: float):
        pass


# Module Components
# ~~~~~~~~~~~~~~~~~
class ModuleComponentABC(ComponentABC, ABC):
    """ Module component abstract base class.

    Module components operate by using one or more pin objects to perform some function.
    """
    pin_types: Dict[str, type(PinABC)] = {}
    default_settings: Dict[str, Any] = {}

    def __init__(self, settings: dict = None):
        self.pins: Dict[str, Union[PWMPinABC, OutputPinABC, InputPinABC]] = {}
        self._settings = intersect_update(self.default_settings.copy(), {} if settings is None else settings)

    def add_pin(self, tag: str, pin_id: int, pin_type: str, *args, **kwargs) -> None:
        self.pins[tag] = self.pin_types[pin_type](pin_id, *args, **kwargs)

    def remove_pin(self, tag: str) -> None:
        if tag in self.pins:
            self.pins[tag].cleanup()
            del self.pins[tag]

    def get_setting(self, key: str) -> Any:
        return self._settings[key]

    def cleanup(self) -> None:
        for pin in self.pins.values():
            pin.cleanup()


def make_module_component(module_cls: type(ModuleComponentABC),
                          pin_types: Dict[str, type(PinABC)]) -> type(ModuleComponentABC):
    module_cls.pin_types = pin_types.copy()
    return module_cls


class ServoComponent(ModuleComponentABC):
    default_settings = {
        "frequency": 50,
        "start_on_time": 0.0005,
        "end_on_time": 0.0025,
        "max_angle": 180
    }

    def __init__(self, output_pin: int, settings: Dict[str, float] = None):
        super().__init__(settings=settings)
        self.is_active: bool = False
        self.angle: float = 0.0
        # add pins that will be used:
        self.add_pin(tag="output", pin_id=output_pin, pin_type="pwm", frequency=self._settings["frequency"])

    def set_angle(self, angle: float):
        max_angle: float = self.get_setting("max_angle")
        if not self.is_active:
            raise RuntimeWarning("Could not set angle. Servo can't be used without first being activated.")
        if not 0 <= angle <= self._settings["max_angle"]:
            raise RuntimeWarning("Servo angle should be between 0 and {}".format(max_angle))
        self.angle = angle
        self.pins["output"].change_duty_cycle(self._angle_to_duty_cycle(angle))

    def get_angle(self) -> float:
        return self.angle

    def start(self) -> None:
        dc = self._angle_to_duty_cycle(self.get_angle())
        self.pins["output"].start(dc)
        self.is_active = True

    def stop(self) -> None:
        self.pins["output"].stop()
        self.is_active = False

    def read(self) -> dict:
        return {"angle": self.get_angle(), "is_active": self.is_active}

    def _angle_to_duty_cycle(self, angle: float) -> float:
        end_on_time: float = self.get_setting("end_on_time")
        start_on_time: float = self.get_setting("start_on_time")
        max_angle: float = self.get_setting("max_angle")
        frequency: float = self.get_setting("frequency")
        time_delta = end_on_time - start_on_time
        return round(frequency * 100 * (start_on_time + time_delta * angle / max_angle), 2)


class UltrasonicSensorComponent(ModuleComponentABC):
    default_settings = {
        "pulse_width": 0.00001,
        "n": 1
    }

    def __init__(self, output_pin: int, input_pin: int, settings: Dict[str, float] = None):
        super().__init__(settings=settings)
        self.add_pin(tag="output", pin_id=output_pin, pin_type="output")
        self.add_pin(tag="input", pin_id=input_pin, pin_type="input")

    def read(self) -> dict:
        n = int(self.get_setting("n"))
        return {"time_change": sum([self.measure_time_change() for _ in range(n)]) / n}

    def measure_time_change(self) -> float:
        trigger_channel: OutputPinABC = self.pins["output"]
        echo_channel: InputPinABC = self.pins["input"]

        trigger_channel.set_low()

        # create a short delay for the sensor to settle
        time.sleep(0.1)

        # request a pulse to the sensor's activate pin
        trigger_channel.set_high()
        time.sleep(self.get_setting("pulse_width"))
        trigger_channel.set_low()

        # measure time for echo to return to receiver
        while not echo_channel.value():
            pass
        initial_time = time.time()
        while echo_channel.value():
            pass
        final_time = time.time()

        return final_time - initial_time


class PlatformABC(dict, ABC):
    """ Platform abstract base class.

    A platform instance holds a collection of components which are used to directly interface with a
    device. The type of interface that is used will depend on the device the worker runs on as
    different platforms will have different supported components.
    """
    component_types: dict = {}

    def add_component(self, key: str, type: str, **kwargs) -> None:
        # Initialize a new component. Any existing component with the same name will be deleted and replaced.
        if key in self:
            self.remove_component(key)

        if type not in self.component_types:
            raise RuntimeError("Component type '{}' is not supported. Try: {}".format(
                type, ", ".join(self.component_types)))

        required_setup_args = get_required_args(self.component_types[type])
        required_setup_args.remove("self")
        if not required_setup_args.issubset(kwargs.keys()):
            raise RuntimeError("Component setup for '{}' does not satisfy all the required fields ({}).".format(
                key, ", ".join(required_setup_args)))
        self[key] = self.component_types[type](**kwargs)

    def remove_component(self, key: str) -> None:
        if key in self:
            self[key].cleanup()
            del self[key]

    def trigger_component(self, key: str, method: str, *args, **kwargs):
        return getattr(self[key], method)(*args, **kwargs)

    def cleanup(self) -> None:
        for tag in self.keys():
            self.remove_component(tag)


def add_platform(alias: str, component_types: Dict[str, type]) -> None:
    # copy the main platform class into an "anonymous" class and add the component types
    # used by the platform.
    new_platform_cls = type("", PlatformABC.__bases__, dict(PlatformABC.__dict__))
    new_platform_cls.component_types = component_types
    platform_types[alias] = new_platform_cls


platform_types: Dict[str, type(PlatformABC)] = {}


# Debug platform setup
# ~~~~~~~~~~~~~~~~~~~~
class DebugOutputPin(OutputPinABC):
    def __init__(self, pin_id: int):
        super().__init__(pin_id)
        print("NEW OUTPUT PIN (id={})".format(pin_id))
        self._state = False

    @property
    def state(self) -> bool:
        return self._state

    def set_high(self):
        self._state = True
        print("OUTPUT PIN SET (id={}, state={})".format(self.id, self._state))

    def set_low(self):
        self._state = False
        print("OUTPUT PIN SET (id={}, state={})".format(self.id, self._state))

    def cleanup(self):
        print("CLEANED OUTPUT PIN (id={})".format(self.id))


class DebugPWMPin(PWMPinABC):
    def __init__(self, pin_id: int, frequency: float):
        super().__init__(pin_id)
        print("NEW PWM PIN (id={}, frequency={})".format(pin_id, frequency))
        self.frequency = frequency
        self.duty_cycle = 0.0

    def start(self, duty_cycle: float):
        self.duty_cycle = duty_cycle
        print("START PWM PIN (id={}, dc={})".format(self.id, self.duty_cycle))

    def stop(self):
        print("STOP PWM PIN (id={}, dc={})".format(self.id, self.duty_cycle))

    def change_frequency(self, frequency: float):
        self.frequency = frequency
        print("CHANGED PWM PIN FREQUENCY (id={}, frequency={})".format(self.id, frequency))

    def change_duty_cycle(self, duty_cycle: float):
        self.duty_cycle = duty_cycle
        print("CHANGED PWM PIN DUTY CYCLE (id={}, dc={})".format(self.id, duty_cycle))

    def cleanup(self):
        print("CLEANED PWM PIN (id={})".format(self.id))


# add the debug platform to the platform stack
add_platform(
    "debug", {
        "output": DebugOutputPin,
        "pwm": DebugPWMPin,
        "servo": make_module_component(ServoComponent, {"pwm": DebugPWMPin})
    })

# Raspberry Pi platform setup
# ~~~~~~~~~~~~~~~~~~~~~~~~~~~

try:
    # Note that if this block of code does not throw an import error, it will be assumed that the raspberry pi platform
    # is available.
    import RPi.GPIO as RPi_GPIO

    # set default platform GPIO configurations
    RPi_GPIO.setmode(RPi_GPIO.BCM)
    RPi_GPIO.setwarnings(0)


    class RPiInputPin(InputPinABC):
        def __init__(self, pin_id: int, pull=None):
            super().__init__(pin_id)
            if pull is None:
                # this means that the value that is read by the input is undefined
                # until it receives a signal
                RPi_GPIO.setup(pin_id, RPi_GPIO.IN)
            else:
                RPi_GPIO.setup(pin_id, RPi_GPIO.IN, pull_up_down=pull)

        def value(self) -> bool:
            return RPi_GPIO.input(self.id) == RPi_GPIO.HIGH

        def wait_for_edge(self, edge_type, *args, **kwargs):
            RPi_GPIO.wait_for_edge(self.id, edge_type, *args, **kwargs)

        def event(self, edge_type, *args, **kwargs):
            RPi_GPIO.add_event_detect(self.id, edge_type, *args, **kwargs)

        def remove_event(self):
            RPi_GPIO.remove_event_detect(self.id)

        def event_callback(self, callback: Callable, *args, **kwargs):
            RPi_GPIO.add_event_callback(self.id, callback, *args, **kwargs)

        def event_detected(self) -> bool:
            return RPi_GPIO.event_detected(self.id)

        def cleanup(self) -> None:
            RPi_GPIO.cleanup(self.id)


    class RPiOutputPin(OutputPinABC):
        def __init__(self, pin_id: int):
            super().__init__(pin_id)
            RPi_GPIO.setup(pin_id, RPi_GPIO.OUT)

        @property
        def state(self) -> bool:
            return bool(RPi_GPIO.input(self.id))

        def set_high(self) -> None:
            RPi_GPIO.output(self.id, RPi_GPIO.HIGH)

        def set_low(self) -> None:
            RPi_GPIO.output(self.id, RPi_GPIO.LOW)

        def cleanup(self) -> None:
            RPi_GPIO.cleanup(self.id)


    class RPiPWMPin(PWMPinABC):
        def __init__(self, pin_id: int, frequency: float):
            super().__init__(pin_id)
            # ~ the channel needs to be set to an output before
            # it can be used as a pwm channel
            RPi_GPIO.setup(pin_id, RPi_GPIO.OUT)
            # ~ store a pwm variable that can be later used
            self.pwm = RPi_GPIO.PWM(pin_id, frequency)

        def start(self, duty_cycle: float) -> None:
            self.pwm.start(duty_cycle)

        def stop(self) -> None:
            self.pwm.stop()

        def change_frequency(self, frequency: float) -> None:
            self.pwm.ChangeFrequency(frequency)

        def change_duty_cycle(self, duty_cycle: float) -> None:
            self.pwm.ChangeDutyCycle(duty_cycle)

        def cleanup(self) -> None:
            self.stop()
            RPi_GPIO.cleanup(self.id)


    # add the debug platform to the platform stack
    add_platform(
        "rpi", {
            "input": RPiInputPin,
            "output": RPiOutputPin,
            "pwm": RPiPWMPin,
            "servo": make_module_component(ServoComponent, {"pwm": RPiPWMPin}),
            "ultrasonic": make_module_component(
                UltrasonicSensorComponent, {"input": RPiInputPin, "output": RPiOutputPin})
        })
except ImportError:
    # if there is an import error, it means that the raspberry pi platform type wont be added to the stack and
    # therefore can't be used.
    pass


# Front-end utilities
# ~~~~~~~~~~~~~~~~~~~

def get_available_platforms() -> set:
    return set(platform_types)


def get_available_platform_components(platform_key: str) -> set:
    return set(platform_types[platform_key].component_types)


def get_available_platform_component_setup_args(platform_key: str, component_label: str) -> set:
    return get_args(platform_types[platform_key].component_types[component_label].__init__)


def get_available_platform_component_required_setup_args(platform_key: str, component_label: str) -> set:
    return get_required_args(platform_types[platform_key].component_types[component_label].__init__)
