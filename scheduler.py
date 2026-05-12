"""
반복 실행 스케줄러.

별도 스레드에서 동작하며, 지정된 간격마다 콜백을 호출한다.
- 시작/정지/일시정지 지원
- 다음 실행까지 남은 시간을 1초 단위로 tick 콜백으로 알려줌
- 최대 실행 횟수 제한 옵션
- 첫 실행을 즉시 vs. 간격 후 선택 가능
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable, Optional


TickCallback = Callable[[int, int], None]  # (remaining_seconds, run_count)
RunCallback = Callable[[int], None]  # (run_count_after_this_run)
ErrorCallback = Callable[[BaseException], None]
StopCallback = Callable[[str], None]  # reason


@dataclass
class SchedulerConfig:
    interval_seconds: int
    run_immediately: bool = True
    max_runs: Optional[int] = None  # None = 무제한


class RepeatingScheduler:
    """간격마다 작업을 반복 실행하는 스레드 기반 스케줄러."""

    def __init__(
        self,
        config: SchedulerConfig,
        on_run: RunCallback,
        on_tick: Optional[TickCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        on_stop: Optional[StopCallback] = None,
    ) -> None:
        if config.interval_seconds <= 0:
            raise ValueError("interval_seconds는 1 이상이어야 합니다.")
        self._config = config
        self._on_run = on_run
        self._on_tick = on_tick
        self._on_error = on_error
        self._on_stop = on_stop

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._run_count = 0
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def run_count(self) -> int:
        return self._run_count

    def start(self) -> None:
        with self._lock:
            if self.is_running:
                return
            self._stop_event.clear()
            self._run_count = 0
            self._thread = threading.Thread(
                target=self._loop, name="RepeatingScheduler", daemon=True
            )
            self._thread.start()

    def stop(self, reason: str = "user") -> None:
        self._stop_event.set()
        # on_stop은 _loop의 finally에서 발화 (단, 외부에서 stop 호출 시 reason 전달 필요)
        self._stop_reason = reason

    def _loop(self) -> None:
        reason = "completed"
        try:
            if self._config.run_immediately:
                self._fire_once()
                if self._should_stop_by_count():
                    return

            while not self._stop_event.is_set():
                # 카운트다운
                for remaining in range(self._config.interval_seconds, 0, -1):
                    if self._stop_event.is_set():
                        reason = getattr(self, "_stop_reason", "user")
                        return
                    if self._on_tick:
                        try:
                            self._on_tick(remaining, self._run_count)
                        except Exception:
                            pass
                    time.sleep(1)

                if self._stop_event.is_set():
                    reason = getattr(self, "_stop_reason", "user")
                    return

                self._fire_once()
                if self._should_stop_by_count():
                    reason = "max_runs_reached"
                    return
        finally:
            if self._on_stop:
                try:
                    self._on_stop(reason)
                except Exception:
                    pass

    def _fire_once(self) -> None:
        try:
            self._run_count += 1
            self._on_run(self._run_count)
        except BaseException as exc:
            if self._on_error:
                try:
                    self._on_error(exc)
                except Exception:
                    pass

    def _should_stop_by_count(self) -> bool:
        return (
            self._config.max_runs is not None
            and self._run_count >= self._config.max_runs
        )
