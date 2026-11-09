"""Fullscreen pygame launcher for other pygame programs.

Usage: python main.py [GAMES_DIR]

Navigation: joystick / arcade controls (or keyboard equivalents).
Exit: keyboard only (Escape, or the OS quit event such as Alt+F4).
"""

import argparse
import configparser
import os
import sys

import pygame

from launcher import Launcher

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.ini")
DEFAULT_GAMES_DIR = os.path.join(BASE_DIR, "games")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Fullscreen launcher for pygame games.")
    parser.add_argument(
        "games_dir", nargs="?", default=DEFAULT_GAMES_DIR,
        help="folder containing the games: each sub-folder with a main.py is "
             "listed by its folder name (default: the 'games' folder next to "
             "this launcher)")
    return parser.parse_args(argv)


def load_config(games_dir):
    cfg = configparser.ConfigParser()
    cfg.read(CONFIG_FILE)
    sec = cfg["launcher"] if cfg.has_section("launcher") else {}
    return {
        "games_dir": os.path.abspath(games_dir),
        "python": sec.get("python", "") or sys.executable,
        "font_size": int(sec.get("font_size", 16)),
        "description_font_size": int(sec.get("description_font_size", 16)),
        "error_font_size": int(sec.get("error_font_size", 16)),
        "scroll_speed": float(sec.get("scroll_speed", 10)),
    }


def main(argv=None):
    args = parse_args(argv)
    try:
        Launcher(load_config(args.games_dir)).run()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
