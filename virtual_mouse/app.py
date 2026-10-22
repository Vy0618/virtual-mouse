"""Execução pelo terminal, com espera por eventos enquanto o mouse está parado."""

import argparse
from dataclasses import asdict, replace
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import sys
import tempfile
import time

from . import __version__
from .config import Settings, default_config_path, load_settings, save_settings
from .control import ControlServer, send_toggle
from .engine import MouseEngine
from .x11 import X11Backend, X11Error


class AlreadyRunningError(X11Error):
    pass


class InstanceLock:
    """Uma instância por usuário/display, liberada pelo kernel ao encerrar."""

    def __enter__(self):
        display = os.environ.get("DISPLAY", "")
        suffix = hashlib.sha256(display.encode()).hexdigest()[:12]
        path = Path(tempfile.gettempdir()) / f"virtual-mouse-{os.getuid()}-{suffix}.lock"
        flags = os.O_CREAT | os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
        self.fd = os.open(path, flags, 0o600)
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            os.close(self.fd)
            raise AlreadyRunningError("O mouse virtual já está aberto nesta sessão.") from exc
        return self

    def __exit__(self, *args):
        os.close(self.fd)


class Application:
    def __init__(self, backend, settings):
        self.backend = backend
        self.settings = settings
        self.engine = MouseEngine(backend, settings)
        self.running = True
        self.last_tick = time.monotonic()
        self._wakeup_write = None
        self.control = None
        if settings.start_enabled:
            self.set_enabled(True)

    def set_enabled(self, enabled):
        if enabled:
            self.backend.set_enabled(True)
            self.engine.set_enabled(True)
        else:
            self.engine.set_enabled(False)
            self.backend.set_enabled(False)
        print(f"Mouse virtual {'ATIVADO' if enabled else 'desativado'}.", flush=True)

    def request_stop(self):
        self.running = False
        if self._wakeup_write is not None:
            try:
                os.write(self._wakeup_write, b"\0")
            except BlockingIOError:
                pass  # O pipe cheio já acorda o select.

    def toggle(self):
        self.set_enabled(not self.engine.enabled)
        return self.engine.enabled

    def pump(self):
        was_ticking = self.engine.needs_tick
        for kind, action in self.backend.events():
            if kind == "toggle":
                self.set_enabled(not self.engine.enabled)
            elif kind == "quit":
                self.request_stop()
                break
            elif kind == "press":
                self.engine.press(action)
            elif kind == "release":
                self.engine.release(action)
        now = time.monotonic()
        if self.running and self.engine.needs_tick:
            # O primeiro movimento não inclui o tempo passado em repouso.
            dt = now - self.last_tick if was_ticking else 0.0
            self.engine.tick(dt, self.backend.precision_pressed() if self.engine.moving else False)
        self.last_tick = now

    def run(self):
        print(f"Ativar/desativar: {self.settings.toggle_hotkey} | Sair: {self.settings.quit_hotkey} ou Ctrl+C", flush=True)
        wakeup_read, wakeup_write = os.pipe2(os.O_NONBLOCK | os.O_CLOEXEC)
        self._wakeup_write = wakeup_write
        self.last_tick = time.monotonic()
        try:
            while self.running:
                self.pump()
                if not self.running:
                    break
                # Xlib pode ter lido eventos durante uma consulta síncrona.
                if self.backend.pending():
                    continue
                timeout = None
                if self.engine.needs_tick:
                    timeout = max(0, 1 / self.settings.tick_hz - (time.monotonic() - self.last_tick))
                readers = [self.backend.fd, wakeup_read]
                if self.control is not None:
                    readers.append(self.control.fileno())
                ready, _, _ = select.select(readers, [], [], timeout)
                if self.running and self.control is not None and self.control.fileno() in ready:
                    self.control.handle(self.toggle)
                    self.last_tick = time.monotonic()
        finally:
            self._wakeup_write = None
            os.close(wakeup_read)
            os.close(wakeup_write)

    def close(self):
        try:
            self.engine.set_enabled(False)
        finally:
            self.backend.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Mouse virtual pelo numpad para Linux Mint/X11, sem interface gráfica.")
    # Compatibilidade: a execução já é sempre pelo terminal.
    parser.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--enabled", action="store_true", help="Iniciar com o controle ativado.")
    parser.add_argument("--toggle", action="store_true", help="Alternar uma instância em execução; se não houver, iniciar ativado.")
    parser.add_argument("--config", type=Path, help="Caminho do arquivo JSON de configuração.")
    parser.add_argument("--check", action="store_true", help="Verificar conexão e extensões X11 sem capturar teclas.")
    parser.add_argument("--print-default-config", action="store_true", help="Mostrar a configuração padrão em JSON.")
    parser.add_argument("--write-config", action="store_true", help="Salvar configuração padrão (recusa sobrescrever arquivo).")
    parser.add_argument("--version", action="version", version=__version__)
    args = parser.parse_args(argv)
    try:
        path = args.config or default_config_path()
        if args.print_default_config:
            print(json.dumps(asdict(Settings()), ensure_ascii=False, indent=2))
            return 0
        if args.write_config:
            if path.exists():
                raise ValueError(f"{path} já existe. Edite o arquivo existente.")
            save_settings(Settings(), path, overwrite=False)
            print(f"Configuração criada: {path}")
            return 0
        if args.toggle and not args.check and send_toggle():
            return 0
        settings = load_settings(path)
        if args.enabled or (args.toggle and not args.check):
            settings = replace(settings, start_enabled=True)
        if args.check:
            with X11Backend(toggle_hotkey=settings.toggle_hotkey, quit_hotkey=settings.quit_hotkey, reserve_hotkeys=False):
                print("OK: X11, XTEST, XInput 2.1+, teclado numérico e atalhos válidos.")
                print(f"Configuração: {path}")
                print("Nenhuma tecla foi reservada. Conflitos de atalhos são verificados ao iniciar.")
            return 0
        with InstanceLock(), ControlServer() as control:
            backend = X11Backend(toggle_hotkey=settings.toggle_hotkey, quit_hotkey=settings.quit_hotkey)
            app = None
            try:
                app = Application(backend, settings)
                app.control = control
                def stop(signum, frame):
                    app.request_stop()
                old_handlers = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)}
                try:
                    app.run()
                finally:
                    for sig, handler in old_handlers.items():
                        signal.signal(sig, handler)
            finally:
                if app is not None:
                    app.close()
                else:
                    backend.close()
    except AlreadyRunningError as exc:
        if args.toggle:
            # Outra invocação pode estar entre adquirir a trava e abrir o socket.
            try:
                for _ in range(20):
                    if send_toggle():
                        return 0
                    time.sleep(0.05)
            except (OSError, ValueError) as control_error:
                exc = control_error
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    except (ValueError, OSError, X11Error) as exc:
        print(f"Erro: {exc}", file=sys.stderr)
        return 1
    return 0
