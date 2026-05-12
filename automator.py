"""
Cursor IDE 자동화 모듈 (macOS 전용)

AppleScript(osascript)를 사용해 Cursor 앱을 활성화하고
채팅창(Ask/Agent)을 열어 프롬프트를 입력 후 전송합니다.

긴 텍스트나 한글의 안정적인 입력을 위해 클립보드 paste 방식을 사용합니다.
원본 클립보드 내용은 작업 후 복원합니다.
"""

from __future__ import annotations

import shlex
import subprocess
import time
from dataclasses import dataclass


class AutomatorError(RuntimeError):
    """자동화 실행 중 발생한 오류."""


@dataclass(frozen=True)
class CursorMode:
    """Cursor 채팅 모드 정의.

    key:    내부 식별자
    label:  UI 표시명
    shortcut_key: ⌘+<key> 형태로 채팅창을 여는 단축키
    """

    key: str
    label: str
    shortcut_key: str


CURSOR_MODES: dict[str, CursorMode] = {
    "agent": CursorMode("agent", "Agent (Cmd+I)", "i"),
    "ask": CursorMode("ask", "Ask (Cmd+L)", "l"),
    "inline": CursorMode("inline", "Inline Edit (Cmd+K)", "k"),
}


def _run_osascript(script: str, timeout: float = 15.0) -> str:
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
        raise AutomatorError("osascript를 찾을 수 없습니다. macOS 환경에서만 동작합니다.") from exc
    except subprocess.TimeoutExpired as exc:
        raise AutomatorError("AppleScript 실행이 시간 초과되었습니다.") from exc

    if result.returncode != 0:
        stderr = (result.stderr or "").strip()
        raise AutomatorError(f"AppleScript 오류: {stderr or 'unknown'}")
    return (result.stdout or "").strip()


def is_cursor_installed() -> bool:
    """Cursor.app이 설치되어 있는지 확인."""
    script = 'tell application "System Events" to (exists application process "Cursor") or true'
    try:
        _run_osascript(
            'try\n'
            '  tell application "Finder" to get application file id "com.todesktop.230313mzl4w4u92"\n'
            '  return "yes"\n'
            'on error\n'
            '  return "no"\n'
            'end try'
        )
    except AutomatorError:
        pass
    # 더 일반적인 검사: 이름 기반
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


def _applescript_string(value: str) -> str:
    """AppleScript 문자열 리터럴로 안전 변환."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


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


def send_prompt_to_cursor(
    prompt: str,
    mode_key: str = "agent",
    *,
    open_chat: bool = True,
    press_enter: bool = True,
    activate_delay: float = 0.6,
    open_delay: float = 0.4,
    paste_delay: float = 0.25,
    pre_send_delay: float = 0.3,
    preserve_clipboard: bool = True,
) -> None:
    """Cursor 채팅창에 프롬프트를 입력하고 (옵션) 전송한다.

    Parameters
    ----------
    prompt : 보낼 프롬프트 본문 (필수, 빈 문자열 불가)
    mode_key : "agent" | "ask" | "inline" (CURSOR_MODES 키)
    open_chat : True면 단축키로 채팅창을 새로 연다.
    press_enter : True면 입력 후 Enter로 전송한다.
    *_delay : 각 단계 사이의 대기 시간(초). 환경에 따라 조정.
    preserve_clipboard : 작업 후 원래 클립보드 내용을 복원할지.
    """
    if not prompt or not prompt.strip():
        raise AutomatorError("빈 프롬프트는 전송할 수 없습니다.")
    if mode_key not in CURSOR_MODES:
        raise AutomatorError(f"알 수 없는 모드: {mode_key}")

    mode = CURSOR_MODES[mode_key]

    original_clipboard = _get_clipboard() if preserve_clipboard else None

    try:
        _set_clipboard(prompt)
        activate_cursor()
        time.sleep(activate_delay)

        # AppleScript 한 번에 묶어서 실행 (단축키 + 붙여넣기 + 전송)
        steps: list[str] = []
        if open_chat:
            steps.append(
                f'keystroke "{mode.shortcut_key}" using {{command down}}'
            )
            steps.append(f"delay {open_delay}")
        # 혹시 기존 입력이 남아있을 수 있으니 전체 선택 후 덮어씀
        steps.append('keystroke "a" using {command down}')
        steps.append("delay 0.05")
        # 클립보드 paste
        steps.append('keystroke "v" using {command down}')
        steps.append(f"delay {paste_delay}")
        if press_enter:
            steps.append(f"delay {pre_send_delay}")
            steps.append("key code 36")  # Return

        body = "\n            ".join(steps)
        script = (
            'tell application "System Events"\n'
            '    tell process "Cursor"\n'
            '        set frontmost to true\n'
            f"            {body}\n"
            "    end tell\n"
            "end tell"
        )
        _run_osascript(script)
    finally:
        if preserve_clipboard and original_clipboard is not None:
            # 약간의 지연 후 복원 (붙여넣기가 실제로 처리될 시간 확보)
            time.sleep(0.2)
            try:
                _set_clipboard(original_clipboard)
            except AutomatorError:
                pass


def check_accessibility_permission() -> bool:
    """System Events 키 입력이 가능한지 가볍게 확인.

    실제 권한이 없으면 osascript가 -1719 오류를 반환합니다.
    """
    try:
        _run_osascript(
            'tell application "System Events" to get name of first process'
        )
        return True
    except AutomatorError:
        return False
