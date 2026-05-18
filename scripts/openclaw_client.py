from __future__ import annotations

import json
import subprocess
from typing import Any, Dict


def get_openclaw_reply(*, text: str, config: Dict[str, Any]) -> str:
    openclaw = config.get("openclaw") or {}
    adapter = str(openclaw.get("adapter", "echo")).strip().lower()

    if adapter == "echo":
        prefix = str(openclaw.get("echo_prefix", "OpenClaw 收到："))
        return prefix + text
    if adapter == "http":
        return _http_reply(text=text, openclaw=openclaw)
    if adapter == "command":
        return _command_reply(text=text, openclaw=openclaw)

    raise ValueError(f"Unsupported openclaw.adapter: {adapter}. Supported: echo, http, command")


def _http_reply(*, text: str, openclaw: Dict[str, Any]) -> str:
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise RuntimeError("requests is not installed. Run: pip install -r requirements.txt") from exc

    http = openclaw.get("http") or {}
    url = str(http.get("url") or "").strip()
    if not url:
        raise ValueError("openclaw.http.url is required for http adapter")

    timeout_seconds = int(http.get("timeout_seconds", 60))
    request_text_field = str(http.get("request_text_field", "text"))
    response_text_field = str(http.get("response_text_field", "reply"))

    response = requests.post(url, json={request_text_field: text}, timeout=timeout_seconds)
    response.raise_for_status()

    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(f"OpenClaw HTTP response is not JSON: {response.text[:500]}") from exc

    reply = payload.get(response_text_field)
    if reply is None:
        for key in ("reply", "text", "content", "message"):
            if payload.get(key) is not None:
                reply = payload.get(key)
                break
    if reply is None:
        raise RuntimeError(f"OpenClaw HTTP response missing reply field '{response_text_field}': {payload}")
    return str(reply).strip()


def _command_reply(*, text: str, openclaw: Dict[str, Any]) -> str:
    command = openclaw.get("command") or {}
    program = str(command.get("program") or "").strip()
    if not program:
        raise ValueError("openclaw.command.program is required for command adapter")

    raw_args = command.get("args") or []
    args = [str(arg).replace("{text}", text) for arg in raw_args]
    timeout_seconds = int(command.get("timeout_seconds", 120))

    completed = subprocess.run(
        [program, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "OpenClaw command failed. "
            f"stderr: {(completed.stderr or '').strip() or 'No stderr output'}; "
            f"stdout: {(completed.stdout or '').strip() or 'No stdout output'}"
        )

    stdout = (completed.stdout or "").strip()
    if not stdout:
        raise RuntimeError("OpenClaw command returned empty stdout")

    try:
        payload = json.loads(stdout)
        if isinstance(payload, dict):
            for key in ("reply", "text", "content", "message"):
                if payload.get(key) is not None:
                    return str(payload[key]).strip()
    except Exception:
        pass

    return stdout
