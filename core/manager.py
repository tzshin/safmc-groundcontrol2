import threading
import serial.tools.list_ports
import json
from typing import Callable
import logging

import rclpy
from rclpy.qos import QoSProfile
from espkenisis_msgs.msg import ChannelOverride

from .target import Target


class ESPKenisisManager:
    def __init__(self, callback_on_targets_update: Callable[[dict], None]):
        self.__callback_on_targets_update = callback_on_targets_update

        self.__serial = None

        self.__is_connected = False
        self.__read_serial_thread = None

        self.__logger = logging.getLogger(__name__)
        self.__logger.info("Initializing ESPKenisisManager")

        self.__data_handlers: dict[str, Callable[[dict], None]] = {}
        self.__data_handlers["targets_update"] = self.__handle_targets_update

        self.__targets: list[Target] = []

        self.__ros_node = None
        self.__ros_thread = None
        self.__ros_subs = {}  # {target_id: subscription} TODO: Revise this
        self.__is_ros_running = False

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

            self.__start_ros()
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
        
        self.__stop_ros()
        self.__logger.info("Disconnected")

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
            required_fields = Target.get_fields()
            if not all(field in target for field in required_fields):
                self.__logger.error(f"Target missing required fields, target: {target}")
                return

        self.__logger.debug(f"Pushing targets update to UI: {targets}")
        self.__callback_on_targets_update(targets)

    def __start_ros(self):
        if self.__ros_node:
            self.__logger.error("ROS integration already running")
            return

        try:
            rclpy.init()
            self.__ros_node = rclpy.create_node("espkenisis_manager")
            self.__is_ros_running = True
            self.__logger.debug("Initialized ROS node")

            self.__ros_thread = threading.Thread(target=self.__ros_spin, daemon=True)
            self.__ros_thread.start()
            self.__logger.debug("Started ROS spin thread")

            self.__update_ros_subs()
            self.__logger.info("Started ROS integration")
        except Exception as e:
            self.__logger.error(
                f"ROS integration initialization error: {e}", exc_info=True
            )

    def __stop_ros(self):
        if self.__ros_thread:
            self.__ros_thread.join(timeout=1.0)
        if self.__ros_node:
            self.__ros_node.destroy_node()
            rclpy.shutdown()

        self.__ros_node = None
        self.__ros_thread = None
        self.__is_ros_running = False
        self.__logger.info("Stopped ROS integration")

    def __ros_spin(self):
        while self.__is_ros_running and rclpy.ok():
            rclpy.spin_once(self.__ros_node)

    def __update_ros_subs(self):
        if not self.__is_ros_running and self.__ros_node:
            self.__logger.error("ROS integration not running")
            return

        for target_id in list(self.__ros_subs.keys()):
            if not any(target.id == target_id for target in self.__targets):
                self.__ros_node.destroy_subscription(self.__ros_subs[target_id])
                del self.__ros_subs[target_id]
                self.__logger.debug(f"Removed ROS subscription for target {target_id}")

        for target in self.__targets:
            if target.id not in self.__ros_subs:
                qos = QoSProfile(depth=10)
                sub = self.__ros_node.create_subscription(
                    ChannelOverride,
                    f"espkenisis/{target.id}/channel_override",
                    lambda msg, target_id=target.id: self.__process_channel_override(msg, target_id),
                    qos
                )
                self.__ros_subs[target.id] = sub
                self.__logger.debug(f"Created ROS subscription for target {target.id}")

    def __process_channel_override(self, msg: ChannelOverride, target_id: int):
        if not self.__is_connected:
            self.__logger.error("Not connected to ESPKenisis")
            return
        
        try:
            channels = list(msg.channels)
            duration = msg.duration
            bypass_safety = msg.bypass_safety

            if len(channels) > 16:
                self.__logger.error(f"Channel override for target {target_id} has too many channels: {len(channels)}, maximum is 16")
                return

            if not bypass_safety:
                if len(channels) > 4:
                    channels = channels[:4]
                    self.__logger.debug(f"Safety feature applied: limited to first 4 channels for target ID {target_id}")

            self.__send_override_command(target_id, channels, duration)
            self.__logger.debug(f"Processed ROS2 override command for target ID {target_id}")
        except Exception as e:
            self.__logger.error(f"Error processing ROS2 override command: {e}", exc_info=True)

    def __send_override_command(self, target_id: int, channels: list[int], duration: int):
        if not self.__is_connected or not self.__serial:
            self.__logger.error("Serial not connected")
            return
            
        command = {
            "type": "override_channels",
            "target_id": target_id,
            "channels": channels,
            "duration": duration
        }
        
        try:
            command_json = json.dumps(command) + "\n"

            self.__serial.write(command_json.encode())
            self.__logger.debug(f"Sent override command to target {target_id}: {channels} for {duration}ms")
        except Exception as e:
            self.__logger.error(f"Failed to send override command: {e}", exc_info=True)    