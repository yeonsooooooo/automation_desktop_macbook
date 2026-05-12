"""앱 설정 영속화."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional


CONFIG_DIR = Path(os.path.expanduser("~/.cursor_auto_prompter"))
CONFIG_PATH = CONFIG_DIR / "config.json"


@dataclass
class AppConfig:
    prompt: str = "계속 진행해줘."
    interval_seconds: int = 300  # 5분
    mode_key: str = "agent"  # agent (Cmd+I) | ask | agents_window | inline | focused
    run_immediately: bool = True
    max_runs: Optional[int] = None
    press_enter: bool = True
    open_chat: bool = True
    activate_delay: float = 0.8
    open_delay: float = 0.0  # 0이면 모드별 권장값 사용
    paste_delay: float = 0.25
    pre_send_delay: float = 0.3
    preserve_clipboard: bool = True
    command_text_override: str = ""  # "Agents Window" 외 다른 명령으로 바꾸고 싶을 때
    verify_cursor_frontmost: bool = True
    window_geometry: Optional[str] = None
    recent_prompts: list[str] = field(default_factory=list)

    def add_recent_prompt(self, prompt: str, max_items: int = 10) -> None:
        prompt = prompt.strip()
        if not prompt:
            return
        if prompt in self.recent_prompts:
            self.recent_prompts.remove(prompt)
        self.recent_prompts.insert(0, prompt)
        del self.recent_prompts[max_items:]


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return AppConfig()
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()
    cfg = AppConfig()
    for key, value in data.items():
        if hasattr(cfg, key):
            setattr(cfg, key, value)
    # 마이그레이션: "focused" 모드는 단축키 없이 현재 포커스된 곳에 paste 하므로
    # Tk 앱이 포커스를 잡고 있을 때 사고가 자주 남. 기본 Cmd+I 모드로 전환.
    if cfg.mode_key == "focused":
        cfg.mode_key = "agent"
    # 이전 설정에 짧은 대기시간이 저장돼 있으면 Cmd+I 직후 paste가 너무 빨리 들어갈 수 있다.
    if cfg.mode_key == "agent" and cfg.open_delay and cfg.open_delay < 0.8:
        cfg.open_delay = 0.0
    if cfg.mode_key == "agent" and cfg.paste_delay < 0.5:
        cfg.paste_delay = 0.5
    return cfg


def save_config(cfg: AppConfig) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(asdict(cfg), ensure_ascii=False, indent=2), encoding="utf-8"
    )
