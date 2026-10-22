import contextlib
from dataclasses import asdict
import io
import json
import os
from pathlib import Path
import signal
import tempfile
import threading
import unittest
from unittest import mock

from virtual_mouse import app
from virtual_mouse.config import Settings


class CommandLineTests(unittest.TestCase):
    def setUp(self):
        control = mock.patch.object(app, "ControlServer")
        control.start()
        self.addCleanup(control.stop)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "config.json"
        self.stdout = io.StringIO()
        self.stderr = io.StringIO()

    def run_cli(self, *arguments):
        with contextlib.redirect_stdout(self.stdout), contextlib.redirect_stderr(self.stderr):
            return app.main(["--config", str(self.path), *arguments])

    def test_print_defaults_does_not_connect_or_create_configuration(self):
        with mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli("--print-default-config")

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.stdout.getvalue()), asdict(Settings()))
        self.assertFalse(self.path.exists())
        backend.assert_not_called()

    def test_write_defaults_creates_configuration_without_connecting(self):
        self.path = self.path.parent / "nested" / "config.json"
        with mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli("--write-config")

        self.assertEqual(result, 0)
        self.assertEqual(json.loads(self.path.read_text()), asdict(Settings()))
        backend.assert_not_called()

    def test_write_defaults_refuses_to_overwrite_existing_file(self):
        contents = '{"speed": 1111}\n'
        self.path.write_text(contents, encoding="utf-8")
        with mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli("--write-config")

        self.assertEqual(result, 1)
        self.assertEqual(self.path.read_text(), contents)
        self.assertIn("já existe", self.stderr.getvalue())
        backend.assert_not_called()

    def test_write_defaults_preserves_file_created_during_write(self):
        original_save = app.save_settings
        contents = '{"speed": 1300}\n'

        def concurrent_save(settings, path, **kwargs):
            path.write_text(contents, encoding="utf-8")
            return original_save(settings, path, **kwargs)

        with mock.patch.object(app, "save_settings", side_effect=concurrent_save), mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli("--write-config")

        self.assertEqual(result, 1)
        self.assertEqual(self.path.read_text(), contents)
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])
        backend.assert_not_called()

    def test_invalid_configuration_fails_before_connecting(self):
        self.path.write_text('{"speed": -1}', encoding="utf-8")
        with mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli()

        self.assertEqual(result, 1)
        self.assertIn("Erro:", self.stderr.getvalue())
        self.assertIn("speed", self.stderr.getvalue())
        backend.assert_not_called()

    def test_check_does_not_reserve_hotkeys_or_take_instance_lock(self):
        with mock.patch.object(app, "X11Backend") as backend, mock.patch.object(app, "InstanceLock") as lock:
            result = self.run_cli("--check")

        self.assertEqual(result, 0)
        backend.assert_called_once_with(
            toggle_hotkey=Settings().toggle_hotkey,
            quit_hotkey=Settings().quit_hotkey,
            reserve_hotkeys=False,
        )
        backend.return_value.__enter__.assert_called_once()
        backend.return_value.__exit__.assert_called_once()
        lock.assert_not_called()

    def test_backend_error_is_reported_without_traceback(self):
        with mock.patch.object(app, "X11Backend", side_effect=app.X11Error("Sem sessão X11")):
            result = self.run_cli("--check")

        self.assertEqual(result, 1)
        self.assertIn("Sem sessão X11", self.stderr.getvalue())
        self.assertNotIn("Traceback", self.stderr.getvalue())

    def test_enabled_flag_overrides_settings_and_shutdown_restores_signals(self):
        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        previous = {sig: signal.getsignal(sig) for sig in signals}
        with mock.patch.object(app, "X11Backend") as backend, mock.patch.object(app, "Application") as application, mock.patch.object(app, "InstanceLock"):
            result = self.run_cli("--enabled")

        self.assertEqual(result, 0)
        called_backend, settings = application.call_args.args
        self.assertIs(called_backend, backend.return_value)
        self.assertTrue(settings.start_enabled)
        application.return_value.run.assert_called_once()
        application.return_value.close.assert_called_once()
        self.assertEqual({sig: signal.getsignal(sig) for sig in signals}, previous)

    def test_application_failure_still_closes_backend(self):
        with mock.patch.object(app, "X11Backend") as backend, mock.patch.object(app, "Application", side_effect=app.X11Error("Atalho indisponível")), mock.patch.object(app, "InstanceLock"):
            result = self.run_cli()

        self.assertEqual(result, 1)
        backend.return_value.close.assert_called_once()

    def test_loop_failure_still_closes_application_and_restores_signals(self):
        signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
        previous = {sig: signal.getsignal(sig) for sig in signals}
        with mock.patch.object(app, "X11Backend"), mock.patch.object(app, "Application") as application, mock.patch.object(app, "InstanceLock"):
            application.return_value.run.side_effect = app.X11Error("Falha de entrada")
            result = self.run_cli()

        self.assertEqual(result, 1)
        application.return_value.close.assert_called_once()
        self.assertEqual({sig: signal.getsignal(sig) for sig in signals}, previous)

    def test_headless_legacy_argument_runs_the_default_terminal_loop(self):
        with mock.patch.object(app, "X11Backend"), mock.patch.object(app, "Application") as application, mock.patch.object(app, "InstanceLock"):
            result = self.run_cli("--headless")

        self.assertEqual(result, 0)
        application.return_value.run.assert_called_once()
        application.return_value.close.assert_called_once()
        self.assertEqual(self.stderr.getvalue(), "")

    def test_signal_requests_stop_and_restores_previous_handler(self):
        previous = signal.getsignal(signal.SIGTERM)
        with mock.patch.object(app, "X11Backend"), mock.patch.object(app, "Application") as application, mock.patch.object(app, "InstanceLock"):
            application.return_value.run.side_effect = lambda: signal.raise_signal(signal.SIGTERM)
            result = self.run_cli()

        self.assertEqual(result, 0)
        application.return_value.request_stop.assert_called_once_with()
        application.return_value.close.assert_called_once()
        self.assertEqual(signal.getsignal(signal.SIGTERM), previous)

    def test_toggle_existing_instance_does_not_open_x11_or_read_settings(self):
        self.path.write_text("JSON inválido")
        with mock.patch.object(app, "send_toggle", return_value=True), mock.patch.object(app, "X11Backend") as backend, mock.patch.object(app, "InstanceLock") as lock:
            result = self.run_cli("--toggle")
        self.assertEqual(result, 0)
        backend.assert_not_called()
        lock.assert_not_called()

    def test_toggle_starts_enabled_when_no_instance_exists(self):
        with mock.patch.object(app, "send_toggle", return_value=False), mock.patch.object(app, "X11Backend"), mock.patch.object(app, "Application") as application, mock.patch.object(app, "InstanceLock"):
            result = self.run_cli("--toggle")
        self.assertEqual(result, 0)
        self.assertTrue(application.call_args.args[1].start_enabled)
        application.return_value.run.assert_called_once()

    def test_simultaneous_start_retries_toggle_instead_of_starting_twice(self):
        with mock.patch.object(app, "send_toggle", side_effect=[False, False, True]), mock.patch.object(app.time, "sleep"), mock.patch.object(app, "InstanceLock", side_effect=app.AlreadyRunningError("já está aberto")), mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli("--toggle")
        self.assertEqual(result, 0)
        backend.assert_not_called()

    def test_toggle_error_is_reported_without_starting_another_instance(self):
        with mock.patch.object(app, "send_toggle", side_effect=ValueError("Atalho indisponível")), mock.patch.object(app, "X11Backend") as backend:
            result = self.run_cli("--toggle")
        self.assertEqual(result, 1)
        self.assertIn("Atalho indisponível", self.stderr.getvalue())
        backend.assert_not_called()


class InstanceLockTests(unittest.TestCase):
    def test_second_instance_is_rejected_and_lock_is_released(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(app.tempfile, "gettempdir", return_value=directory), mock.patch.dict(os.environ, {"DISPLAY": ":virtual-mouse-unittest"}):
            with app.InstanceLock():
                with self.assertRaisesRegex(app.X11Error, "já está aberto"):
                    with app.InstanceLock():
                        self.fail("Uma segunda instância não pode adquirir a mesma trava.")
            with app.InstanceLock():
                pass

    def test_independent_displays_can_run_concurrently(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(app.tempfile, "gettempdir", return_value=directory), mock.patch.dict(os.environ, {"DISPLAY": ":virtual-mouse-first"}):
            with app.InstanceLock():
                with mock.patch.dict(os.environ, {"DISPLAY": ":virtual-mouse-second"}):
                    with app.InstanceLock():
                        pass

    def test_lock_is_released_when_application_raises(self):
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(app.tempfile, "gettempdir", return_value=directory), mock.patch.dict(os.environ, {"DISPLAY": ":virtual-mouse-unittest"}):
            with self.assertRaisesRegex(RuntimeError, "falha"):
                with app.InstanceLock():
                    raise RuntimeError("falha")
            with app.InstanceLock():
                pass


class ApplicationLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.backend = mock.Mock()
        self.backend.events.return_value = []
        self.backend.pending.return_value = False
        self.backend.precision_pressed.return_value = False
        self.application = app.Application(self.backend, Settings())

    def test_start_enabled_activates_backend_and_engine(self):
        with contextlib.redirect_stdout(io.StringIO()):
            application = app.Application(
                self.backend, Settings(start_enabled=True)
            )

        self.assertTrue(application.engine.enabled)
        self.backend.set_enabled.assert_called_once_with(True)

    def test_activation_failure_leaves_engine_disabled(self):
        self.backend.set_enabled.side_effect = app.X11Error("Tecla ocupada")

        with self.assertRaises(app.X11Error):
            self.application.set_enabled(True)

        self.assertFalse(self.application.engine.enabled)

    def test_quit_event_stops_loop_before_movement_tick(self):
        self.backend.events.return_value = [("quit", None), ("press", "right")]
        with mock.patch.object(self.application.engine, "tick") as tick:
            self.application.pump()

        self.assertFalse(self.application.running)
        tick.assert_not_called()

    def test_idle_pump_does_not_tick_or_query_pointer(self):
        with mock.patch.object(self.application.engine, "tick") as tick:
            self.application.pump()
            with contextlib.redirect_stdout(io.StringIO()):
                self.application.set_enabled(True)
            self.application.pump()
            self.application.engine.press("drag")
            self.application.pump()

        tick.assert_not_called()
        self.backend.precision_pressed.assert_not_called()

    def test_movement_pump_ticks_and_checks_precision(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.application.set_enabled(True)
        self.backend.events.return_value = [("press", "right")]
        with mock.patch.object(self.application.engine, "tick") as tick:
            self.application.pump()

        tick.assert_called_once()
        self.backend.precision_pressed.assert_called_once_with()

    def test_scroll_pump_ticks_without_querying_pointer(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.application.set_enabled(True)
        self.backend.events.return_value = [("press", "scroll_up")]
        with mock.patch.object(self.application.engine, "tick") as tick:
            self.application.pump()

        tick.assert_called_once()
        self.backend.precision_pressed.assert_not_called()

    def first_wait(self):
        calls = []

        def stop_after_wait(*args):
            calls.append(args)
            self.application.request_stop()
            return [], [], []

        with mock.patch.object(app.select, "select", side_effect=stop_after_wait), contextlib.redirect_stdout(io.StringIO()):
            self.application.run()
        self.assertEqual(len(calls), 1)
        return calls[0]

    def test_disabled_loop_waits_for_events_without_polling(self):
        with mock.patch.object(self.application.engine, "tick") as tick:
            readers, writers, errors, timeout = self.first_wait()

        self.assertIn(self.backend.fd, readers)
        self.assertEqual(writers, [])
        self.assertEqual(errors, [])
        self.assertIsNone(timeout)
        tick.assert_not_called()
        self.backend.precision_pressed.assert_not_called()

    def test_enabled_idle_loop_waits_without_polling(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.application.set_enabled(True)

        self.assertIsNone(self.first_wait()[3])
        self.backend.precision_pressed.assert_not_called()

    def test_control_socket_wakes_idle_loop_and_toggles(self):
        control = mock.Mock()
        control.fileno.return_value = 999
        self.application.control = control

        def handle(toggle):
            self.assertTrue(toggle())
            self.application.request_stop()

        control.handle.side_effect = handle
        with mock.patch.object(app.select, "select", return_value=([999], [], [])) as wait, contextlib.redirect_stdout(io.StringIO()):
            self.application.run()
        self.assertIsNone(wait.call_args.args[3])
        self.assertIn(999, wait.call_args.args[0])
        control.handle.assert_called_once()
        self.backend.set_enabled.assert_called_once_with(True)

    def test_opposite_directions_wait_without_polling(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.application.set_enabled(True)
        self.backend.events.return_value = [("press", "left"), ("press", "right")]

        self.assertIsNone(self.first_wait()[3])
        self.backend.precision_pressed.assert_not_called()

    def test_only_movement_and_scrolling_schedule_periodic_ticks(self):
        for action in ("right", "scroll_up"):
            with self.subTest(action=action):
                self.application.running = True
                self.application.engine.stop()
                with contextlib.redirect_stdout(io.StringIO()):
                    self.application.set_enabled(True)
                self.backend.events.return_value = [("press", action)]

                timeout = self.first_wait()[3]

                self.assertIsNotNone(timeout)
                self.assertGreaterEqual(timeout, 0)
                self.assertLessEqual(timeout, 1 / self.application.settings.tick_hz)

    def test_buffered_x11_events_are_consumed_before_waiting(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.application.set_enabled(True)
        self.backend.events.side_effect = [[], [("press", "right")]]
        self.backend.pending.side_effect = [True, False]

        timeout = self.first_wait()[3]

        self.assertEqual(self.backend.events.call_count, 2)
        self.assertIsNotNone(timeout)
        self.backend.precision_pressed.assert_called_once_with()

    def test_stop_wakes_indefinite_wait_without_x11_activity(self):
        backend_read, backend_write = os.pipe()
        self.addCleanup(os.close, backend_read)
        self.addCleanup(os.close, backend_write)
        self.backend.fd = backend_read
        entered_wait = threading.Event()
        errors = []
        waits = []
        real_select = app.select.select

        def observed_select(readers, writers, exceptions, timeout):
            waits.append(timeout)
            entered_wait.set()
            return real_select(readers, writers, exceptions, timeout)

        def run():
            try:
                self.application.run()
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=run, daemon=True)
        with mock.patch.object(app.select, "select", side_effect=observed_select), contextlib.redirect_stdout(io.StringIO()):
            worker.start()
            try:
                self.assertTrue(entered_wait.wait(2), "O loop não chegou à espera de eventos.")
                self.application.request_stop()
                worker.join(2)
                self.assertFalse(worker.is_alive(), "Encerrar deve acordar a espera infinita.")
            finally:
                self.application.request_stop()
                worker.join(2)

        self.assertEqual(errors, [])
        self.assertEqual(waits, [None])
        self.backend.precision_pressed.assert_not_called()

    def test_close_releases_drag_before_closing_backend(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.application.set_enabled(True)
        self.application.engine.press("drag")
        self.backend.reset_mock()

        self.application.close()

        self.assertEqual(
            self.backend.mock_calls,
            [mock.call.button(1, False), mock.call.close()],
        )
        self.assertFalse(self.application.engine.enabled)


if __name__ == "__main__":
    unittest.main()
