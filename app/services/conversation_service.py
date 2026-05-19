from __future__ import annotations

import json
import sys
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

ROOT_DIR = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = ROOT_DIR / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from asr_whisper import transcribe_audio  # type: ignore  # noqa: E402
from openclaw_client import get_openclaw_reply  # type: ignore  # noqa: E402
from providers.tts_edge import synthesize_sync as edge_synthesize_sync  # type: ignore  # noqa: E402
from voice_chat import append_jsonl, normalize_text, play_audio  # type: ignore  # noqa: E402

from app.config.loader import AppConfig, resolve_path
from app.utils.speech_text import cleanup_for_speech

StatusCallback = Callable[[str, str], None]


@dataclass
class TurnResult:
    ok: bool
    user_text: str
    reply_text: str
    reply_audio_path: str | None
    played: bool
    input_audio_path: str | None = None


class PushToTalkRecorder:
    def __init__(self, *, config: dict[str, Any], config_path: Path) -> None:
        self.config = config
        self.config_path = config_path
        self._stream: Any = None
        self._chunks: list[Any] = []
        self._sample_rate = 16000
        self._output_path: Path | None = None
        self._lock = threading.Lock()

    def start(self) -> Path:
        try:
            import sounddevice as sd  # type: ignore
        except ImportError as exc:
            raise RuntimeError("录音依赖 sounddevice 缺失，请先运行：pip install -r requirements.txt") from exc

        recording = self.config.get("recording") or {}
        self._sample_rate = int(recording.get("sample_rate", 16000))
        channels = int(recording.get("channels", 1))
        device = recording.get("device")
        output_dir = resolve_path(recording.get("output_dir"), base_dir=self.config_path.parent, default="./runtime/input")
        output_dir.mkdir(parents=True, exist_ok=True)
        self._output_path = output_dir / (datetime.now().strftime("input-%Y%m%d-%H%M%S-") + uuid4().hex[:8] + ".wav")
        self._chunks = []

        def callback(indata: Any, frames: int, time: Any, status: Any) -> None:
            if status:
                print(f"[recording] {status}")
            with self._lock:
                self._chunks.append(indata.copy())

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=channels,
            dtype="float32",
            device=device,
            callback=callback,
        )
        self._stream.start()
        return self._output_path.resolve()

    def stop(self) -> Path:
        try:
            import numpy as np  # type: ignore
            import soundfile as sf  # type: ignore
        except ImportError as exc:
            raise RuntimeError("录音保存依赖缺失，请先运行：pip install -r requirements.txt") from exc

        stream = self._stream
        self._stream = None
        if stream is not None:
            stream.stop()
            stream.close()

        with self._lock:
            chunks = list(self._chunks)
            self._chunks = []

        if not chunks:
            raise RuntimeError("没有录到麦克风声音，请检查麦克风权限和输入设备。")
        if self._output_path is None:
            raise RuntimeError("录音输出路径未初始化。")

        audio = np.concatenate(chunks, axis=0)
        sf.write(str(self._output_path), audio, self._sample_rate, subtype="PCM_16")
        return self._output_path.resolve()

    def abort(self) -> None:
        stream = self._stream
        self._stream = None
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass


class ConversationService:
    def __init__(self, app_config: AppConfig, *, status_callback: StatusCallback | None = None) -> None:
        self.app_config = app_config
        self.config = app_config.data
        self.config_path = app_config.path
        self.log_path = app_config.log_path
        self.status_callback = status_callback or (lambda state, message: None)
        self.history: list[dict[str, str]] = []
        self.recorder = PushToTalkRecorder(config=self.config, config_path=self.config_path)
        self.current_audio_path: Path | None = None

    def start_recording(self) -> Path:
        self._status("recording", "正在录音，请说话……")
        self.current_audio_path = self.recorder.start()
        return self.current_audio_path

    def stop_recording_and_process(self, *, no_play: bool = False) -> TurnResult:
        self._status("transcribing", "正在停止录音并识别文字……")
        input_audio_path = self.recorder.stop()
        user_text = transcribe_audio(audio_path=input_audio_path, config=self.config)
        return self.run_text_turn(user_text=user_text, no_play=no_play, input_audio_path=input_audio_path)

    def run_text_turn(self, *, user_text: str, no_play: bool = False, input_audio_path: Path | None = None) -> TurnResult:
        user_text = normalize_text(user_text, self.config)
        self._status("waiting", "正在等待模型回复……")
        reply_text = normalize_text(get_openclaw_reply(text=user_text, config=self.config, history=self.history), self.config)

        self.history.append({"role": "user", "content": user_text})
        self.history.append({"role": "assistant", "content": reply_text})
        max_history_messages = int((self.config.get("openclaw") or {}).get("max_history_messages", 12))
        if max_history_messages > 0 and len(self.history) > max_history_messages:
            del self.history[:-max_history_messages]

        self._status("speaking", "正在合成语音……")
        speech_text = cleanup_for_speech(
            reply_text,
            max_chars=int((self.config.get("tts") or {}).get("speech_max_chars", 700)),
        ) or reply_text
        reply_audio_path = self._synthesize_reply_for_gui(text=speech_text)

        playback_enabled = bool((self.config.get("playback") or {}).get("enabled", True)) and not no_play
        playback_result = None
        if playback_enabled:
            self._status("speaking", "正在播放回复……")
            playback_result = play_audio(audio_path=reply_audio_path, config=self.config, config_path=self.config_path)

        turn = {
            "ok": True,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "user_text": user_text,
            "reply_text": reply_text,
            "tts_text": speech_text,
            "input_audio_path": str(input_audio_path) if input_audio_path else None,
            "reply_audio_path": str(reply_audio_path),
            "played": playback_enabled,
            "history_messages": len(self.history),
            "playback_result": playback_result,
            "source": "gui",
        }
        append_jsonl(self.log_path, turn)
        self._status("ready", "完成，可以继续下一轮。")
        return TurnResult(
            ok=True,
            user_text=user_text,
            reply_text=reply_text,
            reply_audio_path=str(reply_audio_path),
            played=playback_enabled,
            input_audio_path=str(input_audio_path) if input_audio_path else None,
        )

    def abort_recording(self, *, update_status: bool = True) -> None:
        self.recorder.abort()
        if update_status:
            self._status("ready", "已取消录音。")

    def _synthesize_reply_for_gui(self, *, text: str) -> Path:
        tts = self.config.get("tts") or {}
        provider = str(tts.get("provider", "edge")).strip().lower()
        if provider != "edge":
            raise ValueError("目前只支持 tts.provider='edge'。")

        output_dir = resolve_path(tts.get("output_dir"), base_dir=self.config_path.parent, default="./runtime/reply")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / (datetime.now().strftime("reply-%Y%m%d-%H%M%S-") + uuid4().hex[:8] + ".wav")
        edge_synthesize_sync(
            text=text,
            output_path=output_path,
            voice=str(tts.get("voice", "zh-CN-XiaoxiaoNeural")),
            rate=str(tts.get("rate", "+0%")),
        )
        return output_path.resolve()

    def _status(self, state: str, message: str) -> None:
        self.status_callback(state, message)


def format_error(exc: BaseException) -> str:
    raw = str(exc).strip() or exc.__class__.__name__
    lower = raw.lower()
    if "config" in lower and "not found" in lower:
        return "找不到配置文件。请复制 config.example.json 为 config.json。"
    if "ffmpeg" in lower:
        return "找不到或无法使用 ffmpeg。请安装 ffmpeg，并确认 ffmpeg -version 可运行。"
    if "sounddevice" in lower or "microphone" in lower or "麦克风" in raw:
        return "麦克风不可用。请检查 Windows 麦克风权限、输入设备，以及依赖是否安装。"
    if "faster-whisper" in lower or "asr" in lower:
        return "语音识别失败。首次加载模型会较慢；如果持续失败，请检查 faster-whisper 安装和模型配置。"
    if "edge-tts" in lower or "edge_tts" in lower:
        return "语音合成失败。请检查网络连接和 edge-tts 依赖。"
    if "401" in raw or "api_key" in lower:
        return "模型 API Key 无效或未配置。请检查 config.json 或环境变量。"
    if "502" in raw or "bad gateway" in lower:
        return "模型服务返回 502，通常是上游服务暂时不可用或 OpenClaw/provider 地址配置问题。"
    return f"发生错误：{raw}"


def dump_turn_for_cli(result: TurnResult) -> str:
    return json.dumps(result.__dict__, ensure_ascii=False, indent=2)
