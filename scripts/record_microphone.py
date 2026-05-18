from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict
from uuid import uuid4


def list_devices() -> None:
    try:
        import sounddevice as sd  # type: ignore
    except ImportError as exc:
        raise RuntimeError("sounddevice is not installed. Run: pip install -r requirements.txt") from exc

    print(sd.query_devices())


def record_until_enter(*, config: Dict[str, Any], config_path: Path) -> Path:
    try:
        import numpy as np  # type: ignore
        import sounddevice as sd  # type: ignore
        import soundfile as sf  # type: ignore
    except ImportError as exc:
        raise RuntimeError("Recording dependencies are missing. Run: pip install -r requirements.txt") from exc

    recording = config.get("recording") or {}
    sample_rate = int(recording.get("sample_rate", 16000))
    channels = int(recording.get("channels", 1))
    device = recording.get("device")
    output_dir = Path(recording.get("output_dir", "./runtime/input"))
    if not output_dir.is_absolute():
        output_dir = (config_path.parent / output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = datetime.now().strftime("input-%Y%m%d-%H%M%S-") + uuid4().hex[:8] + ".wav"
    output_path = output_dir / filename

    chunks: list[Any] = []

    def callback(indata: Any, frames: int, time: Any, status: Any) -> None:
        if status:
            print(f"[recording] {status}")
        chunks.append(indata.copy())

    print("按 Enter 停止录音。")
    with sd.InputStream(samplerate=sample_rate, channels=channels, dtype="float32", device=device, callback=callback):
        input()

    if not chunks:
        raise RuntimeError("No microphone audio was captured")

    audio = np.concatenate(chunks, axis=0)
    sf.write(str(output_path), audio, sample_rate, subtype="PCM_16")
    return output_path.resolve()
