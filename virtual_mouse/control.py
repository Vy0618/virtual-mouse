"""Toggle entre processos usando um socket local do Linux, sem polling."""

import errno
import hashlib
import os
import socket
import struct


def control_address():
    display = os.environ.get("DISPLAY", "")
    suffix = hashlib.sha256(display.encode()).hexdigest()[:12]
    # Socket abstrato: o kernel remove o endereço ao fechar o processo.
    return f"\0virtual-mouse-{os.getuid()}-{suffix}"


def _same_user(connection):
    credentials = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
    return struct.unpack("3i", credentials)[1] == os.getuid()


def send_toggle():
    """Retorna False se não houver servidor; espera confirmação se houver."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(2)
        try:
            connection.connect(control_address())
        except OSError as exc:
            if exc.errno in (errno.ECONNREFUSED, errno.ENOENT):
                return False
            raise
        if not _same_user(connection):
            raise ValueError("O controle remoto pertence a outro usuário.")
        connection.sendall(b"toggle\n")
        response = b""
        while b"\n" not in response and len(response) < 2048:
            chunk = connection.recv(2048 - len(response))
            if not chunk:
                break
            response += chunk
        message = response.decode("utf-8", errors="replace").strip()
        if not message.startswith("OK "):
            raise ValueError(message or "O programa encerrou sem confirmar o toggle.")
        print(message[3:], flush=True)
        return True


class ControlServer:
    def __enter__(self):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self.socket.bind(control_address())
            self.socket.listen(8)
            self.socket.setblocking(False)
        except BaseException:
            self.socket.close()
            raise
        return self

    def fileno(self):
        return self.socket.fileno()

    def handle(self, toggle):
        try:
            connection, _ = self.socket.accept()
        except BlockingIOError:
            return
        with connection:
            connection.settimeout(0.2)
            try:
                if not _same_user(connection):
                    return
                command = b""
                while b"\n" not in command and len(command) < 128:
                    chunk = connection.recv(128 - len(command))
                    if not chunk:
                        return
                    command += chunk
                if command != b"toggle\n":
                    connection.sendall(b"ERRO: comando desconhecido.\n")
                    return
                try:
                    enabled = toggle()
                    message = "OK Mouse virtual ATIVADO.\n" if enabled else "OK Mouse virtual desativado.\n"
                except (RuntimeError, OSError, ValueError) as exc:
                    message = f"ERRO: {exc}\n"
                connection.sendall(message.encode())
            except OSError:
                pass  # Cliente que encerrou não deve derrubar o controle do mouse.

    def __exit__(self, *args):
        self.socket.close()
