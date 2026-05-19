from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, scrolledtext, ttk
from typing import Any

from app.config.loader import load_app_config
from app.services.conversation_service import ConversationService, format_error
from app.utils.diagnostics import format_check_summary, run_startup_checks

STATE_LABELS = {
    "ready": "就绪",
    "recording": "录音中",
    "transcribing": "识别中",
    "waiting": "等待模型",
    "speaking": "播报中",
    "error": "错误",
}


class VoiceAssistantApp:
    def __init__(self, *, config_path: str | Path | None = None) -> None:
        self.root = tk.Tk()
        self.root.title("OpenClaw 本地语音助手")
        self.root.geometry("820x620")
        self.root.minsize(720, 520)

        self.event_queue: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.is_recording = False
        self.is_busy = False
        self.no_play_var = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="正在启动……")
        self.state_var = tk.StringVar(value="启动中")

        try:
            self.app_config = load_app_config(config_path)
            self.service = ConversationService(self.app_config, status_callback=self._post_status)
            self.startup_checks = run_startup_checks(self.app_config.data)
        except Exception as exc:
            messagebox.showerror("启动失败", format_error(exc))
            raise

        self._build_widgets()
        self._set_state("ready", f"就绪。日志：{self.app_config.log_path}")
        self._append_system(format_check_summary(self.startup_checks))
        failed = [item for item in self.startup_checks if not item.ok]
        if failed:
            self._append_system("检测到部分依赖异常。文本测试可能可用，但完整语音链路可能失败。")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(100, self._drain_events)

    def run(self) -> None:
        self.root.mainloop()

    def _build_widgets(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill=tk.BOTH, expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text="状态：", font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, textvariable=self.state_var, font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=1, sticky="w")
        ttk.Checkbutton(header, text="静音/不播放", variable=self.no_play_var).grid(row=0, column=2, sticky="e", padx=8)

        ttk.Label(outer, textvariable=self.status_var, foreground="#555").grid(row=1, column=0, sticky="ew", pady=(6, 8))

        panes = ttk.PanedWindow(outer, orient=tk.VERTICAL)
        panes.grid(row=2, column=0, sticky="nsew")

        user_frame = ttk.Labelframe(panes, text="你说的话 / 文本测试")
        user_frame.rowconfigure(0, weight=1)
        user_frame.columnconfigure(0, weight=1)
        self.user_text = scrolledtext.ScrolledText(user_frame, height=7, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.user_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        panes.add(user_frame, weight=1)

        reply_frame = ttk.Labelframe(panes, text="OpenClaw 回复")
        reply_frame.rowconfigure(0, weight=1)
        reply_frame.columnconfigure(0, weight=1)
        self.reply_text = scrolledtext.ScrolledText(reply_frame, height=10, wrap=tk.WORD, font=("Microsoft YaHei UI", 10))
        self.reply_text.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        panes.add(reply_frame, weight=2)

        buttons = ttk.Frame(outer)
        buttons.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        buttons.columnconfigure(4, weight=1)
        self.record_button = ttk.Button(buttons, text="开始录音", command=self._toggle_recording)
        self.record_button.grid(row=0, column=0, padx=(0, 8))
        self.text_button = ttk.Button(buttons, text="发送文本测试", command=self._send_text)
        self.text_button.grid(row=0, column=1, padx=(0, 8))
        self.clear_button = ttk.Button(buttons, text="清空", command=self._clear_text)
        self.clear_button.grid(row=0, column=2, padx=(0, 8))
        self.exit_button = ttk.Button(buttons, text="退出", command=self._on_close)
        self.exit_button.grid(row=0, column=5, sticky="e")

        hint = "用法：点击“开始录音”，说完后点击“停止录音”。也可以在上方输入文字后点“发送文本测试”。"
        ttk.Label(outer, text=hint, foreground="#666").grid(row=4, column=0, sticky="ew", pady=(8, 0))

    def _toggle_recording(self) -> None:
        if self.is_busy and not self.is_recording:
            return
        if not self.is_recording:
            try:
                self.service.start_recording()
                self.is_recording = True
                self.is_busy = True
                self.record_button.configure(text="停止录音")
                self.text_button.configure(state=tk.DISABLED)
                self._set_state("recording", "正在录音，请说话……")
            except Exception as exc:
                self._show_error(exc)
            return

        self.is_recording = False
        self.record_button.configure(state=tk.DISABLED, text="处理中……")
        worker = threading.Thread(target=self._process_recording_worker, daemon=True)
        worker.start()

    def _process_recording_worker(self) -> None:
        try:
            result = self.service.stop_recording_and_process(no_play=self.no_play_var.get())
            self.event_queue.put(("turn", result))
        except Exception as exc:
            self.event_queue.put(("error", exc))

    def _send_text(self) -> None:
        if self.is_busy:
            return
        text = self.user_text.get("1.0", tk.END).strip()
        if not text:
            messagebox.showinfo("提示", "请先输入要发送的文字，或使用录音。")
            return
        self.is_busy = True
        self.record_button.configure(state=tk.DISABLED)
        self.text_button.configure(state=tk.DISABLED)
        worker = threading.Thread(target=self._text_worker, args=(text,), daemon=True)
        worker.start()

    def _text_worker(self, text: str) -> None:
        try:
            result = self.service.run_text_turn(user_text=text, no_play=self.no_play_var.get())
            self.event_queue.put(("turn", result))
        except Exception as exc:
            self.event_queue.put(("error", exc))

    def _post_status(self, state: str, message: str) -> None:
        self.event_queue.put(("status", (state, message)))

    def _drain_events(self) -> None:
        while True:
            try:
                kind, payload = self.event_queue.get_nowait()
            except queue.Empty:
                break
            if kind == "status":
                state, message = payload
                self._set_state(state, message)
            elif kind == "turn":
                self._handle_turn(payload)
            elif kind == "error":
                self._show_error(payload)
        self.root.after(100, self._drain_events)

    def _handle_turn(self, result: Any) -> None:
        self.user_text.delete("1.0", tk.END)
        self.user_text.insert(tk.END, result.user_text)
        self.reply_text.delete("1.0", tk.END)
        self.reply_text.insert(tk.END, result.reply_text)
        play_note = "已播放" if result.played else "未播放"
        self._set_state("ready", f"完成（{play_note}）。日志：{self.app_config.log_path}")
        self._reset_buttons()

    def _show_error(self, exc: BaseException) -> None:
        message = format_error(exc)
        self._set_state("error", message)
        self._append_system("错误：" + message)
        self.service.abort_recording(update_status=False)
        self.is_recording = False
        self._reset_buttons()
        messagebox.showerror("OpenClaw 本地语音助手", message)

    def _set_state(self, state: str, message: str) -> None:
        self.state_var.set(STATE_LABELS.get(state, state))
        self.status_var.set(message)

    def _reset_buttons(self) -> None:
        self.is_busy = False
        self.record_button.configure(state=tk.NORMAL, text="开始录音")
        self.text_button.configure(state=tk.NORMAL)

    def _clear_text(self) -> None:
        self.user_text.delete("1.0", tk.END)
        self.reply_text.delete("1.0", tk.END)

    def _append_system(self, text: str) -> None:
        existing = self.reply_text.get("1.0", tk.END).strip()
        prefix = "\n\n" if existing else ""
        self.reply_text.insert(tk.END, prefix + "[系统]\n" + text)

    def _on_close(self) -> None:
        if self.is_recording:
            self.service.abort_recording()
        self.root.destroy()


def run_app(*, config_path: str | Path | None = None) -> None:
    app = VoiceAssistantApp(config_path=config_path)
    app.run()
