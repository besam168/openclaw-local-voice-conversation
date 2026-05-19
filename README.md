# openclaw-local-voice-conversation

A Windows/OpenClaw desktop voice conversation plugin framework.

It lets a user speak to the computer microphone, converts speech to text, sends the text to OpenClaw, converts OpenClaw's reply to speech, and plays it through the local speaker.

```text
Microphone -> ASR -> OpenClaw -> TTS -> Speaker
```

This repository is a **stable MVP framework**. It intentionally starts with push-to-talk instead of realtime full-duplex voice, because push-to-talk is much easier to make reliable on ordinary Windows PCs.

## Features

- Windows PowerShell launcher
- double-click Tkinter desktop GUI launcher
- visible GUI states: ready, recording, transcribing, waiting for model, speaking, error
- push-to-talk recording loop
- microphone recording to WAV
- faster-whisper ASR provider
- Edge TTS reply voice
- ffmpeg WAV conversion for TTS output
- local speaker playback using Windows `SoundPlayer` with MCI fallback
- OpenClaw adapters:
  - `echo` for smoke tests
  - `http` for local HTTP APIs
  - `command` for CLI/script integration
  - `openai` for any OpenAI-compatible chat/completions API
  - `openclaw_config` for reading a provider from `~/.openclaw/openclaw.json`
- JSONL conversation logs
- UTF-8 Chinese-friendly console output

## Non-goals in v1

This first framework does not implement:

- realtime duplex calls
- wake word detection
- interruption/barge-in while the assistant is speaking
- echo cancellation
- QQBot sending
- Tmall Genie integration
- web control panel

## Repository structure

```text
openclaw-local-voice-conversation/
├─ SKILL.md
├─ README.md
├─ LICENSE
├─ requirements.txt
├─ config.example.json
├─ config.openai.example.json
├─ config.openclaw-config.example.json
├─ start-voice-chat.ps1
├─ start-gui.ps1
├─ start-gui.bat
├─ app/
│  ├─ main.py
│  ├─ config/
│  ├─ services/
│  ├─ ui/
│  └─ utils/
└─ scripts/
   ├─ voice_chat.py
   ├─ record_microphone.py
   ├─ asr_whisper.py
   ├─ openclaw_client.py
   ├─ play-local-audio.ps1
   └─ providers/
      └─ tts_edge.py
```

Runtime directories:

```text
runtime/input/   # recorded microphone WAV files
runtime/reply/   # generated reply WAV files
logs/            # JSONL session logs
```

These runtime folders are ignored by git.

## System requirements

- Windows 10/11
- PowerShell 5.1+ or PowerShell 7+
- Python 3.10+ recommended
- Microphone and speaker
- Internet access for Edge TTS
- `ffmpeg` available in `PATH`
- Optional but recommended: GPU/modern CPU for faster Whisper ASR

## Install

```powershell
git clone https://github.com/besam168/openclaw-local-voice-conversation.git
cd openclaw-local-voice-conversation
pip install -r requirements.txt
ffmpeg -version
copy config.example.json config.json
```

If `ffmpeg -version` fails, install ffmpeg and add `ffmpeg.exe` to Windows `PATH`.

## Desktop GUI

Start the desktop assistant by double-clicking `start-gui.bat`, or from PowerShell:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-gui.ps1
```

The GUI shows clear state changes:

- **就绪**: ready for a new turn
- **录音中**: microphone is recording
- **识别中**: Whisper ASR is transcribing
- **等待模型**: waiting for OpenClaw/model response
- **播报中**: generating or playing Edge TTS audio
- **错误**: a recoverable error occurred

Use **开始录音** to start, then **停止录音** after speaking. You can also type into the text box and click **发送文本测试** to test the OpenClaw/TTS path without microphone/ASR. Enable **静音/不播放** when you want to generate text/audio without speaker playback.

The GUI performs startup dependency checks and displays Chinese-friendly diagnostics in the reply panel. Long or markdown-heavy model replies are cleaned before TTS so speech is shorter and more natural; the original reply text is still shown and logged.

You can also run the GUI service smoke test without opening a window:

```powershell
python -m app.main --text "老板你好，测试 GUI 服务。" --no-play
```

## Quick smoke test without OpenClaw

The default config uses the `echo` adapter, so you can test recording, ASR, TTS, and playback without a real OpenClaw API:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-voice-chat.ps1
```

Then:

1. Press Enter to start recording.
2. Speak Chinese or English.
3. Press Enter again to stop.
4. The app transcribes your speech.
5. It replies with an echo message and plays it.
6. Type `q` at the prompt to exit.

## Non-interactive text smoke test

You can bypass microphone/ASR and test OpenClaw adapter + TTS:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-voice-chat.ps1 -Text "老板你好，测试本地语音对话。"
```

Disable local playback:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\start-voice-chat.ps1 -Text "老板你好。" -NoPlay
```

## Configuration

Copy one of the example configs to `config.json`:

```powershell
copy config.example.json config.json
```

For a direct OpenAI-compatible provider:

```powershell
copy config.openai.example.json config.json
$env:OPENAI_API_KEY="your_api_key_here"
```

For a provider already configured in OpenClaw:

```powershell
copy config.openclaw-config.example.json config.json
```

Main sections:

```json
{
  "conversation": {
    "mode": "push_to_talk"
  },
  "recording": {
    "sample_rate": 16000,
    "channels": 1,
    "output_dir": "./runtime/input"
  },
  "asr": {
    "provider": "faster_whisper",
    "model_size": "base",
    "language": "zh"
  },
  "openclaw": {
    "adapter": "echo"
  },
  "tts": {
    "provider": "edge",
    "voice": "zh-CN-XiaoxiaoNeural",
    "output_dir": "./runtime/reply"
  },
  "playback": {
    "enabled": true,
    "backend": "auto"
  }
}
```

## OpenClaw adapter options

### 1. `echo` adapter

Good for local smoke testing:

```json
"openclaw": {
  "adapter": "echo",
  "echo_prefix": "OpenClaw 收到："
}
```

### 2. `http` adapter

Use this when OpenClaw exposes a local HTTP endpoint. Set `include_history` to `true` if the endpoint accepts a `history` array with previous `{role, content}` messages:

```json
"openclaw": {
  "adapter": "http",
  "http": {
    "url": "http://127.0.0.1:8765/chat",
    "timeout_seconds": 60,
    "request_text_field": "text",
    "response_text_field": "reply",
    "include_history": true
  }
}
```

The plugin sends:

```json
{
  "text": "用户说的话"
}
```

It expects JSON back with a reply field:

```json
{
  "reply": "OpenClaw 的回复"
}
```

You can change field names in config.

### 3. `command` adapter

Use this when OpenClaw can be called with a local command or script:

```json
"openclaw": {
  "adapter": "command",
  "command": {
    "program": "python",
    "args": ["C:/path/to/openclaw_chat.py", "{text}"],
    "timeout_seconds": 120
  }
}
```

`{text}` in args is replaced with the recognized user text. The adapter reads stdout. If stdout is JSON, it looks for `reply`, `text`, `content`, or `message`; otherwise stdout itself is used as the reply.

### 4. `openai` adapter

Use this for OpenAI or any OpenAI-compatible `/v1/chat/completions` provider:

```powershell
copy config.openai.example.json config.json
$env:OPENAI_API_KEY="your_api_key_here"
```

```json
"openclaw": {
  "adapter": "openai",
  "system_prompt": "你是 OpenClaw 本地电脑端语音对话助手。回答要自然、简洁，适合直接语音播报。",
  "max_history_messages": 12,
  "openai": {
    "base_url": "https://api.openai.com/v1",
    "api_key": "env:OPENAI_API_KEY",
    "model": "gpt-4o-mini",
    "timeout_seconds": 120,
    "max_tokens": 1024,
    "temperature": 0.6
  }
}
```

`api_key` supports `env:NAME` so secrets stay outside git. `base_url` may be either `https://host` or `https://host/v1`; the adapter normalizes it to `/v1/chat/completions`.

### 5. `openclaw_config` adapter

Use this when OpenClaw already has a model provider in `~/.openclaw/openclaw.json`:

```powershell
copy config.openclaw-config.example.json config.json
```

```json
"openclaw": {
  "adapter": "openclaw_config",
  "system_prompt": "你是 OpenClaw 本地电脑端语音对话助手。回答要自然、简洁，适合直接语音播报。",
  "max_history_messages": 12,
  "openclaw_config": {
    "path": "~/.openclaw/openclaw.json",
    "provider": "",
    "model": "",
    "timeout_seconds": 120,
    "max_tokens": 1024,
    "temperature": 0.6
  }
}
```

If `provider` or `model` is blank, the adapter uses the first usable provider/model it can discover. Do not copy `~/.openclaw/openclaw.json` into this repository because it may contain API keys.

### Multi-turn history

The `openai` and `openclaw_config` adapters include recent conversation turns as chat messages. `max_history_messages` controls how many previous user/assistant messages are kept; set it to `0` to disable memory. The `http` adapter can also send history when `http.include_history` is `true`.

## ASR notes

This framework uses `faster-whisper`.

Recommended starting config:

```json
"asr": {
  "provider": "faster_whisper",
  "model_size": "base",
  "device": "auto",
  "compute_type": "auto",
  "language": "zh"
}
```

If your computer is slow, try:

```json
"model_size": "small"
```

or for faster but less accurate recognition:

```json
"model_size": "tiny"
```

The first run may download the Whisper model.

## ffmpeg requirement

Edge TTS writes a temporary MP3. This plugin uses ffmpeg to convert it to WAV:

- codec: `pcm_s16le`
- mono
- `16000 Hz`

Check ffmpeg:

```powershell
ffmpeg -version
```

## Logs

Each turn is appended to:

```text
logs/session-YYYYMMDD-HHMMSS.jsonl
```

Each line contains fields such as:

- user text
- OpenClaw reply text
- recorded WAV path
- reply WAV path
- playback status
- timestamp

## Troubleshooting

### `sounddevice is not installed`

Run:

```powershell
pip install -r requirements.txt
```

### No microphone input

- Check Windows microphone privacy permissions.
- Check the default recording device.
- Try setting `recording.device` in `config.json`.

### `faster-whisper is not installed`

Run:

```powershell
pip install -r requirements.txt
```

### First ASR run is slow

The first run may download the model. Use `tiny` or `base` for early tests.

### `edge-tts is not installed`

Run:

```powershell
pip install -r requirements.txt
```

### `ffmpeg not found in PATH`

Install ffmpeg, then verify:

```powershell
ffmpeg -version
```

Restart PowerShell after changing `PATH`.

### Local playback has no sound

- Verify the reply WAV exists.
- Open it manually in Windows Media Player.
- Check Windows speaker device and volume mixer.
- Run with `-NoPlay` to separate TTS generation from playback.
- Test the playback script directly:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\play-local-audio.ps1 -AudioPath "runtime\reply\reply-file.wav"
```

- If `SoundPlayer` reports success but you still hear nothing, try the MCI backend:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\play-local-audio.ps1 -AudioPath "runtime\reply\reply-file.wav" -Backend mci
```

You can also set this in `config.json`:

```json
"playback": {
  "enabled": true,
  "backend": "mci",
  "player_script": "./scripts/play-local-audio.ps1",
  "timeout_seconds": 60
}
```

The script prints `PLAYBACK_CONFIRMED=1` when the Windows playback API returns success. If that appears but there is still no audible sound, check the Windows default output device, mute state, mixer volume, Bluetooth/headphone routing, or remote desktop audio settings.

### OpenClaw does not reply

- Start with `adapter: "echo"` to validate mic/ASR/TTS.
- For `http`, test the endpoint separately with `Invoke-RestMethod`.
- For `command`, test the command manually in PowerShell.
- Check `logs/session-*.jsonl` and console errors.

## Development plan

### Phase 1: MVP framework

- push-to-talk recording
- faster-whisper ASR
- echo/http/command OpenClaw adapters
- Edge TTS playback
- logs and docs

### Phase 2: Better desktop UX

- device listing and selection helper
- tray launcher
- hotkey push-to-talk
- better session transcript view

### Phase 3: More natural voice conversation

- VAD auto stop
- optional wake word
- assistant speech interruption
- echo cancellation investigation

## License

MIT License. See [LICENSE](LICENSE).
