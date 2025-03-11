import PySimpleGUI as sg
import os
import logging

from core.manager import ESPKenisisManager


class ESPKenisisWindow:
    def __init__(self, theme: str, scale: float, refresh_rate_ms: int = 100):
        os.environ["XDG_SESSION_TYPE"] = "xcb"
        sg.theme(theme)
        sg.set_options(
            scaling=scale,
            font=("Helvetica", 10),
        )

        self.__logger = logging.getLogger(__name__)
        self.__logger.info("Initializing ESPKenisisUI")

        self.__font_smaller = (sg.DEFAULT_FONT[0], sg.DEFAULT_FONT[1] - 2)
        self.__font_larger = (sg.DEFAULT_FONT[0], sg.DEFAULT_FONT[1] + 4)

        self.__manager = ESPKenisisManager(
            callback_on_targets_update=self.__on_targets_update
        )
        self.__window_title = "ESPKenisis Radio Link Manager"
        self.__refresh_rate_ms = refresh_rate_ms
        self.__window = None

        self.__init_ui()

    def __init_ui(self):
        column_targets_content = [
            [sg.Text("Connect to ESPKenisis transmitter to view targets")]
        ]
        self.__create_window(column_targets_content)

    def __create_window(self, column_targets_content):
        frame_connection = sg.Frame(
            "Connection",
            [
                [
                    sg.Text("Serial Port:"),
                    sg.Combo(
                        self.__manager.get_all_ports(), key="-CF-PORTS-", size=(20, 1)
                    ),
                    sg.Button("Refresh", key="-CF-REFRESH-"),
                    sg.Button("Connect", key="-CF-CONNECT-"),
                    sg.Button("Disconnect", key="-CF-DISCONNECT-", disabled=True),
                ]
            ],
            font=self.__font_larger,
        )
        frame_targets = sg.Frame(
            "Targets",
            [
                [
                    sg.Column(
                        column_targets_content,
                        size=(800, 400),
                        scrollable=False,
                        vertical_scroll_only=True,
                    ),
                ]
            ],
            font=self.__font_larger,
        )
        layout = [[frame_connection], [frame_targets]]

        if self.__window:
            self.__window.close()
        self.__window = sg.Window(
            self.__window_title,
            layout=layout,
            finalize=True,
            resizable=True,
            size=(850, 700),
            icon=sg.DEFAULT_BASE64_ICON,
        )

    def __create_frame_target(self, target: dict):
        get_element_key = lambda target_id, element_type: f"-TARGET-{target_id}-{element_type}-"

        target_frame = sg.Frame(
            f"Target {target['id']}",
            [
                [
                    sg.Text(f"Target {target['id']} Control"),
                    sg.Button(
                        "Override: OFF",
                        key=get_element_key(target["id"], "OVERRIDE"),
                        enable_events=True,
                    ),
                    sg.Text("MAC: "),
                    sg.Text(target["mac"])
                ]
            ],
            font=self.__font_larger,
        )
        
        return target_frame

    def __on_targets_update(self, targets: list):
        self.__window.write_event_value("-TARGETS-UPDATE-", value=targets)

    def run(self):
        self.__logger.info("Starting UI event loop")
        while True:
            event, value = self.__window.read(timeout=self.__refresh_rate_ms)
            
            if event != "__TIMEOUT__":
                self.__logger.debug(f"Received event: {event}")

            if event == sg.WINDOW_CLOSED:
                break

            elif event == "-CF-REFRESH-":
                self.__logger.debug("Refreshing port list")
                ports = self.__manager.get_all_ports()
                self.__window["-CF-PORTS-"].update(values=ports)
                self.__logger.info(f"Found {len(ports)} ports")

            elif event == "-CF-CONNECT-":
                port = value["-CF-PORTS-"]
                self.__logger.info(f"Attempting to connect to {port}")
                if port and self.__manager.connect(port):
                    self.__logger.info(f"Successfully connected to {port}")
                    self.__window["-CF-CONNECT-"].update(disabled=True)
                    self.__window["-CF-DISCONNECT-"].update(disabled=False)
                else:
                    self.__logger.warning(f"Failed to connect to {port}")

            elif event == "-CF-DISCONNECT-":
                self.__logger.info("Disconnecting")
                self.__manager.disconnect()
                self.__window["-CF-CONNECT-"].update(disabled=False)
                self.__window["-CF-DISCONNECT-"].update(disabled=True)
                self.__window["-TARGET-COLUMN-"].update(
                    [sg.Text("Connect to ESPKenisis transmitter to view targets")]
                )
                self.__logger.info("Disconnected successfully")

            elif event == "-TARGETS-UPDATE-":
                self.__logger.debug("Updating targets display")
                targets_column = []
                targets = value[event]
                for target in targets:
                    targets_column.append(self.__create_frame_target(target))

                # self.__window["-TARGET-COLUMN-"].update([[sg.Text("Yes!!!")]])
                content = [[sg.Text("Yes!!!")]]
                self.__create_window(content)
                self.__logger.info(f"Updated display with {len(targets_column)} targets")
