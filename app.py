"""
Cursor Auto Prompter — macOS

설정한 프롬프트를 일정 간격마다 Cursor IDE 채팅창에 자동으로 입력 + 전송한다.

실행:
    python3 app.py
"""

from __future__ import annotations

import datetime as dt
import platform
import queue
import sys
import threading
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, ttk
from typing import Optional

from automator import (
    AutomatorError,
    CURSOR_MODES,
    check_accessibility_permission,
    send_prompt_to_cursor,
)
from config import AppConfig, load_config, save_config
from scheduler import RepeatingScheduler, SchedulerConfig


APP_TITLE = "Cursor Auto Prompter"
APP_VERSION = "1.0.0"


# ----------------- 헬퍼 -----------------


def _format_seconds(total: int) -> str:
    total = max(int(total), 0)
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _parse_interval(value_str: str, unit: str) -> int:
    """문자열 + 단위(sec/min/hour) → 초."""
    value = float(value_str)
    if value <= 0:
        raise ValueError("간격은 0보다 커야 합니다.")
    multiplier = {"초": 1, "분": 60, "시간": 3600}.get(unit, 60)
    seconds = int(round(value * multiplier))
    if seconds < 1:
        raise ValueError("간격은 최소 1초 이상이어야 합니다.")
    return seconds


# ----------------- GUI -----------------


class CursorAutoPrompterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.config: AppConfig = load_config()
        self.scheduler: Optional[RepeatingScheduler] = None
        self._ui_queue: "queue.Queue[callable]" = queue.Queue()

        self._build_ui()
        self._apply_config_to_ui()
        self._poll_ui_queue()
        self._update_status("대기 중")

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        if platform.system() != "Darwin":
            messagebox.showwarning(
                APP_TITLE,
                "이 앱은 macOS 전용입니다. 다른 OS에서는 자동화가 동작하지 않습니다.",
            )

    # --- UI 구성 ---

    def _build_ui(self) -> None:
        self.root.title(f"{APP_TITLE} v{APP_VERSION}")
        self.root.minsize(640, 620)

        if self.config.window_geometry:
            try:
                self.root.geometry(self.config.window_geometry)
            except tk.TclError:
                pass

        style = ttk.Style()
        # macOS 기본 테마가 보기 좋음
        try:
            style.theme_use("aqua")
        except tk.TclError:
            pass

        mono = tkfont.nametofont("TkFixedFont")

        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(2, weight=1)
        outer.rowconfigure(5, weight=1)

        # ----- 1) 프롬프트 -----
        prompt_label = ttk.Label(outer, text="반복 입력할 프롬프트")
        prompt_label.grid(row=0, column=0, sticky="w")

        prompt_frame = ttk.Frame(outer)
        prompt_frame.grid(row=2, column=0, sticky="nsew", pady=(2, 8))
        prompt_frame.columnconfigure(0, weight=1)
        prompt_frame.rowconfigure(0, weight=1)

        self.prompt_text = tk.Text(prompt_frame, height=8, wrap="word", undo=True)
        self.prompt_text.grid(row=0, column=0, sticky="nsew")
        prompt_scroll = ttk.Scrollbar(
            prompt_frame, orient="vertical", command=self.prompt_text.yview
        )
        prompt_scroll.grid(row=0, column=1, sticky="ns")
        self.prompt_text.configure(yscrollcommand=prompt_scroll.set)

        # 최근 프롬프트
        recent_frame = ttk.Frame(outer)
        recent_frame.grid(row=1, column=0, sticky="ew", pady=(0, 4))
        recent_frame.columnconfigure(1, weight=1)
        ttk.Label(recent_frame, text="최근 프롬프트:").grid(row=0, column=0, padx=(0, 6))
        self.recent_var = tk.StringVar()
        self.recent_combo = ttk.Combobox(
            recent_frame,
            textvariable=self.recent_var,
            values=self.config.recent_prompts,
            state="readonly",
        )
        self.recent_combo.grid(row=0, column=1, sticky="ew")
        self.recent_combo.bind("<<ComboboxSelected>>", self._on_pick_recent)

        # ----- 3) 옵션 -----
        opts = ttk.LabelFrame(outer, text="실행 설정", padding=10)
        opts.grid(row=3, column=0, sticky="ew", pady=(0, 8))
        for col in range(6):
            opts.columnconfigure(col, weight=1 if col in (1, 3, 5) else 0)

        ttk.Label(opts, text="간격:").grid(row=0, column=0, sticky="w")
        self.interval_value_var = tk.StringVar(value="5")
        ttk.Entry(opts, textvariable=self.interval_value_var, width=8).grid(
            row=0, column=1, sticky="w", padx=(4, 8)
        )
        self.interval_unit_var = tk.StringVar(value="분")
        ttk.Combobox(
            opts,
            textvariable=self.interval_unit_var,
            values=["초", "분", "시간"],
            width=5,
            state="readonly",
        ).grid(row=0, column=2, sticky="w")

        ttk.Label(opts, text="모드:").grid(row=0, column=3, sticky="e", padx=(12, 4))
        self.mode_var = tk.StringVar()
        mode_values = [m.label for m in CURSOR_MODES.values()]
        self.mode_combo = ttk.Combobox(
            opts,
            textvariable=self.mode_var,
            values=mode_values,
            state="readonly",
            width=22,
        )
        self.mode_combo.grid(row=0, column=4, columnspan=2, sticky="ew")

        ttk.Label(opts, text="최대 실행 횟수:").grid(
            row=1, column=0, sticky="w", pady=(8, 0)
        )
        self.max_runs_var = tk.StringVar(value="")
        ttk.Entry(opts, textvariable=self.max_runs_var, width=8).grid(
            row=1, column=1, sticky="w", padx=(4, 8), pady=(8, 0)
        )
        ttk.Label(opts, text="(비우면 무제한)").grid(
            row=1, column=2, sticky="w", pady=(8, 0)
        )

        self.run_immediately_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts,
            text="시작 즉시 1회 실행",
            variable=self.run_immediately_var,
        ).grid(row=1, column=3, columnspan=2, sticky="w", pady=(8, 0), padx=(12, 0))

        self.press_enter_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts,
            text="입력 후 Enter로 전송",
            variable=self.press_enter_var,
        ).grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 0))

        self.open_chat_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts,
            text="단축키로 채팅창 열기",
            variable=self.open_chat_var,
        ).grid(row=2, column=2, columnspan=2, sticky="w", pady=(6, 0))

        self.preserve_clipboard_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opts,
            text="클립보드 원복",
            variable=self.preserve_clipboard_var,
        ).grid(row=2, column=4, columnspan=2, sticky="w", pady=(6, 0))

        # ----- 4) 컨트롤 버튼 -----
        ctrl = ttk.Frame(outer)
        ctrl.grid(row=4, column=0, sticky="ew", pady=(0, 8))
        for col in range(4):
            ctrl.columnconfigure(col, weight=1)

        self.start_btn = ttk.Button(ctrl, text="▶ 시작", command=self._on_start)
        self.start_btn.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.stop_btn = ttk.Button(
            ctrl, text="■ 정지", command=self._on_stop, state="disabled"
        )
        self.stop_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self.test_btn = ttk.Button(ctrl, text="⚡ 즉시 한 번 보내기", command=self._on_test)
        self.test_btn.grid(row=0, column=2, sticky="ew", padx=4)

        self.clear_log_btn = ttk.Button(
            ctrl, text="🗑 로그 지우기", command=self._on_clear_log
        )
        self.clear_log_btn.grid(row=0, column=3, sticky="ew", padx=(4, 0))

        # ----- 5) 상태바 -----
        status = ttk.Frame(outer)
        status.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        status.columnconfigure(1, weight=1)
        ttk.Label(status, text="상태:").grid(row=0, column=0, sticky="w")
        self.status_var = tk.StringVar(value="대기 중")
        self.status_label = ttk.Label(
            status, textvariable=self.status_var, foreground="#0a7"
        )
        self.status_label.grid(row=0, column=1, sticky="w", padx=(6, 12))

        ttk.Label(status, text="실행 횟수:").grid(row=0, column=2, sticky="e")
        self.run_count_var = tk.StringVar(value="0")
        ttk.Label(status, textvariable=self.run_count_var).grid(
            row=0, column=3, sticky="w", padx=(4, 0)
        )

        # ----- 5) 로그 -----
        log_label = ttk.Label(outer, text="로그")
        log_label.grid(row=5, column=0, sticky="w", pady=(0, 2))
        log_frame = ttk.Frame(outer)
        log_frame.grid(row=5, column=0, sticky="nsew", pady=(18, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            log_frame, height=10, wrap="word", state="disabled", font=mono
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(
            log_frame, orient="vertical", command=self.log_text.yview
        )
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)
        self.log_text.tag_config("info", foreground="#333")
        self.log_text.tag_config("ok", foreground="#0a7")
        self.log_text.tag_config("warn", foreground="#c80")
        self.log_text.tag_config("err", foreground="#c33")

    # --- config <-> UI ---

    def _apply_config_to_ui(self) -> None:
        cfg = self.config
        self.prompt_text.delete("1.0", "end")
        self.prompt_text.insert("1.0", cfg.prompt)

        # 간격을 보기 좋은 단위로 분해
        if cfg.interval_seconds % 3600 == 0:
            self.interval_value_var.set(str(cfg.interval_seconds // 3600))
            self.interval_unit_var.set("시간")
        elif cfg.interval_seconds % 60 == 0:
            self.interval_value_var.set(str(cfg.interval_seconds // 60))
            self.interval_unit_var.set("분")
        else:
            self.interval_value_var.set(str(cfg.interval_seconds))
            self.interval_unit_var.set("초")

        mode = CURSOR_MODES.get(cfg.mode_key, CURSOR_MODES["agent"])
        self.mode_var.set(mode.label)
        self.run_immediately_var.set(cfg.run_immediately)
        self.max_runs_var.set("" if cfg.max_runs is None else str(cfg.max_runs))
        self.press_enter_var.set(cfg.press_enter)
        self.open_chat_var.set(cfg.open_chat)
        self.preserve_clipboard_var.set(cfg.preserve_clipboard)
        self.recent_combo["values"] = cfg.recent_prompts

    def _collect_config_from_ui(self) -> AppConfig:
        cfg = self.config
        cfg.prompt = self.prompt_text.get("1.0", "end").rstrip("\n")
        cfg.interval_seconds = _parse_interval(
            self.interval_value_var.get().strip(), self.interval_unit_var.get()
        )
        # 모드 라벨 → key
        label = self.mode_var.get()
        cfg.mode_key = next(
            (k for k, m in CURSOR_MODES.items() if m.label == label), "agent"
        )
        cfg.run_immediately = bool(self.run_immediately_var.get())
        max_runs_str = self.max_runs_var.get().strip()
        cfg.max_runs = int(max_runs_str) if max_runs_str else None
        if cfg.max_runs is not None and cfg.max_runs <= 0:
            raise ValueError("최대 실행 횟수는 1 이상이어야 합니다.")
        cfg.press_enter = bool(self.press_enter_var.get())
        cfg.open_chat = bool(self.open_chat_var.get())
        cfg.preserve_clipboard = bool(self.preserve_clipboard_var.get())
        cfg.window_geometry = self.root.geometry()
        return cfg

    # --- 액션 핸들러 ---

    def _on_pick_recent(self, _event=None) -> None:
        value = self.recent_var.get()
        if value:
            self.prompt_text.delete("1.0", "end")
            self.prompt_text.insert("1.0", value)

    def _on_start(self) -> None:
        try:
            cfg = self._collect_config_from_ui()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"설정 오류: {exc}")
            return

        if not cfg.prompt.strip():
            messagebox.showerror(APP_TITLE, "프롬프트를 입력해주세요.")
            return

        if platform.system() == "Darwin" and not check_accessibility_permission():
            messagebox.showwarning(
                APP_TITLE,
                "시스템 환경설정 → 개인정보 보호 및 보안 → 손쉬운 사용에서\n"
                "터미널(또는 이 앱을 실행한 프로세스)에 권한을 허용해야 합니다.",
            )

        cfg.add_recent_prompt(cfg.prompt)
        self.config = cfg
        save_config(cfg)
        self.recent_combo["values"] = cfg.recent_prompts

        self._log(
            f"시작: 간격 {_format_seconds(cfg.interval_seconds)}, "
            f"모드 {CURSOR_MODES[cfg.mode_key].label}, "
            f"최대 {cfg.max_runs if cfg.max_runs is not None else '∞'}회",
            "info",
        )

        self.scheduler = RepeatingScheduler(
            SchedulerConfig(
                interval_seconds=cfg.interval_seconds,
                run_immediately=cfg.run_immediately,
                max_runs=cfg.max_runs,
            ),
            on_run=self._on_scheduled_run,
            on_tick=self._on_scheduled_tick,
            on_error=self._on_scheduled_error,
            on_stop=self._on_scheduled_stop,
        )
        self.scheduler.start()
        self._set_running_ui(True)

    def _on_stop(self) -> None:
        if self.scheduler is not None:
            self.scheduler.stop("user")
            self._log("정지 요청됨", "warn")

    def _on_test(self) -> None:
        try:
            cfg = self._collect_config_from_ui()
        except ValueError as exc:
            messagebox.showerror(APP_TITLE, f"설정 오류: {exc}")
            return
        if not cfg.prompt.strip():
            messagebox.showerror(APP_TITLE, "프롬프트를 입력해주세요.")
            return
        cfg.add_recent_prompt(cfg.prompt)
        self.config = cfg
        save_config(cfg)
        self.recent_combo["values"] = cfg.recent_prompts

        self._log("테스트 전송 시도…", "info")
        threading.Thread(
            target=self._send_once_async, args=(cfg,), daemon=True
        ).start()

    def _send_once_async(self, cfg: AppConfig) -> None:
        try:
            send_prompt_to_cursor(
                cfg.prompt,
                mode_key=cfg.mode_key,
                open_chat=cfg.open_chat,
                press_enter=cfg.press_enter,
                activate_delay=cfg.activate_delay,
                open_delay=cfg.open_delay,
                paste_delay=cfg.paste_delay,
                pre_send_delay=cfg.pre_send_delay,
                preserve_clipboard=cfg.preserve_clipboard,
            )
        except AutomatorError as exc:
            self._post(lambda: self._log(f"전송 실패: {exc}", "err"))
            return
        except Exception as exc:  # noqa: BLE001
            self._post(lambda: self._log(f"예기치 못한 오류: {exc}", "err"))
            return
        self._post(lambda: self._log("전송 성공", "ok"))

    def _on_clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    # --- 스케줄러 콜백 (워커 스레드에서 호출됨) ---

    def _on_scheduled_run(self, run_count: int) -> None:
        cfg = self.config
        try:
            send_prompt_to_cursor(
                cfg.prompt,
                mode_key=cfg.mode_key,
                open_chat=cfg.open_chat,
                press_enter=cfg.press_enter,
                activate_delay=cfg.activate_delay,
                open_delay=cfg.open_delay,
                paste_delay=cfg.paste_delay,
                pre_send_delay=cfg.pre_send_delay,
                preserve_clipboard=cfg.preserve_clipboard,
            )
        except AutomatorError as exc:
            self._post(
                lambda: self._log(f"[{run_count}회차] 전송 실패: {exc}", "err")
            )
            return
        self._post(
            lambda: (
                self._log(f"[{run_count}회차] 전송 성공", "ok"),
                self.run_count_var.set(str(run_count)),
            )
        )

    def _on_scheduled_tick(self, remaining: int, run_count: int) -> None:
        self._post(
            lambda: self._update_status(
                f"실행 중 — 다음 전송까지 {_format_seconds(remaining)}"
            )
        )

    def _on_scheduled_error(self, exc: BaseException) -> None:
        self._post(lambda: self._log(f"스케줄러 오류: {exc}", "err"))

    def _on_scheduled_stop(self, reason: str) -> None:
        text = {
            "user": "사용자가 정지함",
            "max_runs_reached": "최대 실행 횟수 도달",
            "completed": "완료",
        }.get(reason, reason)
        self._post(
            lambda: (
                self._log(f"정지됨 ({text})", "warn"),
                self._set_running_ui(False),
                self._update_status("대기 중"),
            )
        )

    # --- 유틸 ---

    def _set_running_ui(self, running: bool) -> None:
        self.start_btn.configure(state="disabled" if running else "normal")
        self.stop_btn.configure(state="normal" if running else "disabled")
        self.test_btn.configure(state="disabled" if running else "normal")
        for child in self.root.winfo_children():
            pass  # 입력 잠금은 추가하지 않음 — 사용자가 다음 프롬프트를 미리 편집 가능

    def _update_status(self, text: str) -> None:
        self.status_var.set(text)

    def _log(self, message: str, level: str = "info") -> None:
        ts = dt.datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{ts}] {message}\n", level)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _post(self, fn) -> None:
        """워커 스레드에서 메인 스레드로 콜백 디스패치."""
        self._ui_queue.put(fn)

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                fn = self._ui_queue.get_nowait()
                try:
                    fn()
                except Exception as exc:  # noqa: BLE001
                    print(f"UI 콜백 오류: {exc}", file=sys.stderr)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui_queue)

    def _on_close(self) -> None:
        try:
            cfg = self._collect_config_from_ui()
            save_config(cfg)
        except Exception:
            pass
        if self.scheduler is not None and self.scheduler.is_running:
            self.scheduler.stop("user")
        self.root.destroy()


def main() -> int:
    root = tk.Tk()
    CursorAutoPrompterApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
