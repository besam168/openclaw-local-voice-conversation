from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AppConfig:
    data: dict[str, Any]
    path: Path
    root_dir: Path
    log_path: Path


def default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config.json"


def load_app_config(config_path: str | Path | None = None) -> AppConfig:
    path = Path(config_path) if config_path else default_config_path()
    path = path.expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(
            f"找不到配置文件：{path}\n请先复制 config.example.json 为 config.json，然后再启动。"
        )

    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("配置文件格式不正确：根节点必须是 JSON object。")

    root_dir = path.parent
    log_path = make_log_path(data, root_dir)
    return AppConfig(data=data, path=path, root_dir=root_dir, log_path=log_path)


def resolve_path(value: str | None, *, base_dir: Path, default: str) -> Path:
    raw = str(value or default).strip()
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def make_log_path(config: dict[str, Any], root_dir: Path) -> Path:
    conversation = config.get("conversation") or {}
    log_dir = resolve_path(conversation.get("log_dir"), base_dir=root_dir, default="./logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / (datetime.now().strftime("session-%Y%m%d-%H%M%S") + ".jsonl")
