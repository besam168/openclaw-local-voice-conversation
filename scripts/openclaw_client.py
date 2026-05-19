from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List

History = List[Dict[str, str]]


def get_openclaw_reply(*, text: str, config: Dict[str, Any], history: History | None = None) -> str:
    openclaw = config.get("openclaw") or {}
    adapter = str(openclaw.get("adapter", "echo")).strip().lower()
    history = history or []

    if adapter == "echo":
        prefix = str(openclaw.get("echo_prefix", "OpenClaw 收到："))
        return prefix + text
    if adapter == "http":
        return _http_reply(text=text, openclaw=openclaw, history=history)
    if adapter == "command":
        return _command_reply(text=text, openclaw=openclaw)
    if adapter in {"openai", "openclaw_config"}:
        return _openai_compatible_reply(text=text, config=config, history=history)

    raise ValueError(
        f"Unsupported openclaw.adapter: {adapter}. "
        "Supported: echo, http, command, openai, openclaw_config"
    )


def _http_reply(*, text: str, openclaw: Dict[str, Any], history: History) -> str:
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
    include_history = bool(http.get("include_history", False))

    body: Dict[str, Any] = {request_text_field: text}
    if include_history:
        body["history"] = history

    response = requests.post(url, json=body, timeout=timeout_seconds)
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


def _openai_compatible_reply(*, text: str, config: Dict[str, Any], history: History) -> str:
    try:
        import requests  # type: ignore
    except ImportError as exc:
        raise RuntimeError("requests is not installed. Run: pip install -r requirements.txt") from exc

    openclaw = config.get("openclaw") or {}
    adapter = str(openclaw.get("adapter", "openai")).strip().lower()

    if adapter == "openclaw_config":
        client = _load_client_from_openclaw_config(openclaw)
    else:
        client = dict(openclaw.get("openai") or {})

    base_url = _normalize_openai_base_url(client.get("base_url") or client.get("baseUrl") or "")
    api_key = _resolve_secret(client.get("api_key") or client.get("apiKey") or "")
    model = str(client.get("model") or "").strip()
    timeout_seconds = int(client.get("timeout_seconds", client.get("timeoutSeconds", 120)))
    max_tokens = int(client.get("max_tokens", client.get("maxTokens", 1024)))
    temperature = float(client.get("temperature", 0.6))

    if not base_url:
        raise ValueError("openai/openclaw_config base_url is required")
    if not api_key:
        raise ValueError("openai/openclaw_config api_key is required")
    if not model:
        raise ValueError("openai/openclaw_config model is required")

    system_prompt = str(
        openclaw.get(
            "system_prompt",
            "你是 OpenClaw 本地电脑端语音对话助手。回答要自然、简洁，适合直接语音播报。",
        )
    )
    max_history_messages = int(openclaw.get("max_history_messages", 12))
    trimmed_history = history[-max_history_messages:] if max_history_messages > 0 else []
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    messages.extend(trimmed_history)
    messages.append({"role": "user", "content": text})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    extra_headers = client.get("headers") or {}
    if isinstance(extra_headers, dict):
        headers.update({str(k): str(v) for k, v in extra_headers.items()})

    url = base_url + "/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    response = requests.post(url, headers=headers, json=payload, timeout=timeout_seconds)
    response.raise_for_status()
    data = response.json()
    try:
        reply = data["choices"][0]["message"]["content"]
    except Exception as exc:
        raise RuntimeError(f"OpenAI-compatible response missing choices[0].message.content: {data}") from exc
    return str(reply).strip()


def _normalize_openai_base_url(value: Any) -> str:
    base_url = str(value or "").strip().rstrip("/")
    if not base_url:
        return ""
    if base_url.endswith("/v1"):
        return base_url
    return base_url + "/v1"


def _load_client_from_openclaw_config(openclaw: Dict[str, Any]) -> Dict[str, Any]:
    cfg = openclaw.get("openclaw_config") or {}
    config_path = Path(str(cfg.get("path") or "~/.openclaw/openclaw.json")).expanduser()
    provider_id = str(cfg.get("provider") or "").strip()
    model_id = str(cfg.get("model") or "").strip()
    timeout_seconds = int(cfg.get("timeout_seconds", 120))
    max_tokens = int(cfg.get("max_tokens", 1024))
    temperature = float(cfg.get("temperature", 0.6))

    if not config_path.exists():
        raise FileNotFoundError(f"OpenClaw config file not found: {config_path}")
    data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    providers = ((data.get("models") or {}).get("providers") or {})
    if not isinstance(providers, dict) or not providers:
        raise RuntimeError(f"No model providers found in {config_path}")

    provider: Dict[str, Any] | None = None
    if provider_id:
        raw = providers.get(provider_id)
        if not isinstance(raw, dict):
            raise RuntimeError(f"Provider '{provider_id}' not found in {config_path}")
        provider = raw
    else:
        for raw in providers.values():
            if isinstance(raw, dict) and raw.get("baseUrl") and raw.get("apiKey") and raw.get("models"):
                provider = raw
                break
    if provider is None:
        raise RuntimeError(f"No usable provider found in {config_path}")

    models = provider.get("models") or []
    if not model_id:
        for model in models:
            if isinstance(model, dict) and model.get("id"):
                model_id = str(model["id"])
                break
    if not model_id:
        raise RuntimeError("No model id configured or discoverable from OpenClaw config")

    return {
        "base_url": _normalize_openai_base_url(provider.get("baseUrl") or ""),
        "api_key": provider.get("apiKey") or "",
        "model": model_id,
        "timeout_seconds": timeout_seconds,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "headers": provider.get("headers") or {},
    }


def _resolve_secret(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.startswith("env:"):
        return os.environ.get(raw[4:], "").strip()
    return raw
