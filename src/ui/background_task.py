"""
background_task.py

메인(GUI) 스레드를 막지 않고, 시간이 걸릴 수 있는 함수(주로 큰 Port List Excel
파싱)를 백그라운드 스레드에서 실행하기 위한 작은 유틸리티 (2026-08 추가).

무거운 동기 호출을 그대로 GUI 스레드에서 실행하면 그동안 창이 완전히 멈춘 것처럼
보인다 - Qt 이벤트 루프가 아무것도 처리하지 못해서 화면도 안 그려지고, Ctrl+C 강제
종료(ui/force_quit.py)의 이벤트 필터 경로도 그 순간엔 반응하지 못한다(터미널 SIGINT는
여전히 먹힘). run_task()로 실제 작업을 QThread로 옮기면:
  - 창이 계속 응답한다(로딩 오버레이 애니메이션 포함, 다른 위젯 클릭도 무시되지 않음).
  - Ctrl+C 이벤트 필터도 작업 도중에 정상적으로 먹힌다(더 이상 터미널에만 의존할
    필요가 없어짐).
  - 작업이 끝나면 그 결과를 콜백으로 메인 스레드에 안전하게 넘겨준다 - PyQt는 발신
    객체와 수신 객체의 스레드가 다르면 시그널/슬롯 연결을 자동으로 큐잉된
    연결(QueuedConnection)로 처리하므로, on_success/on_error는 항상 메인(GUI)
    스레드에서 실행된다(직접 위젯을 만지는 코드를 그 안에 그대로 써도 안전함).

work_fn은 인자를 받지 않는 콜러블이어야 하고(필요한 값은 클로저로 미리 캡처), 예외를
던지면 on_error로 전달된다(예외를 삼키지 않고 화면에 보여줄 수 있도록).
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QObject, QThread, pyqtSignal


class _Worker(QObject):
    succeeded = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, work_fn: Callable[[], object]):
        super().__init__()
        self._work_fn = work_fn

    def run(self) -> None:
        try:
            result = self._work_fn()
        except Exception as e:  # noqa: BLE001 - 백그라운드 작업의 모든 실패를 화면에 보여줘야 함
            self.failed.emit(str(e))
            return
        self.succeeded.emit(result)


def run_task(
    parent: QObject,
    work_fn: Callable[[], object],
    on_success: Callable[[object], None],
    on_error: Callable[[str], None] | None = None,
) -> None:
    """
    work_fn()을 백그라운드 QThread에서 실행하고, 끝나면 on_success(result)(성공) 또는
    on_error(message)(실패, 지정 안 하면 조용히 무시)를 메인 스레드에서 호출한다.

    Args:
        parent: QThread/worker의 참조를 붙여 살려 둘, 호출부 화면 자신(self) 같은
            살아있는 QObject. 참조를 안 붙이면 작업이 끝나기 전에 스레드 객체가
            GC될 수 있다.
    """
    thread = QThread(parent)
    worker = _Worker(work_fn)
    worker.moveToThread(thread)

    def _cleanup() -> None:
        thread.quit()
        thread.wait()
        thread.deleteLater()
        worker.deleteLater()
        tasks = getattr(parent, "_background_tasks", None)
        if tasks is not None:
            tasks.discard(thread)

    def _on_success(result: object) -> None:
        _cleanup()
        on_success(result)

    def _on_failed(message: str) -> None:
        _cleanup()
        if on_error:
            on_error(message)

    thread.started.connect(worker.run)
    worker.succeeded.connect(_on_success)
    worker.failed.connect(_on_failed)
    thread.start()

    # thread가 GC되어 도중에 사라지지 않도록 parent에 참조를 붙여 둔다.
    if not hasattr(parent, "_background_tasks"):
        parent._background_tasks = set()
    parent._background_tasks.add(thread)
