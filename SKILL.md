# OpenClaw Local Voice Conversation

A Windows desktop OpenClaw skill for local push-to-talk voice conversations.

## Purpose

`openclaw-local-voice-conversation` turns a Windows PC into a local voice front-end for OpenClaw:

```text
microphone -> ASR -> OpenClaw text request -> reply text -> TTS -> speaker
```

This first version is intentionally a stable MVP framework, not a realtime duplex voice call.

## Trigger examples

Use this skill when the user wants to talk directly with OpenClaw from the computer:

- 开启电脑端语音对话
- 启动本地语音对话
- 我要直接和 OpenClaw 说话
- 打开麦克风对话模式
- 开始按键语音聊天

## MVP interaction model

Default mode is push-to-talk / press-to-record:

1. Start `start-voice-chat.ps1`.
2. Press Enter to start recording.
3. Press Enter again to stop recording.
4. ASR converts the recorded WAV to text.
5. The text is sent to an OpenClaw adapter.
6. The reply is converted to speech with Edge TTS.
7. The reply WAV is played locally.
8. Repeat until the user types `q`.

## Included components

- microphone recording
- faster-whisper ASR provider
- placeholder/echo OpenClaw adapter for smoke testing
- HTTP OpenClaw adapter for future real integration
- command adapter for invoking an OpenClaw CLI or script
- Edge TTS reply generation
- local WAV playback through Windows `SoundPlayer`
- UTF-8 JSONL session logging

## Non-goals for v1

- realtime full-duplex calls
- wake word detection
- speaker interruption/barge-in
- echo cancellation
- cloud control panel
- QQBot media sending
- Tmall Genie integration

## Configuration

Copy `config.example.json` to `config.json`, then choose your OpenClaw adapter:

- `echo`: smoke test without OpenClaw
- `http`: POST text to a local OpenClaw HTTP endpoint
- `command`: invoke an OpenClaw CLI/script and read stdout

## Output

Each conversation turn is logged as JSON in `logs/session-*.jsonl`.
