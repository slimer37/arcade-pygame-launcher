"""The launcher screen: program list, launching, and result display."""

import math
import os

import pygame

from controls import DOWN, SELECT, UP, Input, is_quit
from program import Program, ProgramResult, find_programs, run_program

BG_COLOR = (240, 240, 240)
TEXT_COLOR = (10, 10, 10)
ERROR_COLOR = (139, 0, 0)  # dark red
MARGIN = 40
ERROR_BOX_FRACTION = 1 / 3  # error box: top third of the right half
SELECTION_ALPHA = 40  # opacity (0-255) of the box behind the selection
DEPTH = 0.15  # how quickly rows shrink with distance from the selection
FADE_TIME = 0.4  # seconds to fade to black before launching / back after
FPS = 60

NO_MINIMIZE_HINT = "SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"
# Video drivers without a window system, where only one process can own the
# screen; the launcher has to release it while a program runs.
EXCLUSIVE_DRIVERS = {"kmsdrm", "kmsdrm_legacy", "fbcon", "directfb"}


def depth_scale(d):
    """Size of a row d rows away from the centre, relative to the centre row."""
    return 1 / (1 + DEPTH * abs(d))


def depth_offset(d):
    """Distance (in full-size rows) from the centre to a row d rows away.

    This is the integral of depth_scale, so shrunken rows pack closer
    together and positions move smoothly as the list scrolls.
    """
    return math.copysign(math.log1p(DEPTH * abs(d)) / DEPTH, d)


def wrap_text(font, text, width):
    """Word-wrap text into lines that fit within width pixels."""
    out = []
    for para in text.splitlines() or [""]:
        line = ""
        for word in para.split(" "):
            candidate = f"{line} {word}" if line else word
            if font.size(candidate)[0] <= width:
                line = candidate
                continue
            if line:
                out.append(line)
            # Hard-break words that are wider than the line on their own,
            # binary-searching for the longest prefix that fits.
            while font.size(word)[0] > width and len(word) > 1:
                lo, hi = 1, len(word) - 1
                while lo < hi:
                    mid = (lo + hi + 1) // 2
                    if font.size(word[:mid])[0] <= width:
                        lo = mid
                    else:
                        hi = mid - 1
                out.append(word[:lo])
                word = word[lo:]
            line = word
        out.append(line)
    return out


def fit_lines(lines, room, keep_end=False):
    """Trim lines to at most room lines, marking the cut with "...".
    Keeps the start, or the end if keep_end."""
    if len(lines) <= room:
        return lines
    if room < 1:
        return []
    if keep_end:
        return ["..."] + lines[len(lines) - room + 1:]
    return lines[:room - 1] + ["..."]


class Launcher:
    def __init__(self, config):
        self.config = config
        self.programs = find_programs(config["games_dir"])
        self.selected = 0
        self.scroll = 0.0  # list position in rows; animates towards selected
        self.result: ProgramResult | None = None  # set after a failed run
        self.input = Input()
        self.name_surfaces: dict[str, pygame.Surface] = {}  # rendered names
        self.blackout = 1.0  # opacity of the black overlay; fades in on start
        self.blackout_target = 0.0  # update() moves blackout towards this
        self.clock = pygame.time.Clock()
        self.result_cache: tuple[ProgramResult, list[str]] | None = None
        self.info_cache: dict[tuple[Program, int], list[str]] = {}  # wrapped descriptions

    # Created in open_display() and recreated after every launched program.
    screen: pygame.Surface
    font: pygame.font.Font
    error_font: pygame.font.Font

    # -- display lifecycle -------------------------------------------------

    def open_display(self):
        # Keep the fullscreen launcher window up (black) behind a running
        # program instead of letting SDL minimise it when focus moves away.
        os.environ[NO_MINIMIZE_HINT] = "0"
        pygame.display.init()
        pygame.joystick.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Launcher")
        pygame.mouse.set_visible(False)
        self.font = pygame.font.Font(None, self.config["font_size"])
        self.error_font = pygame.font.Font(None, self.config["error_font_size"])
        self.name_surfaces.clear()
        self.result_cache = None  # depends on the font and screen size
        self.info_cache.clear()
        self.input.open_joysticks()
        pygame.event.clear()

    def close_display(self):
        """Release the screen and controllers so the child program gets them."""
        self.input.joysticks.clear()
        pygame.joystick.quit()
        pygame.display.quit()

    # -- actions -----------------------------------------------------------

    def launch(self):
        if not self.programs:
            return
        program = self.programs[self.selected]
        name, script = program.name, program.script
        self.fade_out()
        # Programs shouldn't inherit the launcher's no-minimise hint.
        env = {k: v for k, v in os.environ.items() if k != NO_MINIMIZE_HINT}
        if pygame.display.get_driver() in EXCLUSIVE_DRIVERS:
            # No window system: the program can't open the screen while we
            # hold it, so release it and block until the program exits.
            self.close_display()
            result = run_program(name, self.config["python"], script, env=env)
            self.open_display()
        else:
            # Leave the black window up underneath the program, paused: no
            # drawing, just keeping the window responsive.
            result = run_program(name, self.config["python"], script,
                                 idle=self.idle, env=env)
            # The window system hands focus back to this window, the next one
            # down, when the program's window closes.
            pygame.event.clear()  # drop input meant for the program
            self.input.held.clear()
        self.programs = find_programs(self.config["games_dir"])
        self.info_cache.clear()
        self.selected = min(self.selected, max(len(self.programs) - 1, 0))
        self.scroll = float(self.selected)
        self.blackout, self.blackout_target = 1.0, 0.0  # fade back in
        self.clock.tick()  # don't count the program's run time as a frame
        if result.failed:
            self.result = result

    def idle(self):
        """Called while a program runs: handle window-system events without
        drawing, only re-presenting the black frame if the window is exposed."""
        for event in pygame.event.get():
            if event.type in (pygame.WINDOWEXPOSED, pygame.VIDEOEXPOSE):
                pygame.display.flip()

    def fade_out(self):
        """Fade the screen to black (blocking) before handing it over."""
        self.blackout_target = 1.0
        while self.blackout < 1:
            dt = self.clock.tick(FPS) / 1000
            pygame.event.pump()  # stay responsive to the OS; input is ignored
            self.update(dt)
            self.draw()

    def act(self, action):
        if self.result is not None:
            # Error screen: any control press dismisses it.
            self.result = None
            return
        if action == UP:
            self.selected = max(self.selected - 1, 0)
        elif action == DOWN:
            self.selected = min(self.selected + 1, len(self.programs) - 1)
        elif action == SELECT:
            self.launch()

    def update(self, dt):
        """Slide the list towards the selection at scroll_speed rows/sec,
        and fade the black overlay towards its target."""
        fade_step = dt / FADE_TIME
        if self.blackout < self.blackout_target:
            self.blackout = min(self.blackout + fade_step, self.blackout_target)
        else:
            self.blackout = max(self.blackout - fade_step, self.blackout_target)
        step = self.config["scroll_speed"] * dt
        diff = self.selected - self.scroll
        self.scroll = float(self.selected) if abs(diff) <= step else \
            self.scroll + (step if diff > 0 else -step)

    # -- drawing -----------------------------------------------------------

    def name_surface(self, name):
        surf = self.name_surfaces.get(name)
        if surf is None:
            surf = self.name_surfaces[name] = self.font.render(name, True, TEXT_COLOR)
        return surf

    def draw_list(self):
        """Program list in the left half, selection row fixed at the vertical
        centre. Rows shrink with distance from the selection (towards the
        left edge and the centre) for depth, and fade out towards the top
        and bottom edges."""
        w, h = self.screen.get_size()
        half_h = h / 2
        line_h = self.font.get_linesize()
        box_x = MARGIN + line_h // 2  # room for the dashed guide line
        text_x = box_x + line_h // 4  # padding inside the selection box

        def row_centre(d):
            return half_h + depth_offset(d) * line_h

        def fade(centre):
            return 1 - abs(centre - half_h) / half_h

        def visible(d):
            return fade(row_centre(d)) > 0 and depth_scale(d) * line_h >= 1

        if not self.programs:
            msg = f"No programs found in {self.config['games_dir']}"
            for i, line in enumerate(wrap_text(self.font, msg, w // 2 - 2 * MARGIN)):
                self.screen.blit(self.font.render(line, True, TEXT_COLOR),
                                 (MARGIN, half_h - line_h / 2 + i * line_h))
            return

        self.screen.set_clip(pygame.Rect(0, 0, w // 2, h))

        # Dashed vertical guide, one dash per row slot over the full height.
        # It scrolls with the list and shares its fade, so the fade stays
        # visible even when there are only a few programs.
        dash_w = max(2, line_h // 16)
        offset = self.scroll % 1
        for d, step in ((-offset, 1), (-offset - 1, -1)):  # downwards, upwards
            while visible(d):
                centre = row_centre(d)
                dash = pygame.Surface((dash_w, max(1, round(line_h * 0.7 * depth_scale(d)))))
                dash.fill(TEXT_COLOR)
                dash.set_alpha(round(255 * fade(centre)))
                self.screen.blit(dash, (MARGIN, centre - dash.get_height() / 2))
                d += step

        # Faded box behind the selection, which always sits on the centre row.
        box = pygame.Surface((w // 2 - MARGIN - box_x, line_h))
        box.fill(TEXT_COLOR)
        box.set_alpha(SELECTION_ALPHA)
        self.screen.blit(box, (box_x, half_h - line_h / 2))

        for i, program in enumerate(self.programs):
            d = i - self.scroll
            if not visible(d):
                continue
            centre = row_centre(d)
            surf = self.name_surface(program.name)
            scale = depth_scale(d)
            if scale < 0.999:
                surf = pygame.transform.smoothscale_by(surf, scale)
            surf.set_alpha(round(255 * fade(centre)))
            # Left-aligned, so rows shrink towards the left edge.
            self.screen.blit(surf, (text_x, centre - surf.get_height() / 2))
        self.screen.set_clip(None)

    def draw_lines(self, lines, font, color, y):
        """Draw lines of text in the right half, starting at y."""
        x = self.screen.get_width() // 2 + MARGIN
        for line in lines:
            self.screen.blit(font.render(line, True, color), (x, y))
            y += font.get_linesize()

    def error_box(self):
        """(top, bottom) of the error box: the top of the right half."""
        h = self.screen.get_height()
        return MARGIN, h * ERROR_BOX_FRACTION - MARGIN / 2

    def result_lines(self, result: ProgramResult):
        """Wrapped lines for the error box, trimmed to fit it.
        Computed once per result rather than every frame."""
        if self.result_cache is not None and self.result_cache[0] is result:
            return self.result_cache[1]
        font = self.error_font
        width = self.screen.get_width() // 2 - 2 * MARGIN
        top, bottom = self.error_box()
        head = wrap_text(font, result.summary, width)
        error = wrap_text(font, result.error or "", width)
        tail = wrap_text(font, "Press any button to continue", width)
        room = int((bottom - top) // font.get_linesize()) - len(head) - len(tail)
        # Keep the end of the error output, which is the most relevant.
        lines = head + fit_lines(error, room, keep_end=True) + tail
        self.result_cache = (result, lines)
        return lines

    def draw_result(self, result: ProgramResult):
        """Exit code and error output in dark red, in the error box above
        the info panel."""
        self.draw_lines(self.result_lines(result), self.error_font, ERROR_COLOR,
                        self.error_box()[0])

    def info_lines(self, program: Program, height):
        """Wrapped description (README.md or "Play <name>") for the info
        panel, trimmed to fit height pixels. Cached per program and height."""
        key = (program, int(height))
        lines = self.info_cache.get(key)
        if lines is None:
            width = self.screen.get_width() // 2 - 2 * MARGIN
            room = int(height // self.font.get_linesize())
            lines = fit_lines(wrap_text(self.font, program.description, width), room)
            self.info_cache[key] = lines
        return lines

    def draw_info(self, program: Program):
        """Description of the selected program in the right half, centred on
        the selection row. While an error is shown, it is limited to the
        space below the error box (mirrored above the centre)."""
        h = self.screen.get_height()
        top = MARGIN if self.result is None else self.error_box()[1] + MARGIN / 2
        lines = self.info_lines(program, h - 2 * top)
        y = max(top, (h - len(lines) * self.font.get_linesize()) / 2)
        self.draw_lines(lines, self.font, TEXT_COLOR, y)

    def draw(self):
        self.screen.fill(BG_COLOR)
        self.draw_list()
        if self.programs:
            self.draw_info(self.programs[self.selected])
        if self.result is not None:
            self.draw_result(self.result)
        if self.blackout > 0:
            overlay = pygame.Surface(self.screen.get_size())  # starts black
            overlay.set_alpha(round(255 * self.blackout))
            self.screen.blit(overlay, (0, 0))
        pygame.display.flip()

    # -- main loop ---------------------------------------------------------

    def run(self):
        self.open_display()
        while True:
            dt = self.clock.tick(FPS) / 1000
            actions = []
            for event in pygame.event.get():
                if is_quit(event):
                    return
                actions += self.input.handle(event)
            actions += self.input.update(dt)
            for action in actions:
                self.act(action)
                if action == SELECT:
                    break  # discard anything queued from before a launch
            self.update(dt)
            self.draw()
