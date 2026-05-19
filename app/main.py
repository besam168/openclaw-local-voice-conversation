from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.voice_chat import configure_utf8_console  # type: ignore  # noqa: E402
from app.config.loader import load_app_config  # noqa: E402
from app.services.conversation_service import ConversationService, dump_turn_for_cli, format_error  # noqa: E402
from app.ui.tk_app import run_app  # noqa: E402


def main() -> None:
    configure_utf8_console()
    parser = argparse.ArgumentParser(description="OpenClaw 本地语音助手 GUI")
    parser.add_argument("--config", help="配置文件路径，默认使用仓库根目录 config.json")
    parser.add_argument("--text", help="不打开 GUI，执行一轮文本烟测")
    parser.add_argument("--no-play", action="store_true", help="文本烟测时不播放音频")
    args = parser.parse_args()

    try:
        if args.text:
            app_config = load_app_config(args.config)
            service = ConversationService(app_config)
            result = service.run_text_turn(user_text=args.text, no_play=args.no_play)
            print(dump_turn_for_cli(result))
            return
        run_app(config_path=args.config)
    except KeyboardInterrupt:
        print("用户中断，退出。")
    except Exception as exc:
        print(format_error(exc))
        raise SystemExit(1)


if __name__ == "__main__":
    main()
