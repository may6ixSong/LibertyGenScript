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

from ui.gui_app import launch_gui


def main() -> int:
    return launch_gui()


if __name__ == "__main__":
    sys.exit(main())