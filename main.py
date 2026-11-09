"""Fullscreen pygame launcher for other pygame programs.

Navigation: joystick / arcade controls (or keyboard equivalents).
Exit: keyboard only (Escape, Alt+F4 / window close).
"""

import configparser
import os
import sys

import pygame

from launcher import Launcher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")


def load_config():
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    sec = cfg["launcher"] if cfg.has_section("launcher") else {}
    script_dir = sec.get("script_dir", "games")
    if not os.path.isabs(script_dir):
        script_dir = os.path.join(BASE_DIR, script_dir)
    return {
        "script_dir": os.path.normpath(script_dir),
        "python": sec.get("python", "") or sys.executable,
        "font_size": int(sec.get("font_size", 16)),
        "scroll_speed": float(sec.get("scroll_speed", 10)),
    }


def main():
    try:
        Launcher(load_config()).run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
