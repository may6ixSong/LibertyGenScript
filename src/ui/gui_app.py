"""
gui_app.py (PyQt5)

Liberty Generator 메인 윈도우. Step 1(Setup & Validate), Step 2(UDC Settings),
Step 3(Constants & Pin Settings), Step 4(Generate 진행률)를 QStackedWidget으로
전환하며 보여준다. 이후 단계가 추가되면 같은 방식으로 확장.

2026-08: Step2/3/4 전면 재설계에 맞춰 배선 변경 - Step4는 더 이상 Step2의 UDC 항목
목록을 직접 넘겨받지 않고, 필요한 순간(Generate 클릭 시)에 PDK/DBS 폴더 경로만 받아서
스스로 Step2/Step3 상태를 다시 읽어 pair/job을 계산한다.

2026-08 추가: Ctrl+C 강제 종료(ui/force_quit.py) - 큰 Port List Excel 파싱이나 파일
대화상자의 네트워크 폴더 탐색처럼 느린 동기 작업 중 화면이 멈춘 것처럼 보일 때, 어느
Step 화면에서든 Ctrl+C를 누르면 프로세스를 즉시 하드킬한다.

실행 환경 주의사항 (VWP):
  - PyQt5는 Anaconda Python 3.7.6 (/appl/CAEutil/LINUX/local/Anaconda/Anaconda3.7)
    에서만 사용 가능함이 확인됨.
  - 반드시 이 Anaconda python으로 실행할 것 (run_generator.sh 가 자동으로 처리함)
  - $DISPLAY 가 설정되어 있어야 함 (X11 forwarding 필요)
"""

import sys

from PyQt5.QtCore import QEvent, QObject, Qt, QTimer
from PyQt5.QtWidgets import QAbstractButton, QApplication, QMainWindow, QStackedWidget

from step1_setup import config_manager
from step1_setup.setup_view import SetupView
from step2_udc.udc_view import UDCView
from step3_settings.settings_view import SettingsView
from step4_generate.generate_view import GenerateView
from ui.force_quit import install_force_quit
from ui.loading_overlay import LoadingOverlay
from ui.theme import (
    APP_STYLESHEET, WINDOW_DEFAULT_HEIGHT, WINDOW_DEFAULT_WIDTH,
    WINDOW_MIN_HEIGHT, WINDOW_MIN_WIDTH,
)


class _PointerCursorFilter(QObject):
    """
    모든 버튼(QPushButton/QToolButton은 둘 다 QAbstractButton)에 pointer 커서를 적용.
    QSS의 cursor 속성이 이 환경의 Qt 버전에서 지원되지 않아("Unknown property cursor")
    이 전역 이벤트 필터 방식으로 대체함.
    """

    def eventFilter(self, obj, event) -> bool:
        if isinstance(obj, QAbstractButton) and event.type() in (
            QEvent.Show, QEvent.EnabledChange, QEvent.Polish,
        ):
            obj.setCursor(Qt.PointingHandCursor if obj.isEnabled() else Qt.ArrowCursor)
        return False


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Liberty Generator")
        # 2026-08 레이아웃 개편: Step3의 입력(특히 'Check DBS Output Pins' 버튼)이
        # 스크롤 없이 한 화면에 들어오도록 기본 창을 넓혔다.
        self.setMinimumSize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)
        self.resize(WINDOW_DEFAULT_WIDTH, WINDOW_DEFAULT_HEIGHT)

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        loaded = config_manager.load_config()
        self.setup_view = SetupView(
            loaded, self._on_config_changed, self._on_next, self._on_config_imported,
        )
        self.udc_view = self._new_udc_view()
        self.settings_view = self._new_settings_view()
        self.generate_view = GenerateView(self._on_generate_back)

        self.stack.addWidget(self.setup_view)
        self.stack.addWidget(self.udc_view)
        self.stack.addWidget(self.settings_view)
        self.stack.addWidget(self.generate_view)

        # 창 전체를 덮는 로딩 오버레이 (제일 마지막에 만들어야 다른 위젯들 위로 뜸)
        self.loading_overlay = LoadingOverlay(self)

        # 2026-08 추가: Step1 Port List 파싱, Step3 Output Path 선택(네트워크 폴더
        # 탐색) 등 느린 동기 작업 중 화면이 멈춘 것처럼 보일 때를 대비해, 어느 화면에
        # 있든 Ctrl+C를 누르면 즉시 강제 종료되도록 한다 (ui/force_quit.py 참고).
        install_force_quit(QApplication.instance(), self)

    def _new_udc_view(self) -> UDCView:
        return UDCView(
            self._get_pdk_folder, self._get_dbs_folder, self._on_udc_next, self._on_udc_back,
        )

    def _new_settings_view(self) -> SettingsView:
        return SettingsView(
            self._get_pdk_folder, self._get_dbs_folder, self._get_port_list_file,
            self._on_generate, self._show_loading, self._hide_loading, self._on_settings_back,
        )

    def _on_config_imported(self) -> None:
        """
        Step1의 Import Config로 config 3종 파일이 통째로 바뀐 뒤 호출된다. Step2/3
        화면(self.udc_view/self.settings_view)은 이미 생성 시점의(예전) config로
        만들어져 있어서 그 값을 그대로 들고 있으므로, 새로 만들어 갈아끼운다
        (2026-08 추가). 콜백들이 항상 self.udc_view/self.settings_view를 그때그때
        다시 읽으므로, 참조만 갈아끼우면 기존 배선(_on_udc_next 등)이 새 화면을 그대로
        가리키게 된다.
        """
        old_udc, old_settings = self.udc_view, self.settings_view
        current = self.stack.currentWidget()

        self.udc_view = self._new_udc_view()
        self.settings_view = self._new_settings_view()
        self.stack.addWidget(self.udc_view)
        self.stack.addWidget(self.settings_view)

        self.stack.removeWidget(old_udc)
        self.stack.removeWidget(old_settings)
        old_udc.deleteLater()
        old_settings.deleteLater()

        if current is old_udc:
            self.stack.setCurrentWidget(self.udc_view)
        elif current is old_settings:
            self.stack.setCurrentWidget(self.settings_view)
        else:
            self.stack.setCurrentWidget(current)

    def _on_config_changed(self, values: dict) -> None:
        config_manager.save_config(values)

    def _get_pdk_folder(self) -> str:
        return config_manager.load_config().get("pdk_folder", "")

    def _get_dbs_folder(self) -> str:
        return config_manager.load_config().get("dbs_folder", "")

    def _get_port_list_file(self) -> str:
        return config_manager.load_config().get("port_list_file", "")

    def _show_loading(self, text: str = "Loading...") -> None:
        self.loading_overlay.show_overlay(text)

    def _hide_loading(self) -> None:
        self.loading_overlay.hide_overlay()

    def _on_next(self) -> None:
        self.stack.setCurrentWidget(self.udc_view)

    def _on_udc_next(self) -> None:
        self._show_loading("Loading Constants & Pin Settings...")
        self.stack.setCurrentWidget(self.settings_view)
        self._hide_loading()

    def _on_udc_back(self) -> None:
        self.stack.setCurrentWidget(self.setup_view)

    def _on_settings_back(self) -> None:
        self.stack.setCurrentWidget(self.udc_view)

    def _on_generate_back(self) -> None:
        """
        Step4 -> Step3. Step3의 showEvent가 DBS output pin Check 결과를 무효화하므로,
        돌아오면 Check -> Validate -> Generate 순서를 처음부터 다시 밟게 된다
        (2026-08 확정). Generate를 다시 누르면 GenerateView.start()가 처음부터 다시
        실행되어 몇 번이든 재생성할 수 있다.
        """
        self.stack.setCurrentWidget(self.settings_view)

    def _on_generate(self, output_path: str) -> None:
        """
        Generate 클릭 시 화면이 멈춘 것처럼 보이지 않도록: 로딩 오버레이를 먼저
        띄우고 화면을 Step4로 전환한 뒤(이 시점까지는 즉각적), 실제로 시간이 걸릴 수
        있는 작업(폴더 재스캔 + Port List/PDK 읽어서 job 조립)은 아주 짧게 지연시켜
        오버레이가 실제로 한 번 그려지고 난 다음에 실행한다 - 그래야 Qt가 오버레이를
        화면에 그릴 기회를 먼저 갖는다(동기 코드라 그냥 이어서 실행하면 오버레이가
        뜨기도 전에 무거운 작업이 끝나버려 화면이 멈춘 것처럼 보임).
        """
        self._show_loading("Preparing to generate...")
        self.stack.setCurrentWidget(self.generate_view)
        QTimer.singleShot(50, lambda: self._start_generation(output_path))

    def _start_generation(self, output_path: str) -> None:
        self.generate_view.start(
            output_path, self._get_pdk_folder(), self._get_dbs_folder(), self._get_port_list_file(),
        )
        self._hide_loading()


def launch_gui() -> int:
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_STYLESHEET)
    cursor_filter = _PointerCursorFilter(app)
    app.installEventFilter(cursor_filter)
    window = MainWindow()
    window.show()
    return app.exec_()
