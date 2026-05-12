"""
Cursor IDE 자동화 모듈 (macOS 전용)

AppleScript(osascript) + System Events를 사용해 Cursor를 활성화하고
- (1) Command+I 단축키로 채팅창을 열거나
- (2) Command Palette(Cmd+Shift+P)에서 명령어를 실행해 "Cursor Agents Window"를 열거나
한 뒤, 클립보드 paste로 프롬프트를 입력하고 Return 키로 전송합니다.

긴 텍스트나 한글/이모지의 안정적인 입력을 위해 키 입력 시뮬레이션이 아닌
클립보드 paste 방식을 사용합니다. 작업 후 원본 클립보드 내용은 복원합니다.

기본 모드는 Command 키와 I 키를 동시에 눌러 Cursor 채팅 입력창을 엽니다.
"""

from __future__ import annotations

import subprocess
import time
from dataclasses import dataclass
from typing import Literal


class AutomatorError(RuntimeError):
    """자동화 실행 중 발생한 오류."""


OpenMethod = Literal["shortcut", "command", "none"]


@dataclass(frozen=True)
class CursorMode:
    """Cursor에서 프롬프트 입력 위치를 여는 방식 정의.

    method:
        - "shortcut": ⌘+<shortcut_key> 한 번으로 채팅창을 연다.
        - "command":  ⌘+Shift+P로 Command Palette를 열고 command_text를 paste 한 뒤 Return.
        - "none":     이미 채팅 입력칸에 포커스가 있다고 가정하고 그대로 paste.
    open_delay_default:
        해당 모드에서 채팅창/창 전환이 떠오르기까지의 권장 추가 대기시간(초).
    """

    key: str
    label: str
    method: OpenMethod
    shortcut_key: str = ""  # method=="shortcut"일 때만 사용
    command_text: str = ""  # method=="command"일 때만 사용
    open_delay_default: float = 0.4


# 표시 순서대로 정의 — 첫 항목이 기본값이 됨
CURSOR_MODES: dict[str, CursorMode] = {
    "agent": CursorMode(
        key="agent",
        label="채팅창 (Cmd+I) — 권장",
        method="shortcut",
        shortcut_key="i",
        open_delay_default=0.8,
    ),
    "ask": CursorMode(
        key="ask",
        label="Ask Chat (Cmd+L)",
        method="shortcut",
        shortcut_key="l",
        open_delay_default=0.6,
    ),
    "agents_window": CursorMode(
        key="agents_window",
        label="Cursor Agents Window (Cmd+Shift+P)",
        method="command",
        command_text="Agents Window",
        open_delay_default=1.5,
    ),
    "inline": CursorMode(
        key="inline",
        label="Inline Edit (Cmd+K)",
        method="shortcut",
        shortcut_key="k",
        open_delay_default=0.4,
    ),
    "focused": CursorMode(
        key="focused",
        label="이미 열린 입력칸에 그대로 입력",
        method="none",
        open_delay_default=0.0,
    ),
}

DEFAULT_MODE_KEY = "agent"


# ----------------- osascript 헬퍼 -----------------


def _run_osascript(script: str, timeout: float = 30.0) -> str:
    """osascript를 실행하고 stdout을 반환."""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AutomatorError(
            "osascript를 찾을 수 없습니다. macOS 환경에서만 동작합니다."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AutomatorError("AppleScript 실행이 시간 초과되었습니다.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise AutomatorError(f"AppleScript 오류: {stderr or 'unknown'}")
    return (result.stdout or "").strip()


def is_cursor_installed() -> bool:
    """Cursor.app이 설치돼 있는지 확인."""
    try:
        out = _run_osascript(
            'try\n'
            '  tell application "Finder" to get application file "Cursor.app"\n'
            '  return "yes"\n'
            'on error\n'
            '  return "no"\n'
            'end try'
        )
        return out == "yes"
    except AutomatorError:
        return False


def activate_cursor() -> None:
    """Cursor 앱을 전면으로 활성화."""
    _run_osascript('tell application "Cursor" to activate')


def get_frontmost_app() -> str:
    """현재 프론트인 앱 이름을 반환 (디버깅/검증용)."""
    try:
        return _run_osascript(
            'tell application "System Events" to '
            'get name of first application process whose frontmost is true'
        )
    except AutomatorError:
        return ""


def ensure_cursor_frontmost(
    max_wait: float = 2.0, poll_interval: float = 0.15
) -> None:
    """Cursor가 실제로 frontmost가 될 때까지 대기, 안 되면 한 번 더 activate.

    그래도 안 되면 AutomatorError를 던져 키 입력이 엉뚱한 앱으로
    가는 사고를 방지한다.
    """
    deadline = time.monotonic() + max_wait
    last_seen = ""
    while time.monotonic() < deadline:
        last_seen = get_frontmost_app()
        if last_seen == "Cursor":
            return
        time.sleep(poll_interval)
    # 마지막 한 번 더 activate 시도
    activate_cursor()
    time.sleep(0.4)
    last_seen = get_frontmost_app()
    if last_seen != "Cursor":
        raise AutomatorError(
            "Cursor가 프론트가 아닙니다 (현재 frontmost: "
            f"'{last_seen or 'unknown'}'). Cursor 창이 최소화/숨김이 아닌지, "
            "다른 앱이 가로채지 않는지 확인하세요."
        )


def check_accessibility_permission() -> bool:
    """System Events 키 입력이 가능한지 가볍게 확인.

    권한이 없으면 osascript가 -1719 / -25211 오류를 반환합니다.
    """
    try:
        _run_osascript(
            'tell application "System Events" to get name of first process'
        )
        return True
    except AutomatorError:
        return False


# ----------------- 클립보드 헬퍼 -----------------


def _set_clipboard(text: str) -> None:
    """파이썬 → 시스템 클립보드(pbcopy). 한글/이모지 안전."""
    proc = subprocess.run(
        ["pbcopy"], input=text, text=True, capture_output=True, check=False
    )
    if proc.returncode != 0:
        raise AutomatorError(f"클립보드 쓰기 실패: {proc.stderr.strip()}")


def _get_clipboard() -> str:
    proc = subprocess.run(["pbpaste"], capture_output=True, text=True, check=False)
    return proc.stdout if proc.returncode == 0 else ""


# ----------------- 핵심 자동화 -----------------


@dataclass
class SendOptions:
    """send_prompt_to_cursor의 동작 옵션 묶음."""

    open_chat: bool = True            # 채팅창/Agents 창을 새로 열지
    press_enter: bool = True          # 마지막에 Return으로 전송
    select_all_before_paste: bool = False  # Cmd+A로 기존 입력 덮어쓰기 (보통 불필요)
    activate_delay: float = 0.8       # 앱 활성화 후 대기
    open_delay: float = 0.0           # 0이면 모드 기본값 사용
    palette_open_delay: float = 0.45  # 커맨드 팔레트가 떠오를 시간
    palette_paste_delay: float = 0.20 # 명령어 paste 후 대기
    palette_run_delay: float = 0.25   # 명령어 실행(Return) 직전 대기
    paste_delay: float = 0.30         # 프롬프트 paste 후 대기
    pre_send_delay: float = 0.35      # Return(전송) 직전 대기
    preserve_clipboard: bool = True   # 작업 후 클립보드 원복
    command_text_override: str = ""   # method=="command" 모드에서 명령어 직접 지정
    verify_cursor_frontmost: bool = True  # 키 입력 직전 Cursor가 프론트인지 확인
    skip_paste_and_send: bool = False  # 진단용: 채팅창/Agents 창만 열고 멈춤


def _paste_via_clipboard(text: str) -> list[str]:
    """현재 클립보드를 text로 바꾸고 Cmd+V를 누르는 AppleScript 단계 목록.

    주의: 클립보드 자체는 파이썬에서 미리 _set_clipboard로 갱신해야 한다.
    이 함수는 AppleScript 단계만 만든다.
    """
    return ["key code 9 using {command down}"]


def _resolve_command_text(mode: CursorMode, opts: SendOptions) -> str:
    if opts.command_text_override.strip():
        return opts.command_text_override.strip()
    return mode.command_text


def _build_open_steps(
    mode: CursorMode, opts: SendOptions, *, run_command: bool = True
) -> list[str]:
    """채팅창/Agents 창을 여는 AppleScript 단계.

    run_command=False이면 명령어를 paste만 하고 Return은 누르지 않음 (진단용).
    """
    steps: list[str] = []
    open_delay = opts.open_delay or mode.open_delay_default

    if mode.method == "shortcut" and opts.open_chat:
        if mode.shortcut_key == "i":
            steps.append("key code 34 using {command down}")
        else:
            steps.append(f'keystroke "{mode.shortcut_key}" using {{command down}}')
        steps.append(f"delay {open_delay}")
    elif mode.method == "command" and opts.open_chat:
        # 1) Command Palette 열기
        steps.append('keystroke "p" using {command down, shift down}')
        steps.append(f"delay {opts.palette_open_delay}")
        # 2) 안전을 위해 기존 텍스트 전체 선택 후 paste (명령어는 미리 클립보드에 셋업)
        steps.append('keystroke "a" using {command down}')
        steps.append("delay 0.05")
        steps.append("key code 9 using {command down}")
        steps.append(f"delay {opts.palette_paste_delay}")
        if run_command:
            # 3) Return → 명령 실행
            steps.append(f"delay {opts.palette_run_delay}")
            steps.append("key code 36")
            # 4) Agents 창이 떠오르고 입력란에 포커스가 갈 시간
            steps.append(f"delay {open_delay}")
    # method == "none" 이면 아무 것도 안 함

    return steps


def _build_paste_and_send_steps(opts: SendOptions) -> list[str]:
    steps: list[str] = []
    if opts.select_all_before_paste:
        steps.append('keystroke "a" using {command down}')
        steps.append("delay 0.05")
    steps.append("key code 9 using {command down}")
    steps.append(f"delay {opts.paste_delay}")
    if opts.press_enter:
        steps.append(f"delay {opts.pre_send_delay}")
        steps.append("key code 36")  # Return
    return steps


def _run_steps(steps: list[str]) -> None:
    """System Events 블록으로 묶어서 실행.

    `tell process "Cursor"` 블록은 키 입력 대상을 Cursor 프로세스로
    명시적으로 지정해 다른 frontmost 앱으로 키가 새는 것을 막는다.
    """
    if not steps:
        return
    body = "\n            ".join(steps)
    script = (
        'tell application "System Events"\n'
        '    if not (exists process "Cursor") then error "Cursor 프로세스가 없습니다"\n'
        '    tell process "Cursor"\n'
        '        set frontmost to true\n'
        f"            {body}\n"
        "    end tell\n"
        "end tell"
    )
    _run_osascript(script)


def send_prompt_to_cursor(
    prompt: str,
    mode_key: str = DEFAULT_MODE_KEY,
    *,
    options: SendOptions | None = None,
) -> None:
    """Cursor에 프롬프트를 입력하고 (옵션) 전송한다.

    기본 agent 모드는 Command 키와 I 키를 동시에 눌러 채팅창을 띄운 뒤,
    프롬프트를 클립보드 paste로 입력하고 Return으로 전송한다.

    options.skip_paste_and_send=True 이면 채팅창/Agents 창만 열고
    프롬프트 입력은 건너뛴다 (진단용).
    """
    if not prompt or not prompt.strip():
        if not (options and options.skip_paste_and_send):
            raise AutomatorError("빈 프롬프트는 전송할 수 없습니다.")
    if mode_key not in CURSOR_MODES:
        raise AutomatorError(f"알 수 없는 모드: {mode_key}")

    mode = CURSOR_MODES[mode_key]
    opts = options or SendOptions()

    original_clipboard = _get_clipboard() if opts.preserve_clipboard else None

    try:
        activate_cursor()
        time.sleep(opts.activate_delay)

        # 키 입력 직전 — Cursor가 실제로 프론트인지 확인.
        # 안 그러면 "Notification processing demo"처럼 다른 앱이
        # 키 입력을 가로챌 수 있다.
        if opts.verify_cursor_frontmost:
            ensure_cursor_frontmost(max_wait=2.0)

        if mode.method == "command" and opts.open_chat:
            # 1) Command Palette에 명령어를 paste 하기 위해 클립보드를 명령어로 설정
            command_text = _resolve_command_text(mode, opts)
            if not command_text:
                raise AutomatorError(
                    "Command Palette 명령어가 비어있습니다 (command_text_override 확인)."
                )
            _set_clipboard(command_text)
            _run_steps(_build_open_steps(mode, opts, run_command=True))

            if opts.skip_paste_and_send:
                return  # 진단 모드: 명령만 실행하고 종료

            # 2) 그 다음 실제 프롬프트로 클립보드 교체 후 paste & 전송
            _set_clipboard(prompt)
            time.sleep(0.15)
            # 두 번째 키 입력 직전에도 Cursor가 그대로 프론트인지 확인
            if opts.verify_cursor_frontmost:
                ensure_cursor_frontmost(max_wait=2.0)
            _run_steps(_build_paste_and_send_steps(opts))
        else:
            if opts.skip_paste_and_send:
                # 진단 모드: 채팅창만 열기
                if mode.method != "none":
                    _run_steps(_build_open_steps(mode, opts))
                return
            _set_clipboard(prompt)
            time.sleep(0.15)
            steps = _build_open_steps(mode, opts) + _build_paste_and_send_steps(opts)
            _run_steps(steps)
    finally:
        if opts.preserve_clipboard and original_clipboard is not None:
            time.sleep(0.2)
            try:
                _set_clipboard(original_clipboard)
            except AutomatorError:
                pass
