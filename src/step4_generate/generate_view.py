"""
generate_view.py

Step 4: Step2에서 유효하게 매칭된 pair 개수만큼 1초에 하나씩 실제 liberty 파일을
생성하며 진행 상황을 보여준다 (2026-08 전면 재설계 - UDC 항목 목록 대신 Step2의
자동 페어링 + Voltage Condition 선택값을 기반으로 job을 만든다). 결과는 파일
탐색기처럼 아이콘 그리드로 표시되고, 파일이 생성될 때마다 하나씩 페이드인 애니메이션
으로 나타난다.

liberty_writter.write_liberty_file()가 block1~5를 실제 파일에 쓴다.

2026-08 추가: 생성이 끝난 파일 아이콘을 클릭하면 그 파일이 **새 창**에서 vi/vim처럼
(어두운 배경 + 줄번호 + 상태줄, 읽기 전용) 열린다 (ui/file_viewer.py). 실제 vi/vim
프로세스를 띄우려면 터미널 에뮬레이터가 필요해 VWP 환경에서 보장할 수 없기 때문에,
앱 안에 같은 느낌의 뷰어 창을 직접 구현했다.

여러 liberty를 동시에 생성하지 않는다 - 1초 간격으로 pair를 하나씩 순차 처리하며,
각 tick에서 PDK 파일 하나만 열어서 순차로 읽는다.

2026-08 재설계 (성능): block3의 lu_table_template(index_1/index_2)은 pair마다 각자의
PDK에서 찾지 않고, Step3에서 고른 "Worst case primitive liberty" PDK 하나에서 생성을
시작할 때 딱 한 번 읽어(read_lut_table_sections) 모든 job에 그대로 재사용한다. 덕분에
각 tick의 PDK 읽기는 첫 `cell (...)` 선언 앞까지(파일의 극히 일부)로 끝난다.

2026-08 수정: 반복(QTimer.start()) 방식 대신, 매번 다음 tick을
QTimer.singleShot()으로 직접 다시 예약하는 방식으로 바꿨다 - 이전 tick이 끝난
시점부터 정확히 1초 뒤에 다음 tick이 잡히도록 보장하기 위해서다. 또한 타일을 하나
추가할 때마다 QApplication.processEvents()를 명시적으로 호출해서, 다음 tick으로
넘어가기 전에 그 타일이 반드시 화면에 그려지도록 강제한다 - 그렇지 않으면 환경에
따라 여러 타일의 repaint가 한꺼번에 몰려서 "한 번에 다 나타나는" 것처럼 보일 수
있다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QPropertyAnimation, QTimer, Qt
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QGridLayout, QLabel,
    QProgressBar, QScrollArea, QStyle, QVBoxLayout, QWidget,
)

from step1_setup.port_list_reader import (
    list_port_bit_values, list_port_pins_detailed, list_power_ground_pins,
)
from step2_udc import udc_manager
from step3_settings import settings_manager
from step4_generate import liberty_assembler
from step4_generate.liberty_writter import write_liberty_file
from step4_generate.pdk_stream_reader import new_lut_sections, read_lut_table_sections
from ui.file_viewer import open_file_viewer
from ui.theme import ERROR_COLOR, PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR
from ui.ui_common import add_shadow, build_back_button, build_bottom_button_row

# 2026-08: 파일명이 길어 타일 안에서 잘리지 않도록 타일을 넓히고 열 수를 줄였다.
_GRID_COLUMNS = 5
_TILE_WIDTH = 130
_TICK_INTERVAL_MS = 1000


class _FileTile(QWidget):
    """
    파일 탐색기 아이콘 뷰 느낌의 타일 하나 (아이콘 + 파일명, 실패 시 다른 색/아이콘).

    2026-08 추가: 생성에 성공한 타일을 클릭하면 그 파일을 vi/vim 스타일의 읽기 전용
    뷰어 창으로 연다 (on_open 콜백 -> GenerateView._open_file).
    """

    def __init__(
        self, filename: str, success: bool, error_message: str = "", file_path: str = "",
        on_open=None, parent=None,
    ):
        super().__init__(parent)
        self.setFixedWidth(_TILE_WIDTH)
        self.file_path = file_path
        self._on_open = on_open if success and file_path else None
        if error_message:
            self.setToolTip(f"{filename}\n{error_message}")
        elif self._on_open:
            self.setToolTip(f"{filename}\nClick to open in a new window (read-only)")
            self.setCursor(Qt.PointingHandCursor)
        else:
            self.setToolTip(filename)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignHCenter)
        layout.setSpacing(4)
        layout.setContentsMargins(4, 4, 4, 4)

        icon_label = QLabel()
        icon_type = QStyle.SP_FileIcon if success else QStyle.SP_MessageBoxWarning
        icon = QApplication.style().standardIcon(icon_type)
        icon_label.setPixmap(icon.pixmap(48, 48))
        icon_label.setAlignment(Qt.AlignHCenter)
        layout.addWidget(icon_label)

        # 파일명에는 공백이 없어서 QLabel의 word wrap이 먹지 않는다(밑줄은 줄바꿈
        # 지점이 아니라 한 줄에 다 못 들어가면 잘려 보인다). 밑줄 뒤에 zero-width
        # space를 넣어 줄바꿈이 가능하게 한다 - 표시만 바뀌고 파일명 자체는 그대로다.
        name_label = QLabel(filename.replace("_", "_\u200b"))
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)
        if not success:
            color = ERROR_COLOR
        elif self._on_open:
            color = PRIMARY_COLOR  # 클릭할 수 있다는 걸 알 수 있게 링크처럼 보이게
        else:
            color = TEXT_COLOR
        name_label.setStyleSheet(f"font-size: 11px; color: {color};")
        layout.addWidget(name_label)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)
        self._anim = None

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        if self._on_open and event.button() == Qt.LeftButton:
            self._on_open(self.file_path)
        super().mouseReleaseEvent(event)

    def animate_in(self) -> None:
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(350)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim  # 참조 유지 (GC 방지)


class GenerateView(QWidget):
    def __init__(self, on_back=None, parent=None):
        """
        Args:
            on_back: Back 버튼을 눌렀을 때 호출되는 콜백 (Step3으로 이동). 생성이
                진행 중인 동안에는 버튼이 잠기고, 끝나면 다시 열린다.
        """
        super().__init__(parent)
        self.on_back = on_back
        self._jobs: list[dict] = []
        self._prep_errors: list[str] = []
        # Step3에서 고른 worst case PDK에서 실행당 한 번만 읽는 lu_table_template 정보.
        # 모든 job이 이 동일한 결과를 그대로 쓴다.
        self._lut_sections: dict = new_lut_sections()
        self._output_path: str = ""
        self._total = 0
        self._done = 0
        self._failed = 0
        self._run_token = 0  # start()가 다시 호출돼도 이전 예약된 tick이 실행되지 않도록
        # 열려 있는 파일 뷰어 창들 (참조를 들고 있지 않으면 GC로 바로 닫힌다)
        self._viewers: list = []

        self._build_layout()

    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel("Generating Files")
        title.setObjectName("titleLabel")
        self.subtitle = QLabel("")
        self.subtitle.setObjectName("subtitleLabel")
        self.subtitle.setWordWrap(True)
        outer.addWidget(title)
        outer.addWidget(self.subtitle)

        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setSpacing(12)

        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setFixedHeight(14)
        card_layout.addWidget(self.progress_bar)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")
        card_layout.addWidget(self.progress_label)

        outer.addWidget(card)

        # 파일 탐색기 느낌의 아이콘 그리드
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_scroll.setWidget(self.grid_container)
        outer.addWidget(self.grid_scroll, stretch=1)

        self.back_btn = build_back_button(self.on_back)
        outer.addLayout(build_bottom_button_row(self.back_btn))

    def _set_running(self, running: bool) -> None:
        """
        생성이 진행되는 동안에는 Back을 잠근다 - 도중에 화면을 벗어나면 예약된 tick이
        어중간한 상태에서 파일을 계속 쓰게 되기 때문. 생성이 끝나면 다시 열려서 Step3으로
        돌아가 값을 고치고 다시 Generate할 수 있다.
        """
        self.back_btn.setEnabled(not running)
        self.back_btn.setToolTip("Generation in progress..." if running else "")

    def start(self, output_path: str, pdk_folder: str, dbs_folder: str, port_list_file: str) -> None:
        """
        생성을 시작. Step2의 liberty setting 목록을 다시 읽어 job을 만들고, 1초에 하나씩
        실제 liberty 파일을 쓴다. Step3에서 Back으로 돌아갔다가 다시 Generate를 눌러도
        이 함수가 처음부터 다시 실행되므로 몇 번이든 재생성할 수 있다.

        Args:
            pdk_folder: Step1에서 설정한 PDK Folder 경로
            dbs_folder: Step1에서 설정한 DBS Simulation Folder 경로
            port_list_file: Step1에서 설정한 Port List Excel 경로 (block3의 type_bus를
                             만드는 데 필요한 PORT 핀들의 Bits 값을 여기서 읽는다)
        """
        self._output_path = output_path
        self._done = 0
        self._failed = 0
        self._run_token += 1
        current_token = self._run_token

        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self.subtitle.setText(f"Output path: {output_path}")
        self.progress_label.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")

        udc_state = udc_manager.load_state()

        settings = settings_manager.load_settings()
        port_bit_values = list_port_bit_values(port_list_file)
        power_ground_pins = list_power_ground_pins(port_list_file)
        port_pins = list_port_pins_detailed(port_list_file)

        self._jobs, self._prep_errors = liberty_assembler.build_jobs(
            udc_manager.get_entries(udc_state), udc_state["common"],
            pdk_folder, dbs_folder, settings["scalars"], settings["voltage_map"], port_bit_values,
            power_ground_pins, settings["pins"], port_pins,
        )
        self._total = len(self._jobs)

        # worst case PDK의 lu_table_template을 여기서 딱 한 번만 읽는다 (job마다 다시
        # 읽지 않음). 실패해도 생성 자체를 막지는 않고, block3가 결측 주석으로 표시한다.
        self._load_lut_sections(pdk_folder, settings["scalars"])

        self.progress_bar.setMaximum(max(self._total, 1))
        self.progress_bar.setValue(0)

        if self._total == 0:
            self.progress_label.setStyleSheet(f"color: {ERROR_COLOR}; font-weight: 600;")
            message = "No valid UDC/liberty jobs to generate."
            if self._prep_errors:
                message += " " + "; ".join(self._prep_errors)
            self.progress_label.setText(message)
            self._set_running(False)
            return

        if self._prep_errors:
            self.progress_label.setText(
                f"0 of {self._total} files generated "
                f"({len(self._prep_errors)} pair(s) skipped due to errors)"
            )
        else:
            self.progress_label.setText(f"0 of {self._total} files generated")

        self._set_running(True)
        self._schedule_tick(current_token, 0)

    def _load_lut_sections(self, pdk_folder: str, scalars: dict) -> None:
        """
        Step3에서 고른 "Worst case primitive liberty" PDK를 한 번만 읽어 block3의
        lu_table_template(index_1/index_2)을 뽑아 둔다. 파일을 못 열면 예외를 던지지
        않고 빈 결과를 쓰며(=block3가 결측 주석으로 표시), 사유는 prep_errors에 남긴다.
        """
        self._lut_sections = new_lut_sections()
        worst_case_pdk = str(scalars.get("worst_case_pdk", "")).strip()
        if not worst_case_pdk:
            return

        worst_case_path = str(Path(pdk_folder) / worst_case_pdk)
        try:
            self._lut_sections = read_lut_table_sections(
                worst_case_path,
                str(scalars.get("dff_cell_name", "")).strip(),
                str(scalars.get("primitive_cell_name", "")).strip(),
            )
        except OSError as e:
            self._prep_errors.append(
                f"Failed to read the worst case primitive liberty '{worst_case_pdk}': {e}"
            )

    def _schedule_tick(self, token: int, delay_ms: int) -> None:
        QTimer.singleShot(delay_ms, lambda: self._on_tick(token))

    def _on_tick(self, token: int) -> None:
        # start()가 그 사이에 다시 호출됐다면(예: 화면을 벗어났다 다시 Generate를
        # 누른 경우) 이 예약은 더 이상 유효하지 않으므로 조용히 무시한다.
        if token != self._run_token:
            return
        if self._done >= self._total:
            return

        job = self._jobs[self._done]
        output_file = Path(self._output_path) / job["output_filename"]

        success, error_message = self._generate_one(job, output_file)

        self._done += 1
        if not success:
            self._failed += 1

        row, col = divmod(self._done - 1, _GRID_COLUMNS)
        tile = _FileTile(
            output_file.name, success, error_message or "", str(output_file), self._open_file,
        )
        self.grid_layout.addWidget(tile, row, col)
        tile.animate_in()

        self.progress_bar.setValue(self._done)
        if self._failed:
            self.progress_label.setStyleSheet(f"color: {ERROR_COLOR}; font-weight: 600;")
            self.progress_label.setText(
                f"{self._done} of {self._total} files generated ({self._failed} failed)"
            )
        else:
            self.progress_label.setText(f"{self._done} of {self._total} files generated")

        # 방금 추가한 타일이 다음 tick으로 넘어가기 전에 반드시 화면에 그려지도록
        # 강제한다 - 그렇지 않으면 여러 타일의 repaint가 한꺼번에 몰려서 마치
        # "한 번에 다 나타나는" 것처럼 보일 수 있다.
        QApplication.processEvents()

        if self._done >= self._total:
            if not self._failed:
                self.progress_label.setStyleSheet(f"color: {SUCCESS_COLOR}; font-weight: 700;")
                self.progress_label.setText(f"All {self._total} files generated.")
            self._set_running(False)
            return

        self._schedule_tick(token, _TICK_INTERVAL_MS)

    def _open_file(self, file_path: str) -> None:
        """
        타일을 클릭했을 때 그 liberty 파일을 새 창(읽기 전용 vim 스타일 뷰어)으로 연다.
        같은 파일을 여러 번 클릭하면 이미 열려 있는 창을 앞으로 가져온다.
        """
        for viewer in list(self._viewers):
            try:
                already_open = viewer.file_path == file_path and viewer.isVisible()
            except RuntimeError:  # 이미 닫혀서 C++ 객체가 사라진 경우
                self._viewers.remove(viewer)
                continue
            if already_open:
                viewer.raise_()
                viewer.activateWindow()
                return

        viewer = open_file_viewer(file_path, self.window())
        if viewer is not None:
            self._viewers.append(viewer)
            viewer.destroyed.connect(lambda _obj=None, v=viewer: self._forget_viewer(v))

    def _forget_viewer(self, viewer) -> None:
        if viewer in self._viewers:
            self._viewers.remove(viewer)

    def _generate_one(self, job: dict, output_file: Path) -> tuple[bool, str | None]:
        """job 하나를 실제 liberty 파일로 생성. (성공 여부, 에러 메시지)를 반환."""
        try:
            write_liberty_file(job, str(output_file), self._lut_sections)
        except Exception as e:  # noqa: BLE001 - Step4에서는 모든 실패를 화면에 보여줘야 함
            return False, str(e)
        return True, None
