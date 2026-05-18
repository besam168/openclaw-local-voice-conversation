from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}


def _normalize_device(value: str) -> str:
    if value == "auto":
        return "cpu"
    return value


def _normalize_compute_type(value: str, device: str) -> str:
    if value != "auto":
        return value
    if device == "cpu":
        return "int8"
    return "float16"


def transcribe_audio(*, audio_path: Path, config: Dict[str, Any]) -> str:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise RuntimeError("faster-whisper is not installed. Run: pip install -r requirements.txt") from exc

    asr = config.get("asr") or {}
    provider = str(asr.get("provider", "faster_whisper")).strip().lower()
    if provider != "faster_whisper":
        raise ValueError("Only asr.provider='faster_whisper' is supported in this framework")

    model_size = str(asr.get("model_size", "base"))
    device = _normalize_device(str(asr.get("device", "auto")))
    compute_type = _normalize_compute_type(str(asr.get("compute_type", "auto")), device)
    language = asr.get("language", "zh")
    beam_size = int(asr.get("beam_size", 5))

    key = (model_size, device, compute_type)
    model = _MODEL_CACHE.get(key)
    if model is None:
        print(f"[asr] Loading faster-whisper model={model_size} device={device} compute_type={compute_type}")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
        _MODEL_CACHE[key] = model

    segments, info = model.transcribe(str(audio_path), language=language, beam_size=beam_size)
    text = "".join(segment.text for segment in segments).strip()
    if not text:
        raise RuntimeError("ASR returned empty text")
    return text
