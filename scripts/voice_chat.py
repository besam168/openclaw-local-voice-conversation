from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from asr_whisper import transcribe_audio
from openclaw_client import get_openclaw_reply
from providers.tts_edge import synthesize_sync as edge_synthesize_sync
from record_microphone import list_devices, record_until_enter


def configure_utf8_console() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
            ctypes.windll.kernel32.SetConsoleCP(65001)
        except Exception:
            pass
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    return json.loads(config_path.read_text(encoding="utf-8-sig"))


def resolve_path(value: str | None, *, base_dir: Path, default: str) -> Path:
    raw = str(value or default).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def make_log_path(config: Dict[str, Any], config_path: Path) -> Path:
    conversation = config.get("conversation") or {}
    log_dir = resolve_path(conversation.get("log_dir"), base_dir=config_path.parent, default="./logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / (datetime.now().strftime("session-%Y%m%d-%H%M%S") + ".jsonl")


def append_jsonl(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def normalize_text(text: str, config: Dict[str, Any]) -> str:
    normalized = str(text).strip()
    if not normalized:
        raise ValueError("Text is empty")
    max_text_length = int((config.get("tts") or {}).get("max_text_length", 4000))
    if max_text_length > 0 and len(normalized) > max_text_length:
        raise ValueError(f"Text is too long ({len(normalized)} > {max_text_length})")
    return normalized


def synthesize_reply(*, text: str, config: Dict[str, Any], config_path: Path) -> Path:
    tts = config.get("tts") or {}
    provider = str(tts.get("provider", "edge")).strip().lower()
    if provider != "edge":
        raise ValueError("Only tts.provider='edge' is supported")

    output_dir = resolve_path(tts.get("output_dir"), base_dir=config_path.parent, default="./runtime/reply")
    output_dir.mkdir(parents=True, exist_ok=True)
    ext = str(tts.get("output_ext", "wav")).strip().lower().lstrip(".") or "wav"
    if ext != "wav":
        raise ValueError("Only wav TTS output is supported")

    filename = datetime.now().strftime("reply-%Y%m%d-%H%M%S-") + uuid4().hex[:8] + ".wav"
    output_path = output_dir / filename
    edge_synthesize_sync(
        text=text,
        output_path=output_path,
        voice=str(tts.get("voice", "zh-CN-XiaoxiaoNeural")),
        rate=str(tts.get("rate", "+0%")),
    )
    return output_path.resolve()


def play_audio(*, audio_path: Path, config: Dict[str, Any], config_path: Path) -> Dict[str, Any]:
    playback = config.get("playback") or {}
    script = resolve_path(playback.get("player_script"), base_dir=config_path.parent, default="./scripts/play-local-audio.ps1")
    if not script.exists():
        raise FileNotFoundError(f"Playback script not found: {script}")

    timeout_seconds = int(playback.get("timeout_seconds", 60))
    command = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-AudioPath",
        str(audio_path),
        "-TimeoutSeconds",
        str(timeout_seconds),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "Playback failed. "
            f"stderr: {(completed.stderr or '').strip() or 'No stderr output'}; "
            f"stdout: {(completed.stdout or '').strip() or 'No stdout output'}"
        )
    lines = [line.strip() for line in (completed.stdout or "").splitlines() if line.strip()]
    return {"ok": True, "output": lines}


def handle_text_turn(
    *,
    user_text: str,
    config: Dict[str, Any],
    config_path: Path,
    log_path: Path,
    no_play: bool,
    input_audio_path: Path | None = None,
) -> Dict[str, Any]:
    user_text = normalize_text(user_text, config)
    print(f"你：{user_text}")

    reply_text = normalize_text(get_openclaw_reply(text=user_text, config=config), config)
    print(f"OpenClaw：{reply_text}")

    reply_audio_path = synthesize_reply(text=reply_text, config=config, config_path=config_path)

    playback_enabled = bool((config.get("playback") or {}).get("enabled", True)) and not no_play
    playback_result = None
    if playback_enabled:
        playback_result = play_audio(audio_path=reply_audio_path, config=config, config_path=config_path)

    turn = {
        "ok": True,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "user_text": user_text,
        "reply_text": reply_text,
        "input_audio_path": str(input_audio_path) if input_audio_path else None,
        "reply_audio_path": str(reply_audio_path),
        "played": playback_enabled,
        "playback_result": playback_result,
    }
    append_jsonl(log_path, turn)
    print(json.dumps(turn, ensure_ascii=False, indent=2))
    return turn


def run_interactive_loop(*, config: Dict[str, Any], config_path: Path, log_path: Path, no_play: bool) -> None:
    print("OpenClaw 本地语音对话已启动。")
    print("按 Enter 开始录音；录音中再按 Enter 停止；输入 q 回车退出。")
    max_turns = int((config.get("conversation") or {}).get("max_turns", 0))
    turn_count = 0

    while True:
        command = input("\n[Enter=开始录音, q=退出] > ").strip().lower()
        if command in {"q", "quit", "exit"}:
            print("已退出。")
            return
        if command:
            print("未知命令。按 Enter 开始录音，或输入 q 退出。")
            continue

        print("开始录音，请说话……")
        input_audio_path = record_until_enter(config=config, config_path=config_path)
        print(f"录音文件：{input_audio_path}")
        user_text = transcribe_audio(audio_path=input_audio_path, config=config)
        handle_text_turn(
            user_text=user_text,
            config=config,
            config_path=config_path,
            log_path=log_path,
            no_play=no_play,
            input_audio_path=input_audio_path,
        )

        turn_count += 1
        if max_turns > 0 and turn_count >= max_turns:
            print(f"达到 max_turns={max_turns}，退出。")
            return


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="OpenClaw local push-to-talk voice conversation.")
    parser.add_argument("--config", default=str(Path(__file__).resolve().parents[1] / "config.json"))
    parser.add_argument("--text", help="Bypass microphone/ASR and run one text turn")
    parser.add_argument("--no-play", action="store_true", help="Do not play generated reply audio")
    parser.add_argument("--list-devices", action="store_true", help="List audio devices and exit")
    args = parser.parse_args()

    try:
        config_path = Path(args.config).resolve()
        config = load_config(config_path)

        if args.list_devices:
            list_devices()
            return

        log_path = make_log_path(config, config_path)
        print(f"日志文件：{log_path}")

        if args.text:
            handle_text_turn(
                user_text=args.text,
                config=config,
                config_path=config_path,
                log_path=log_path,
                no_play=args.no_play,
            )
            return

        run_interactive_loop(config=config, config_path=config_path, log_path=log_path, no_play=args.no_play)
    except KeyboardInterrupt:
        print("\n用户中断，退出。")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
