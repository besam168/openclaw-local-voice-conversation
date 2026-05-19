import json
import shutil
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print(json.dumps({"reply": "未收到输入文本。"}, ensure_ascii=False))
        return 0

    text = sys.argv[1]
    openclaw_bin = shutil.which("openclaw") or shutil.which("openclaw.cmd") or shutil.which("openclaw.exe")
    if not openclaw_bin:
        raise SystemExit("openclaw executable not found in PATH")

    completed = subprocess.run(
        [openclaw_bin, "agent", "--agent", "main", "--message", text, "--json"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if completed.returncode != 0:
        raise SystemExit(
            f"openclaw agent failed. stderr: {(completed.stderr or '').strip() or 'No stderr'}; "
            f"stdout: {(completed.stdout or '').strip() or 'No stdout'}"
        )

    raw = (completed.stdout or "").strip()
    if not raw:
        print(json.dumps({"reply": ""}, ensure_ascii=False))
        return 0

    try:
        data = json.loads(raw)
    except Exception:
        print(json.dumps({"reply": raw}, ensure_ascii=False))
        return 0

    reply = ""
    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, dict):
            payloads = result.get("payloads")
            if isinstance(payloads, list):
                for item in payloads:
                    if isinstance(item, dict):
                        text_value = item.get("text")
                        if isinstance(text_value, str) and text_value.strip():
                            reply = text_value.strip()
                            break

        if not reply:
            for key in ("reply", "text", "message"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    reply = value.strip()
                    break

        if not reply and isinstance(result, dict):
            for key in ("reply", "text", "message", "content"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    reply = value.strip()
                    break

    print(json.dumps({"reply": reply or raw}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
