"""The launcher screen: program list, launching, and result display."""

import pygame

from controls import DOWN, SELECT, UP, Input, is_quit
from program import find_programs, run_program

BG_COLOR = (240, 240, 240)
TEXT_COLOR = (10, 10, 10)
MARGIN = 40


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
        self.result = None  # (name, exit_code, error_text) after a failed run
        self.input = Input()

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
        code, error = run_program(self.config["python"], script)
        self.open_display()
        self.programs = find_programs(self.config["script_dir"])
        self.selected = min(self.selected, max(len(self.programs) - 1, 0))
        self.scroll = float(self.selected)
        if error is not None:
            self.result = (name, code, error)

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

    def draw_list(self):
        """Program list in the left half, selection row fixed at the vertical
        centre, fading out towards the top and bottom edges."""
        w, h = self.screen.get_size()
        half_h = h / 2
        line_h = self.font.get_linesize()
        marker = self.font.render("> ", True, TEXT_COLOR)
        text_x = MARGIN + marker.get_width()

        if not self.programs:
            msg = f"No programs found in {self.config['script_dir']}"
            for i, line in enumerate(wrap_text(self.font, msg, w // 2 - 2 * MARGIN)):
                self.screen.blit(self.font.render(line, True, TEXT_COLOR),
                                 (MARGIN, half_h - line_h / 2 + i * line_h))
            return

        self.screen.set_clip(pygame.Rect(0, 0, w // 2, h))
        self.screen.blit(marker, (MARGIN, half_h - line_h / 2))
        for i, (name, _) in enumerate(self.programs):
            centre = half_h + (i - self.scroll) * line_h
            alpha = 1 - abs(centre - half_h) / half_h
            if alpha <= 0:
                continue
            surf = self.font.render(name, True, TEXT_COLOR)
            surf.set_alpha(round(255 * alpha))
            self.screen.blit(surf, (text_x, centre - line_h / 2))
        self.screen.set_clip(None)

    def draw_result(self):
        """Exit code and error output in the right half."""
        name, code, error = self.result
        w, h = self.screen.get_size()
        width = w // 2 - 2 * MARGIN
        lines = wrap_text(self.font, f"'{name}' exited with code {code}", width)
        lines += [""] + wrap_text(self.font, error, width)
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
            self.draw_result()
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
