from __future__ import annotations

import asyncio
import shutil
import subprocess
from pathlib import Path


async def synthesize_to_file(*, text: str, output_path: Path, voice: str, rate: str = "+0%") -> Path:
    try:
        import edge_tts  # type: ignore
    except ImportError as exc:
        raise RuntimeError("edge-tts is not installed. Run: pip install -r requirements.txt") from exc

    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if output_path.suffix.lower() != ".wav":
        raise ValueError("Only .wav output is supported")

    temp_mp3_path = output_path.with_suffix(".edge-temp.mp3")
    communicator = edge_tts.Communicate(text=text, voice=voice, rate=rate)
    await communicator.save(str(temp_mp3_path))

    ffmpeg_path = shutil.which("ffmpeg")
    if not ffmpeg_path:
        try:
            temp_mp3_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError("ffmpeg not found in PATH. Install ffmpeg and verify with: ffmpeg -version")

    command = [
        ffmpeg_path,
        "-y",
        "-i",
        str(temp_mp3_path),
        "-acodec",
        "pcm_s16le",
        "-ac",
        "1",
        "-ar",
        "16000",
        str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace", check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "ffmpeg failed to convert edge-tts mp3 to wav. "
            f"stderr: {(completed.stderr or '').strip() or 'No stderr output'}; "
            f"stdout: {(completed.stdout or '').strip() or 'No stdout output'}"
        )

    try:
        temp_mp3_path.unlink(missing_ok=True)
    except Exception:
        pass
    return output_path


def synthesize_sync(*, text: str, output_path: Path, voice: str, rate: str = "+0%") -> Path:
    return asyncio.run(synthesize_to_file(text=text, output_path=output_path, voice=voice, rate=rate))
