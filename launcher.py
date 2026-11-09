"""The launcher screen: program list, launching, and result display."""

import math

import pygame

from controls import DOWN, SELECT, UP, Input, is_quit
from program import ProgramResult, find_programs, run_program

BG_COLOR = (240, 240, 240)
TEXT_COLOR = (10, 10, 10)
MARGIN = 40
SELECTION_ALPHA = 40  # opacity (0-255) of the box behind the selection
DEPTH = 0.15  # how quickly rows shrink with distance from the selection


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
            # Hard-break words that are wider than the line on their own.
            while font.size(word)[0] > width and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and font.size(word[:cut])[0] > width:
                    cut -= 1
                out.append(word[:cut])
                word = word[cut:]
            line = word
        out.append(line)
    return out


class Launcher:
    def __init__(self, config):
        self.config = config
        self.programs = find_programs(config["script_dir"])
        self.selected = 0
        self.scroll = 0.0  # list position in rows; animates towards selected
        self.result: ProgramResult | None = None  # set after a failed run
        self.input = Input()
        self.name_surfaces: dict[str, pygame.Surface] = {}  # rendered names

    # Created in open_display() and recreated after every launched program.
    screen: pygame.Surface
    font: pygame.font.Font

    # -- display lifecycle -------------------------------------------------

    def open_display(self):
        pygame.display.init()
        pygame.joystick.init()
        pygame.font.init()
        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        pygame.display.set_caption("Launcher")
        pygame.mouse.set_visible(False)
        self.font = pygame.font.Font(None, self.config["font_size"])
        self.name_surfaces.clear()
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
        name, script = self.programs[self.selected]
        self.close_display()
        result = run_program(name, self.config["python"], script)
        self.open_display()
        self.programs = find_programs(self.config["script_dir"])
        self.selected = min(self.selected, max(len(self.programs) - 1, 0))
        self.scroll = float(self.selected)
        if result.failed:
            self.result = result

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
        """Slide the list towards the selection at scroll_speed rows/sec."""
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
            msg = f"No programs found in {self.config['script_dir']}"
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

        for i, (name, _) in enumerate(self.programs):
            d = i - self.scroll
            if not visible(d):
                continue
            centre = row_centre(d)
            surf = self.name_surface(name)
            scale = depth_scale(d)
            if scale < 0.999:
                surf = pygame.transform.smoothscale_by(surf, scale)
            surf.set_alpha(round(255 * fade(centre)))
            # Left-aligned, so rows shrink towards the left edge.
            self.screen.blit(surf, (text_x, centre - surf.get_height() / 2))
        self.screen.set_clip(None)

    def draw_result(self, result: ProgramResult):
        """Exit code and error output in the right half."""
        w, h = self.screen.get_size()
        width = w // 2 - 2 * MARGIN
        lines = wrap_text(self.font, result.summary, width)
        lines += [""] + wrap_text(self.font, result.error or "", width)
        lines += [""] + wrap_text(self.font, "Press any button to continue", width)
        line_h = self.font.get_linesize()
        y = max(MARGIN, (h - len(lines) * line_h) / 2)
        for line in lines:
            self.screen.blit(self.font.render(line, True, TEXT_COLOR), (w // 2 + MARGIN, y))
            y += line_h

    def draw(self):
        self.screen.fill(BG_COLOR)
        self.draw_list()
        if self.result is not None:
            self.draw_result(self.result)
        pygame.display.flip()

    # -- main loop ---------------------------------------------------------

    def run(self):
        self.open_display()
        clock = pygame.time.Clock()
        while True:
            dt = clock.tick(60) / 1000
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
