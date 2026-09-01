"""
force_quit.py

Ctrl+C 강제 종료 (2026-08 추가).

Step1의 Port List 파싱, Step3의 Output Path 선택(파일 대화상자가 네트워크 폴더를
훑는 경우) 등 느린 동기 작업 중에 화면이 멈춘 것처럼 보이는 경우를 대비해, **어느
Step 화면에 있든 Ctrl+C를 누르면 즉시 프로세스를 강제 종료**한다 - 단, 텍스트 입력칸/
뷰어에 포커스가 있을 때는 예외다(아래 "텍스트 칸 포커스면 Ctrl+C를 복사로 그대로
통과" 참고 - 텍스트를 복사하려던 Ctrl+C까지 강제 종료로 오인되는 것을 막는다).

두 경로로 Ctrl+C를 받는다:
  1. GUI가 응답 가능한 상태(이벤트 루프가 돌고 있음)일 때: QApplication 전체에 건
     이벤트 필터(_CtrlCFilter)가 모든 KeyPress 이벤트를 검사해서 Ctrl+C를 직접
     잡아낸다. **처음에는 QShortcut(Ctrl+C, ApplicationShortcut)으로 구현했었지만,
     그 방식은 Qt가 내부적으로 판단하는 "활성 창(active window)" 상태에 의존하는데,
     일부 창관리자/X11 forwarding 조합에서는 창을 띄워도 이 내부 플래그가 세팅되지
     않아 단축키가 조용히 먹통이 되는 경우가 확인됐다(2026-08 - 실제 테스트에서
     재현). 이벤트 필터 방식은 그 판단을 거치지 않고 이 앱에 전달되는 모든 키
     이벤트를 직접 보므로 그런 환경 의존성이 없다.**
  2. 터미널에서 SIGINT(Ctrl+C)가 온 경우: signal.signal(SIGINT, ...)로 받는다.
     Qt의 C++ 이벤트 루프는 idle 대기 중에는 파이썬 바이트코드를 실행하지 않아
     시그널을 처리할 기회가 없으므로, 짧은 주기로 아무 일도 안 하는 QTimer를 돌려
     계속 파이썬에 제어권을 돌려준다(PyQt에서 SIGINT가 안 먹는 문제의 표준 우회법).

두 경우 모두 os._exit()로 즉시 하드킬한다 - "강제 종료"이므로 정리/저장을 시도하지
않고 그 자리에서 끝낸다. 도중에 파일을 쓰고 있었다면 중간 상태 파일이 남을 수 있다.

**한계 (완전히 해결되지 않는 부분)**: openpyxl로 큰 Excel 파일을 읽는 도중처럼
메인 스레드가 순수 파이썬 루프를 실행하는 중이면, 위 두 경로 모두 "다음 파이썬
바이트코드가 실행되는 시점"까지는 들어오지 못한다(Qt 이벤트 루프가 막혀 있으면
QShortcut도, 시그널 처리도 그 시점까지 대기). openpyxl 파싱은 대부분 순수 파이썬
루프라서 보통 수백ms~수 초 안에는 반응하지만, 완전한 즉시성은 무거운 파싱을 별도
스레드/프로세스로 옮겨야만 보장된다(이번 라운드 범위 밖 - 근본 원인 분석 참고).

2026-08 수정 - 텍스트 칸 포커스면 Ctrl+C를 복사로 그대로 통과: 이벤트 필터가 모든
Ctrl+C를 무조건 가로채면 텍스트 입력칸/뷰어(예: 생성된 liberty 파일을 읽기 전용으로
보여주는 file_viewer.py의 QPlainTextEdit)에서 텍스트를 복사하려고 누른 Ctrl+C까지
강제 종료로 오인된다. 그래서 이벤트를 가로채기 전에 **현재 포커스를 가진 위젯이
QLineEdit/QPlainTextEdit/QTextEdit(=`_COPY_TEXT_WIDGET_TYPES`)이면 그냥 통과**시켜
Qt의 기본 복사 동작이 그대로 실행되게 한다 - 그 외(버튼/목록 등에 포커스가 있거나,
포커스를 가진 위젯이 아예 없는 경우 - 진짜로 멈춘 것처럼 보일 때 포함)에는 예전과
동일하게 강제 종료한다. 이 예외는 이 앱의 이벤트 필터 안에서만 적용되고
(`install_force_quit`이 이 QApplication에만 필터를 건다), 터미널에서 오는
SIGINT(2번 경로)는 전혀 건드리지 않으므로 "정말 멈췄을 때 터미널에서 Ctrl+C로
강제 종료"라는 안전장치는 그대로 유지된다.
"""

from __future__ import annotations

import os
import signal
import sys

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtWidgets import QApplication, QLineEdit, QPlainTextEdit, QTextEdit, QWidget

_KEEPALIVE_MS = 200

# 이 위젯들에 포커스가 있을 때는 Ctrl+C를 강제 종료로 가로채지 않고 Qt 기본 복사
# 동작으로 통과시킨다(2026-08 추가) - 텍스트 입력칸(QLineEdit)과 읽기 전용 파일
# 뷰어(file_viewer.py의 QPlainTextEdit 서브클래스 _ViewerEdit 포함, QTextEdit도
# 방어적으로 포함)가 대상이다.
_COPY_TEXT_WIDGET_TYPES = (QLineEdit, QPlainTextEdit, QTextEdit)


def _force_quit(*_args) -> None:
    print("\n[Liberty Generator] Ctrl+C received - force quitting.", file=sys.stderr)
    sys.stderr.flush()
    os._exit(1)


class _CtrlCFilter(QObject):
    """
    QApplication 전체에 건 이벤트 필터. Qt::notify()를 거쳐 이 앱의 어느 위젯으로든
    전달되는 모든 KeyPress 이벤트를 필터가 먼저 보므로, 포커스가 어디에 있든(파일
    대화상자 포함) Ctrl+C를 놓치지 않는다 - QShortcut의 "활성 창" 판단에 기대지 않음.

    단, 현재 포커스를 가진 위젯이 텍스트 입력칸/뷰어(_COPY_TEXT_WIDGET_TYPES)면
    가로채지 않고 그대로 통과시킨다(2026-08 추가) - Qt의 기본 Ctrl+C 복사 동작이
    정상적으로 실행되도록.
    """

    def eventFilter(self, obj, event) -> bool:  # noqa: N802 - Qt 오버라이드 시그니처
        if event.type() == QEvent.KeyPress:
            if event.key() == Qt.Key_C and event.modifiers() & Qt.ControlModifier:
                if isinstance(QApplication.focusWidget(), _COPY_TEXT_WIDGET_TYPES):
                    return False
                _force_quit()
                return True
        return False


def install_force_quit(app: QApplication, window: QWidget) -> None:
    """
    앱 전체에 Ctrl+C 강제 종료를 연결한다. launch_gui()에서 QApplication/MainWindow를
    만든 직후 한 번만 호출하면 된다 - 이후 어떤 Step 화면이 떠 있든, 어떤 위젯에
    포커스가 있든(파일 대화상자 포함) 동일하게 동작한다.
    """
    # 1) GUI가 응답 가능한 동안: 앱 전역 이벤트 필터.
    ctrl_c_filter = _CtrlCFilter(app)
    app.installEventFilter(ctrl_c_filter)
    # 필터가 GC되면 사라지므로 참조를 app에 붙여 살려둔다.
    app._force_quit_event_filter = ctrl_c_filter  # noqa: SLF001 - 의도적 참조 유지

    # 2) 터미널에서 SIGINT(Ctrl+C)가 온 경우도 받는다 (run_generator.sh로 터미널에서
    #    실행했고, GUI 창이 아니라 터미널 쪽에 포커스가 있는 경우).
    signal.signal(signal.SIGINT, _force_quit)

    # Qt의 C++ 이벤트 루프는 idle 대기 중에는 파이썬 바이트코드를 실행하지 않아
    # 시그널을 처리할 기회가 없다 - 주기적으로 아무 일도 안 하는 타이머를 돌려
    # 파이썬에 제어권을 돌려준다 (PyQt에서 터미널 Ctrl+C가 안 먹는 문제의 표준 우회법).
    keepalive = QTimer()
    keepalive.setInterval(_KEEPALIVE_MS)
    keepalive.timeout.connect(lambda: None)
    keepalive.start()
    # 로컬 변수로만 두면 함수 종료 시 GC되어 타이머가 멈추므로, app에 참조를 붙여 둔다.
    app._force_quit_keepalive_timer = keepalive  # noqa: SLF001 - 의도적 참조 유지
