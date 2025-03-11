from dotenv import load_dotenv
import os
import logging
from readable_log_formatter import ReadableFormatter

from ui.espk_window import ESPKenisisUI


if __name__ == "__main__":
    logger = logging.getLogger()
    logger.handlers.clear()
    hdlr = logging.StreamHandler()
    hdlr.setFormatter(ReadableFormatter())
    logger.addHandler(hdlr)
    logger.setLevel(logging.DEBUG)
    
    load_dotenv()
    ui_theme = os.getenv("UI_THEME")
    ui_scale = os.getenv("UI_SCALE")

    ui = ESPKenisisUI(theme=ui_theme, scale=ui_scale)
    ui.run()
