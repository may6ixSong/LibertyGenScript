#!/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7/bin/python3
"""
main.py

generator 실행 진입점. 지금은 GUI 실행만 담당하지만,
향후 GUI 없이 config 파일만으로 실행하는 CLI 모드를 추가할 경우
이 파일에 분기만 추가하면 되고 gui_app.py 는 건드릴 필요 없음.

2026-08: 실제 liberty 생성 로직은 모두 step4_generate/ 밑으로 옮겨졌고,
core/(레거시, 미사용 OUTPUT_DIR 관리 코드)는 삭제됨.
"""

import sys

# 2026-10: 시작이 어디서 멈추는지 로그로 남긴다(ui/startup_trace.py 참고). PyQt/앱 모듈
# import보다 먼저 켜야 import 도중 멈춘 경우도 잡힌다.
from ui import startup_trace

startup_trace.install()
startup_trace.mark("importing app modules (PyQt5, step1~4)...")

from ui.gui_app import launch_gui  # noqa: E402

startup_trace.mark("app modules imported")


def main() -> int:
    return launch_gui()


if __name__ == "__main__":
    sys.exit(main())