from __future__ import annotations

import importlib
import shutil
import sys
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    message: str


def run_startup_checks(config: dict[str, Any]) -> list[CheckResult]:
    results: list[CheckResult] = []
    results.append(CheckResult("Python", sys.version_info >= (3, 10), f"Python {sys.version.split()[0]}"))
    results.append(_module_check("tkinter", "GUI 界面"))
    results.append(_module_check("sounddevice", "录音"))
    results.append(_module_check("soundfile", "保存 WAV"))
    results.append(_module_check("numpy", "音频处理"))
    results.append(_module_check("faster_whisper", "语音识别"))
    results.append(_module_check("edge_tts", "语音合成"))
    results.append(CheckResult("ffmpeg", bool(shutil.which("ffmpeg")), "ffmpeg 已找到" if shutil.which("ffmpeg") else "找不到 ffmpeg，请安装并加入 PATH"))

    openclaw = config.get("openclaw") or {}
    adapter = str(openclaw.get("adapter", "echo")).strip().lower()
    if adapter in {"http", "openai", "openclaw_config"}:
        results.append(_module_check("requests", f"{adapter} 模型连接"))
    else:
        results.append(CheckResult("OpenClaw adapter", True, f"当前适配器：{adapter}"))
    return results


def _module_check(module: str, purpose: str) -> CheckResult:
    try:
        importlib.import_module(module)
        return CheckResult(module, True, f"{purpose} 依赖正常")
    except Exception as exc:
        return CheckResult(module, False, f"{purpose} 依赖缺失：{exc}")


def format_check_summary(results: list[CheckResult]) -> str:
    lines = []
    for item in results:
        icon = "✅" if item.ok else "⚠️"
        lines.append(f"{icon} {item.name}: {item.message}")
    return "\n".join(lines)
