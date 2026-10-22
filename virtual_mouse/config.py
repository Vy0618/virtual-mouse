"""Configuração validada, independente do ambiente gráfico."""

from dataclasses import asdict, dataclass, fields
import json
import math
import os
from pathlib import Path
import tempfile


def default_config_path() -> Path:
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "virtual-mouse" / "config.json"


@dataclass(frozen=True)
class Settings:
    speed: float = 700.0
    initial_speed: float = 160.0
    acceleration: float = 1.4
    precision_factor: float = 0.2
    scroll_interval: float = 0.09
    tick_hz: int = 60
    toggle_hotkey: str = "Ctrl+Alt+m"
    quit_hotkey: str = "Ctrl+Alt+q"
    start_enabled: bool = False

    def __post_init__(self):
        ranges = {
            "speed": (20, 5000), "initial_speed": (1, self.speed),
            "acceleration": (0, 10), "precision_factor": (0.001, 1),
            "scroll_interval": (0.02, 2), "tick_hz": (30, 240),
        }
        for name, (low, high) in ranges.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                raise ValueError(f"{name}: informe um número finito.")
            if not low <= value <= high:
                raise ValueError(f"{name}: deve estar entre {low} e {high}.")
        if not isinstance(self.tick_hz, int):
            raise ValueError("tick_hz: informe um número inteiro.")
        for name in ("toggle_hotkey", "quit_hotkey"):
            if not isinstance(getattr(self, name), str) or not getattr(self, name).strip():
                raise ValueError(f"{name}: informe um atalho válido.")
        if self.toggle_hotkey.casefold() == self.quit_hotkey.casefold():
            raise ValueError("Os atalhos de ativar e encerrar devem ser diferentes.")
        if not isinstance(self.start_enabled, bool):
            raise ValueError("start_enabled: use true ou false.")

    @classmethod
    def from_mapping(cls, data):
        if not isinstance(data, dict):
            raise ValueError("A configuração deve ser um objeto JSON.")
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"Opções desconhecidas: {', '.join(sorted(map(str, unknown)))}")
        return cls(**data)


def load_settings(path: Path | None = None) -> Settings:
    path = Path(path) if path is not None else default_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Settings()
    except (OSError, ValueError) as exc:
        raise ValueError(f"Não foi possível ler {path}: {exc}") from exc
    return Settings.from_mapping(data)


def save_settings(settings: Settings, path: Path | None = None, *, overwrite=True):
    path = Path(path) if path is not None else default_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as stream:
            temp_name = stream.name
            json.dump(asdict(settings), stream, ensure_ascii=False, indent=2)
            stream.write("\n")
        if overwrite:
            os.replace(temp_name, path)
        else:
            # Criação exclusiva: não sobrescrever nem em caso de corrida.
            os.link(temp_name, path)
    finally:
        if temp_name and os.path.exists(temp_name):
            os.unlink(temp_name)
