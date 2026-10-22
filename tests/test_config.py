import dataclasses
import json
import tempfile
import unittest
from pathlib import Path

from virtual_mouse.config import Settings, load_settings, save_settings


class SettingsTests(unittest.TestCase):
    def test_defaults_are_valid_and_immutable(self):
        settings = Settings.from_mapping({})

        self.assertEqual(settings, Settings())
        self.assertEqual(settings.speed, 700.0)
        self.assertEqual(settings.initial_speed, 160.0)
        self.assertFalse(settings.start_enabled)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            settings.speed = 800.0

    def test_partial_configuration_preserves_other_defaults(self):
        settings = Settings.from_mapping(
            {"speed": 900, "precision_factor": 0.3, "start_enabled": True}
        )

        self.assertEqual(settings.speed, 900)
        self.assertEqual(settings.precision_factor, 0.3)
        self.assertTrue(settings.start_enabled)
        self.assertEqual(settings.toggle_hotkey, Settings().toggle_hotkey)

    def test_supported_range_boundaries(self):
        for changes in (
            {"speed": 20, "initial_speed": 20},
            {"speed": 5000},
            {"acceleration": 0},
            {"acceleration": 10},
            {"precision_factor": 1},
            {"scroll_interval": 0.02},
            {"scroll_interval": 2},
            {"tick_hz": 30},
            {"tick_hz": 240},
        ):
            with self.subTest(changes=changes):
                Settings.from_mapping(changes)

    def test_invalid_numeric_values_are_rejected(self):
        invalid = {
            "speed": (0, 19, 5001, float("inf"), float("nan")),
            "initial_speed": (0, -1, 701, float("inf"), float("nan")),
            "acceleration": (-0.1, 10.1, float("inf"), float("nan")),
            "precision_factor": (0, -0.1, 1.1, float("inf"), float("nan")),
            "scroll_interval": (0, 0.019, 2.1, float("inf"), float("nan")),
            "tick_hz": (29, 241, 60.5),
        }
        for name, values in invalid.items():
            for value in values:
                with self.subTest(name=name, value=value):
                    with self.assertRaises(ValueError):
                        Settings.from_mapping({name: value})

    def test_initial_speed_cannot_exceed_configured_speed(self):
        with self.assertRaises(ValueError):
            Settings.from_mapping({"speed": 100, "initial_speed": 101})

    def test_incorrect_types_are_rejected(self):
        for name, value in (
            ("speed", "700"),
            ("speed", True),
            ("initial_speed", False),
            ("acceleration", "1.4"),
            ("precision_factor", None),
            ("scroll_interval", []),
            ("tick_hz", True),
            ("start_enabled", 1),
            ("start_enabled", "false"),
            ("toggle_hotkey", 123),
            ("quit_hotkey", None),
        ):
            with self.subTest(name=name, value=value):
                with self.assertRaises(ValueError):
                    Settings.from_mapping({name: value})

    def test_unknown_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            Settings.from_mapping({"speeed": 900})

    def test_empty_or_conflicting_hotkeys_are_rejected(self):
        for changes in (
            {"toggle_hotkey": ""},
            {"quit_hotkey": "   "},
            {"toggle_hotkey": "Ctrl+Alt+m", "quit_hotkey": "Ctrl+Alt+m"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    Settings.from_mapping(changes)


class SettingsFileTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.path = Path(self.tempdir.name) / "settings.json"

    def test_missing_file_returns_defaults(self):
        self.assertEqual(load_settings(self.path), Settings())

    def test_save_and_load_round_trip(self):
        settings = Settings.from_mapping(
            {
                "speed": 1100,
                "initial_speed": 200,
                "tick_hz": 90,
                "toggle_hotkey": "Ctrl+Alt+k",
                "start_enabled": True,
            }
        )

        save_settings(settings, self.path)

        self.assertEqual(load_settings(self.path), settings)
        self.assertEqual(json.loads(self.path.read_text())["speed"], 1100)

    def test_invalid_json_raises_value_error(self):
        self.path.write_text('{"speed": ', encoding="utf-8")

        with self.assertRaises(ValueError):
            load_settings(self.path)

    def test_exclusive_save_refuses_existing_file_and_removes_temporary_file(self):
        contents = '{"speed": 1100}\n'
        self.path.write_text(contents, encoding="utf-8")

        with self.assertRaises(FileExistsError):
            save_settings(Settings(), self.path, overwrite=False)

        self.assertEqual(self.path.read_text(), contents)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_normal_save_updates_existing_configuration(self):
        save_settings(Settings(), self.path)
        updated = Settings.from_mapping({"speed": 1200})

        save_settings(updated, self.path)

        self.assertEqual(load_settings(self.path), updated)

    def test_non_object_json_is_rejected(self):
        for contents in ("[]", "null", '"settings"', "42"):
            with self.subTest(contents=contents):
                self.path.write_text(contents, encoding="utf-8")
                with self.assertRaises(ValueError):
                    load_settings(self.path)

    def test_file_values_are_validated(self):
        self.path.write_text('{"speed": -10}', encoding="utf-8")

        with self.assertRaises(ValueError):
            load_settings(self.path)


if __name__ == "__main__":
    unittest.main()
