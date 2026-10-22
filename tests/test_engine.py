import math
import unittest

from virtual_mouse.config import Settings
from virtual_mouse.engine import MouseEngine


class RecordingOutput:
    """Observe engine output without connecting to an actual desktop."""

    def __init__(self):
        self.moves = []
        self.buttons = []
        self.scrolls = []

    def move(self, dx, dy):
        self.moves.append((dx, dy))

    def button(self, button, pressed):
        self.buttons.append((button, pressed))

    def scroll(self, dy):
        self.scrolls.append(dy)

    @property
    def displacement(self):
        return (
            sum(dx for dx, _ in self.moves),
            sum(dy for _, dy in self.moves),
        )


def constant_speed_settings(speed=240.0, **changes):
    values = {"speed": speed, "initial_speed": speed, "acceleration": 0}
    values.update(changes)
    return Settings.from_mapping(values)


class MouseEngineTests(unittest.TestCase):
    def setUp(self):
        self.output = RecordingOutput()
        self.engine = MouseEngine(self.output, constant_speed_settings())
        self.engine.set_enabled(True)

    def test_disabled_engine_does_not_control_mouse(self):
        self.engine.set_enabled(False)

        for action in ("up", "click_left", "drag", "scroll_up"):
            self.engine.press(action)
        self.engine.tick(0.1)

        self.assertEqual(self.output.displacement, (0, 0))
        self.assertEqual(self.output.buttons, [])
        self.assertEqual(self.output.scrolls, [])
        self.assertFalse(self.engine.dragging)
        self.assertFalse(self.engine.moving)
        self.assertFalse(self.engine.needs_tick)

    def test_clicks_and_drag_do_not_require_periodic_ticks(self):
        self.assertFalse(self.engine.moving)
        self.assertFalse(self.engine.needs_tick)

        for action in ("click_left", "click_right", "click_middle", "drag"):
            with self.subTest(action=action):
                self.engine.press(action)

                self.assertFalse(self.engine.moving)
                self.assertFalse(self.engine.needs_tick)

        self.assertTrue(self.engine.dragging)

    def test_movement_needs_ticks_only_until_released(self):
        self.engine.press("right")

        self.assertTrue(self.engine.moving)
        self.assertTrue(self.engine.needs_tick)

        self.engine.release("right")

        self.assertFalse(self.engine.moving)
        self.assertFalse(self.engine.needs_tick)

    def test_direction_keeps_moving_until_released(self):
        self.engine.press("right")
        for _ in range(10):
            self.engine.tick(0.1)

        self.assertEqual(self.output.displacement, (240, 0))
        self.engine.release("right")
        self.engine.tick(0.1)
        self.assertEqual(self.output.displacement, (240, 0))

    def test_each_direction_has_correct_sign(self):
        for action, expected in (
            ("up", (0, -1)),
            ("down", (0, 1)),
            ("left", (-1, 0)),
            ("right", (1, 0)),
            ("up_left", (-1, -1)),
            ("up_right", (1, -1)),
            ("down_left", (-1, 1)),
            ("down_right", (1, 1)),
        ):
            with self.subTest(action=action):
                output = RecordingOutput()
                engine = MouseEngine(output, constant_speed_settings())
                engine.set_enabled(True)
                engine.press(action)
                engine.tick(0.1)
                dx, dy = output.displacement
                self.assertEqual((self.sign(dx), self.sign(dy)), expected)

    @staticmethod
    def sign(value):
        return (value > 0) - (value < 0)

    def test_opposite_directions_cancel(self):
        for action in ("left", "right", "up", "down"):
            self.engine.press(action)
        self.assertFalse(self.engine.moving)
        self.assertFalse(self.engine.needs_tick)
        self.engine.tick(0.1)

        self.assertEqual(self.output.displacement, (0, 0))

        self.engine.release("right")
        self.assertTrue(self.engine.moving)
        self.assertTrue(self.engine.needs_tick)
        self.engine.tick(0.1)
        self.assertEqual(self.output.displacement, (-24, 0))

    def test_diagonal_speed_matches_straight_speed(self):
        self.engine.press("right")
        self.engine.press("down")
        for _ in range(10):
            self.engine.tick(0.1)

        dx, dy = self.output.displacement
        self.assertAlmostEqual(dx, dy, delta=1)
        self.assertAlmostEqual(math.hypot(dx, dy), 240, delta=2)

    def test_fractional_pixels_are_accumulated(self):
        engine = MouseEngine(self.output, constant_speed_settings(speed=20))
        engine.set_enabled(True)
        engine.press("right")
        for _ in range(120):
            engine.tick(1 / 120)

        self.assertAlmostEqual(self.output.displacement[0], 20, delta=1)
        self.assertEqual(self.output.displacement[1], 0)
        self.assertTrue(all(isinstance(dx, int) for dx, _ in self.output.moves))

    def test_distance_is_independent_of_tick_frequency(self):
        displacements = []
        for frequency in (60, 120):
            output = RecordingOutput()
            engine = MouseEngine(output, constant_speed_settings())
            engine.set_enabled(True)
            engine.press("right")
            for _ in range(frequency):
                engine.tick(1 / frequency)
            displacements.append(output.displacement[0])

        self.assertAlmostEqual(displacements[0], displacements[1], delta=1)
        self.assertAlmostEqual(displacements[0], 240, delta=1)

    def test_precision_modifier_reduces_speed(self):
        self.engine.press("right")
        for _ in range(10):
            self.engine.tick(0.1, precision=True)

        self.assertAlmostEqual(self.output.displacement[0], 48, delta=1)
        self.assertEqual(self.output.displacement[1], 0)

    def test_acceleration_increases_speed(self):
        engine = MouseEngine(
            self.output,
            Settings.from_mapping(
                {"speed": 400, "initial_speed": 100, "acceleration": 1}
            ),
        )
        engine.set_enabled(True)
        engine.press("right")
        engine.tick(0.1)
        first_distance = self.output.displacement[0]
        for _ in range(10):
            engine.tick(0.1)
        before_last = self.output.displacement[0]
        engine.tick(0.1)
        last_distance = self.output.displacement[0] - before_last

        self.assertGreater(last_distance, first_distance)
        self.assertAlmostEqual(last_distance, 40, delta=1)

    def test_cancelled_movement_resets_acceleration_without_intermediate_tick(self):
        engine = MouseEngine(
            self.output,
            Settings.from_mapping(
                {"speed": 400, "initial_speed": 100, "acceleration": 1}
            ),
        )
        engine.set_enabled(True)
        engine.press("right")
        engine.tick(0.1)
        first_distance = self.output.displacement[0]
        for _ in range(10):
            engine.tick(0.1)

        engine.press("left")
        self.assertFalse(engine.needs_tick)
        engine.release("left")
        before_resume = self.output.displacement[0]
        engine.tick(0.1)

        self.assertEqual(self.output.displacement[0] - before_resume, first_distance)

    def test_clicks_use_expected_buttons_and_ignore_key_repeat(self):
        for action, button in (
            ("click_left", 1),
            ("click_right", 3),
            ("click_middle", 2),
        ):
            with self.subTest(action=action):
                self.output.buttons.clear()
                self.engine.press(action)
                self.engine.press(action)
                expected_press = [(button, True)] if button in (1, 3) else [(button, True), (button, False)]
                self.assertEqual(self.output.buttons, expected_press)
                self.engine.release(action)
                self.assertEqual(self.output.buttons, [(button, True), (button, False)])
                self.engine.press(action)
                self.engine.release(action)
                self.assertEqual(
                    self.output.buttons,
                    [(button, True), (button, False)] * 2,
                )

    def test_held_clicks_stay_down_without_periodic_ticks(self):
        for action, button in (("click_left", 1), ("click_right", 3)):
            with self.subTest(action=action):
                self.output.buttons.clear()
                self.engine.press(action)
                for _ in range(10):
                    self.engine.tick(0.1)
                    self.engine.press(action)
                self.assertEqual(self.output.buttons, [(button, True)])
                self.assertFalse(self.engine.needs_tick)
                self.engine.release(action)
                self.engine.release(action)
                self.assertEqual(self.output.buttons, [(button, True), (button, False)])

    def test_left_and_right_can_be_held_and_released_independently(self):
        self.engine.press("click_left")
        self.engine.press("click_right")
        self.engine.release("click_left")
        self.assertEqual(self.output.buttons, [(1, True), (3, True), (1, False)])
        self.engine.release("click_right")
        self.assertEqual(self.output.buttons[-1], (3, False))

    def test_drag_latch_keeps_left_down_after_releasing_five(self):
        self.engine.press("drag")
        self.engine.release("drag")
        self.engine.press("click_left")
        self.engine.release("click_left")
        self.assertEqual(self.output.buttons, [(1, True)])
        self.assertTrue(self.engine.dragging)
        self.engine.press("drag")
        self.assertEqual(self.output.buttons, [(1, True), (1, False)])

    def test_five_keeps_left_down_after_disabling_drag_latch(self):
        self.engine.press("click_left")
        self.engine.press("drag")
        self.engine.release("drag")
        self.engine.press("drag")
        self.assertFalse(self.engine.dragging)
        self.assertEqual(self.output.buttons, [(1, True)])
        self.engine.release("click_left")
        self.assertEqual(self.output.buttons, [(1, True), (1, False)])

    def test_disable_releases_all_button_sources_and_resets_state(self):
        self.engine.press("click_left")
        self.engine.press("click_right")
        self.engine.press("drag")
        self.engine.set_enabled(False)
        self.assertEqual(self.output.buttons, [(1, True), (3, True), (1, False), (3, False)])
        self.engine.set_enabled(True)
        self.engine.release("click_left")
        self.engine.release("click_right")
        self.assertEqual(len(self.output.buttons), 4)
        self.engine.press("click_right")
        self.engine.release("click_right")
        self.assertEqual(self.output.buttons[-2:], [(3, True), (3, False)])

    def test_stop_releases_both_held_buttons(self):
        self.engine.press("click_left")
        self.engine.press("click_right")
        self.engine.stop()
        self.engine.stop()
        self.assertEqual(self.output.buttons, [(1, True), (3, True), (1, False), (3, False)])

    def test_drag_toggles_only_on_new_presses(self):
        self.engine.press("drag")
        self.engine.press("drag")
        self.engine.release("drag")

        self.assertTrue(self.engine.dragging)
        self.assertEqual(self.output.buttons, [(1, True)])

        self.engine.press("drag")

        self.assertFalse(self.engine.dragging)
        self.assertEqual(self.output.buttons, [(1, True), (1, False)])

    def test_disable_releases_drag_and_clears_movement(self):
        self.engine.press("drag")
        self.engine.press("right")
        self.engine.set_enabled(False)
        self.engine.set_enabled(True)
        self.engine.tick(0.1)

        self.assertFalse(self.engine.dragging)
        self.assertEqual(self.output.buttons, [(1, True), (1, False)])
        self.assertEqual(self.output.displacement, (0, 0))

    def test_stop_releases_drag_and_clears_movement(self):
        self.engine.press("drag")
        self.engine.press("right")
        self.engine.stop()
        self.engine.tick(0.1)

        self.assertFalse(self.engine.dragging)
        self.assertEqual(self.output.buttons, [(1, True), (1, False)])
        self.assertEqual(self.output.displacement, (0, 0))

    def test_scroll_is_immediate_and_repeats_while_held(self):
        self.engine.press("scroll_up")
        self.engine.press("scroll_up")
        self.assertEqual(self.output.scrolls, [1])

        for _ in range(6):
            self.engine.tick(0.05)
        self.assertGreaterEqual(len(self.output.scrolls), 3)
        self.assertTrue(all(step == 1 for step in self.output.scrolls))

        self.engine.release("scroll_up")
        count = len(self.output.scrolls)
        self.engine.tick(0.2)
        self.assertEqual(len(self.output.scrolls), count)

    def test_scroll_down_uses_negative_direction(self):
        self.engine.press("scroll_down")
        self.assertEqual(self.output.scrolls, [-1])

    def test_opposite_scroll_inputs_suspend_periodic_ticks_until_released(self):
        self.engine.press("scroll_up")
        self.assertTrue(self.engine.needs_tick)
        self.assertFalse(self.engine.moving)

        self.engine.press("scroll_down")
        count = len(self.output.scrolls)
        self.assertFalse(self.engine.needs_tick)
        self.assertFalse(self.engine.moving)
        self.engine.tick(0.1)
        self.assertEqual(len(self.output.scrolls), count)

        self.engine.release("scroll_down")
        self.assertTrue(self.engine.needs_tick)
        self.assertFalse(self.engine.moving)
        for _ in range(2):
            self.engine.tick(0.1)

        self.assertGreater(len(self.output.scrolls), count)
        self.assertTrue(all(step == 1 for step in self.output.scrolls[count:]))
        self.engine.release("scroll_up")
        self.assertFalse(self.engine.needs_tick)

    def test_settings_update_changes_speed(self):
        self.engine.press("right")
        self.engine.tick(0.1)
        before_update = self.output.displacement[0]

        self.engine.update_settings(constant_speed_settings(speed=480))
        self.engine.tick(0.1)

        self.assertEqual(before_update, 24)
        self.assertEqual(self.output.displacement[0] - before_update, 48)


if __name__ == "__main__":
    unittest.main()
