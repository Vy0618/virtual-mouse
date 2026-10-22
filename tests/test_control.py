import contextlib
import io
import os
import select
import socket
import threading
import unittest
from unittest import mock
import uuid

from virtual_mouse import control


class ControlTests(unittest.TestCase):
    def setUp(self):
        address = mock.patch.object(control, "control_address", return_value=f"\0virtual-mouse-test-{uuid.uuid4().hex}")
        address.start()
        self.addCleanup(address.stop)

    def test_missing_server_returns_false(self):
        self.assertFalse(control.send_toggle())

    def test_toggle_confirmation_and_address_cleanup(self):
        errors = []
        calls = []
        with control.ControlServer() as server:
            def serve():
                try:
                    for enabled in (False, True):
                        ready, _, _ = select.select([server.fileno()], [], [], 2)
                        if not ready:
                            raise AssertionError("O cliente não enviou o comando.")
                        server.handle(lambda: calls.append(enabled) or enabled)
                except BaseException as exc:
                    errors.append(exc)
            worker = threading.Thread(target=serve, daemon=True)
            worker.start()
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertTrue(control.send_toggle())
                self.assertTrue(control.send_toggle())
            worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertEqual(errors, [])
            self.assertEqual(calls, [False, True])
            self.assertIn("desativado", output.getvalue())
            self.assertIn("ATIVADO", output.getvalue())
        self.assertFalse(control.send_toggle())

    def handle_command(self, command, toggle):
        client, accepted = socket.socketpair()
        self.addCleanup(client.close)
        self.addCleanup(accepted.close)
        server = control.ControlServer()
        server.socket = mock.Mock()
        server.socket.accept.return_value = (accepted, None)
        client.sendall(command)
        server.handle(toggle)
        return client.recv(2048).decode()

    def test_invalid_command_does_not_toggle(self):
        toggle = mock.Mock()
        self.assertIn("comando desconhecido", self.handle_command(b"stop\n", toggle))
        toggle.assert_not_called()

    def test_callback_error_is_returned_to_client(self):
        toggle = mock.Mock(side_effect=RuntimeError("numpad ocupado"))
        self.assertIn("ERRO: numpad ocupado", self.handle_command(b"toggle\n", toggle))

    def test_peer_credentials_check_current_user(self):
        client, server = socket.socketpair()
        with client, server:
            self.assertTrue(control._same_user(server))
            with mock.patch.object(control.os, "getuid", return_value=os.getuid() + 1):
                self.assertFalse(control._same_user(server))


if __name__ == "__main__":
    unittest.main()
