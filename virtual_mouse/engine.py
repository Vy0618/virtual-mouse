"""Movimento e gestos; não depende de X11 nem de tempo real nos testes."""

import math

from .config import Settings


DIRECTIONS = {
    "up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0),
    "up_left": (-1, -1), "up_right": (1, -1),
    "down_left": (-1, 1), "down_right": (1, 1),
}
CLICKS = {"click_left": 1, "click_middle": 2, "click_middle_decimal": 2, "click_right": 3}


class MouseEngine:
    def __init__(self, output, settings: Settings):
        self.output = output
        self.settings = settings
        self.enabled = False
        self.dragging = False
        self._held = set()
        self._button_sources = {1: set(), 3: set()}
        self._elapsed = 0.0
        self._fraction = [0.0, 0.0]
        self._scroll_elapsed = 0.0
        self._direction = (0, 0)
        self._unit_direction = (0.0, 0.0)
        self._scroll_direction = 0

    @property
    def moving(self):
        return self.enabled and self._direction != (0, 0)

    @property
    def needs_tick(self):
        return self.enabled and (self._direction != (0, 0) or self._scroll_direction != 0)

    def update_settings(self, settings):
        self.settings = settings

    def set_enabled(self, enabled):
        if not enabled:
            self.stop()
        self.enabled = bool(enabled)

    def press(self, action):
        if not self.enabled or action in self._held:
            return
        self._held.add(action)
        self._refresh_inputs()
        if action in CLICKS:
            button = CLICKS[action]
            if button in self._button_sources:
                self._set_button_source(button, action, True)
            else:
                self.output.button(button, True)
                self.output.button(button, False)
        elif action == "drag":
            self.dragging = not self.dragging
            self._set_button_source(1, "drag", self.dragging)
        elif action in ("scroll_up", "scroll_down"):
            self.output.scroll(1 if action == "scroll_up" else -1)
            self._scroll_elapsed = 0.0

    def release(self, action):
        if action not in self._held:
            return
        self._held.discard(action)
        button = CLICKS.get(action)
        if button in self._button_sources:
            self._set_button_source(button, action, False)
        self._refresh_inputs()

    def _set_button_source(self, button, source, pressed):
        sources = self._button_sources[button]
        was_pressed = bool(sources)
        if pressed:
            sources.add(source)
        else:
            sources.discard(source)
        if bool(sources) != was_pressed:
            self.output.button(button, bool(sources))

    def _refresh_inputs(self):
        x = y = 0
        for action in self._held:
            if action in DIRECTIONS:
                dx, dy = DIRECTIONS[action]
                x += dx
                y += dy
        direction = ((x > 0) - (x < 0), (y > 0) - (y < 0))
        if direction != self._direction:
            self._reset_motion()
            self._direction = direction
            length = math.hypot(*direction)
            if length:
                self._unit_direction = (direction[0] / length, direction[1] / length)
        scroll = int("scroll_up" in self._held) - int("scroll_down" in self._held)
        if scroll != self._scroll_direction:
            self._scroll_elapsed = 0.0
        self._scroll_direction = scroll

    def _reset_motion(self):
        self._elapsed = 0.0
        self._fraction = [0.0, 0.0]
        self._direction = (0, 0)
        self._unit_direction = (0.0, 0.0)

    def tick(self, dt, precision=False):
        if not self.needs_tick:
            return
        # Não saltar pela tela após uma pausa do processo/suspensão.
        dt = min(max(dt, 0.0), 0.1)
        if self.moving:
            s = self.settings
            if s.acceleration == 0:
                distance = s.speed * dt
            else:
                # Integral da rampa linear, calculada sem alocar funções por frame.
                start = min(self._elapsed, s.acceleration)
                ramp = min(dt, s.acceleration - start)
                average = s.initial_speed + (s.speed - s.initial_speed) * (start + ramp / 2) / s.acceleration
                distance = average * ramp + s.speed * (dt - ramp)
                self._elapsed = min(start + dt, s.acceleration)
            distance *= s.precision_factor if precision else 1
            offsets = []
            for i, component in enumerate(self._unit_direction):
                self._fraction[i] += component * distance
                whole = math.trunc(self._fraction[i])
                self._fraction[i] -= whole
                offsets.append(whole)
            if any(offsets):
                self.output.move(*offsets)
        scroll = self._scroll_direction
        if scroll:
            self._scroll_elapsed += dt
            while self._scroll_elapsed + 1e-12 >= self.settings.scroll_interval:
                self.output.scroll(scroll)
                self._scroll_elapsed -= self.settings.scroll_interval
        else:
            self._scroll_elapsed = 0.0

    def stop(self):
        for button, sources in self._button_sources.items():
            if sources:
                self.output.button(button, False)
                sources.clear()
        self.dragging = False
        self._held.clear()
        self._reset_motion()
        self._scroll_elapsed = 0.0
        self._scroll_direction = 0
