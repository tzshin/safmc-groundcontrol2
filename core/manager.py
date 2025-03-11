import threading
import serial.tools.list_ports
import json
from typing import Callable
import logging


class ESPKenisisManager:
    def __init__(self, callback_on_targets_update: Callable[[dict], None]):
        self.__callback_on_targets_update = callback_on_targets_update

        self.__serial = None

        self.__is_connected = False
        self.__read_serial_thread = None

        self.__logger = logging.getLogger(__name__)
        self.__logger.info("Initializing ESPKenisisManager")

        self.__data_handlers = {}
        self.__data_handlers["targets_update"] = self.__handle_targets_update

    def get_all_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        self.__logger.debug(f"Available ports: {ports}")
        return ports

    def connect(self, port: str, baudrate: int = 115200) -> bool:
        try:
            self.__logger.info(f"Connecting to {port} at {baudrate} baud")
            self.__serial = serial.Serial(port, baudrate, timeout=1)
            self.__is_connected = True
            
            self.__read_serial_thread = threading.Thread(
                target=self.__read_serial, daemon=True
            )
            self.__read_serial_thread.start()
            self.__logger.debug("Started serial read thread")
            
            self.__logger.info(f"Successfully connected to {port}")
            return True
        except Exception as e:
            self.__logger.error(f"Connection error: {e}", exc_info=True)
            return False

    def disconnect(self):
        if self.__read_serial_thread:
            self.__read_serial_thread.join(timeout=1.0)
        if self.__serial:
            self.__serial.close()

        self.__serial = None
        self.__is_connected = False
        self.__read_serial_thread = None

    def __read_serial(self):
        if not self.__serial:
            self.__logger.error("Serial not connected")
            return

        buffer = ""
        while self.__is_connected:
            try:
                if self.__serial.in_waiting > 0:
                    new_data = self.__serial.read(self.__serial.in_waiting).decode()
                    buffer += new_data
                    
                    lines = buffer.split("\n")
                    buffer = lines.pop()

                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue

                        try:
                            data = json.loads(line)
                            self.__process_data(data)
                        except json.JSONDecodeError:
                            self.__logger.error(f"Invalid JSON: {line}")
            except Exception as e:
                self.__logger.error(f"Serial read error: {e}", exc_info=True)
                self.__is_connected = False

    def __process_data(self, data: dict):
        if "type" not in data:
            self.__logger.error("Data missing 'type' field")
            return

        data_type = data["type"]
        if data_type in self.__data_handlers:
            self.__data_handlers[data_type](data)

    def __handle_targets_update(self, data: dict):
        if "targets" not in data:
            self.__logger.error("Targets update missing 'targets' field")
            return

        targets = data["targets"]
        for target in targets:
            required_fields = [
                "id",
                "name",
                "mac",
                "channels",
                "connection_state",
                "last_successful_send",
                "is_channels_overridden",
                "override_timeout_remaining",
            ]
            if not all(field in target for field in required_fields):
                self.__logger.error(f"Target missing required fields, target: {target}")
                return

        self.__logger.debug(f"Pushing targets update to UI: {targets}")
        self.__callback_on_targets_update(targets)
