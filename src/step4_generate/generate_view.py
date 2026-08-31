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

2026-08 추가: 화면을 liberty(왼쪽) / Convert 버튼(가운데) / db(오른쪽) 3분할로
재구성했다. Convert 버튼은 liberty 생성이 끝나고 성공한 파일이 1개 이상일 때만
활성화되고, 누르면 db_converter.run_make_db()(사내 lc_sub/lc_shell 배치 잡)를
백그라운드 스레드(ui/background_task.run_task)에서 실행한다 - liberty 생성 때와
같은 방식으로, 실제로 디스크에 .db 파일이 생기는 대로(폴링) 타일이 하나씩 나타나고
실패한 것도 별도로 표시된다. .lib 파일은 변환 후에도 지우지 않는다.

타일 그리드의 열 개수는 더 이상 고정 상수가 아니라 **그리드가 실제로 그려지는 폭**
(스크롤 영역의 viewport 너비)에서 매번 다시 계산한다(`_columns_for_width`) - 창을
리사이즈하면 `resizeEvent`가 짧은 디바운스 뒤 `_reflow_all_grids()`를 불러 이미
놓인 타일들도 새 열 개수에 맞게 다시 배치한다. 예전에는 5로 고정되어 있어서 창을
넓혀도 타일이 만들어질 당시의 폭 기준으로만 배치되고 남는 공간이 그대로 비어
보였다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import QPropertyAnimation, QTimer, Qt
from PyQt5.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout,
    QLabel, QProgressBar, QPushButton, QScrollArea, QStyle, QVBoxLayout, QWidget,
)

from step1_setup.port_list_reader import (
    list_all_pin_bit_info, list_port_bit_values, list_port_pins_detailed, list_power_ground_pins,
)
from step2_udc import udc_manager
from step3_settings import settings_manager
from step4_generate import db_converter, liberty_assembler
from step4_generate.liberty_writter import write_liberty_file
from step4_generate.pdk_stream_reader import new_lut_sections, read_lut_table_sections
from ui.background_task import run_task
from ui.file_viewer import open_file_viewer
from ui.theme import (
    BORDER_COLOR, ERROR_COLOR, MUTED_TEXT_COLOR, PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR,
)
from ui.ui_common import add_shadow, build_back_button, build_bottom_button_row

# 2026-08: 파일명이 길어 타일 안에서 잘리지 않도록 타일을 넓혔다. 열 개수는 더 이상
# 고정하지 않고 그리드의 실제 폭에서 계산한다(_columns_for_width).
_TILE_WIDTH = 130
_TICK_INTERVAL_MS = 1000
_DB_POLL_INTERVAL_MS = 700
_DB_SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]


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
        self._generating = False
        # 열려 있는 파일 뷰어 창들 (참조를 들고 있지 않으면 GC로 바로 닫힌다)
        self._viewers: list = []
        # 반응형 그리드용: 실제 배치된 타일들을 순서대로 들고 있다가, 열 개수가 바뀌면
        # (창 리사이즈) 전부 다시 배치한다.
        self._tiles: list[_FileTile] = []

        # --- db 변환(Convert) 관련 상태 (2026-08 추가) ---
        # liberty 생성에 성공한 job들만 담는다 - 실패한 job은 .lib 파일 자체가 없으므로
        # make_db.scr에 넣을 수 없다.
        self._succeeded_jobs: list[dict] = []
        self._db_tiles: list[_FileTile] = []
        # library_name -> job, 아직 .db 파일이 디스크에 나타나지 않은 것들. 폴링
        # 타이머가 이 dict을 보고 하나씩 비워가며 타일을 만든다.
        self._db_pending: dict[str, dict] = {}
        self._db_failed = 0
        self._db_running = False
        self._db_spinner_index = 0

        self._db_poll_timer = QTimer(self)
        self._db_poll_timer.setInterval(_DB_POLL_INTERVAL_MS)
        self._db_poll_timer.timeout.connect(self._poll_db_files)

        self._db_spinner_timer = QTimer(self)
        self._db_spinner_timer.setInterval(150)
        self._db_spinner_timer.timeout.connect(self._advance_db_spinner)

        # 창 리사이즈 중 매 픽셀마다 그리드를 다시 배치하지 않도록 짧게 디바운스한다.
        self._resize_debounce = QTimer(self)
        self._resize_debounce.setSingleShot(True)
        self._resize_debounce.setInterval(120)
        self._resize_debounce.timeout.connect(self._reflow_all_grids)

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

        # --- liberty(왼쪽) / Convert 버튼(가운데) / db(오른쪽) 3분할 (2026-08 추가) ---
        columns_row = QHBoxLayout()
        columns_row.setSpacing(16)

        left_column = QVBoxLayout()
        left_column.setSpacing(8)
        self.liberty_header = QLabel("Liberty Files")
        self.liberty_header.setObjectName("sectionLabel")
        left_column.addWidget(self.liberty_header)

        # 파일 탐색기 느낌의 아이콘 그리드
        self.grid_scroll = QScrollArea()
        self.grid_scroll.setWidgetResizable(True)
        self.grid_scroll.setFrameShape(QFrame.NoFrame)
        self.grid_container = QWidget()
        self.grid_layout = QGridLayout(self.grid_container)
        self.grid_layout.setSpacing(8)
        self.grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.grid_scroll.setWidget(self.grid_container)
        left_column.addWidget(self.grid_scroll, stretch=1)
        columns_row.addLayout(left_column, 1)

        columns_row.addWidget(self._build_vline())

        center_column = QVBoxLayout()
        center_column.setSpacing(10)
        center_column.setAlignment(Qt.AlignHCenter)
        center_column.addStretch(1)
        self.convert_btn = QPushButton("Convert to .db")
        self.convert_btn.setObjectName("primaryButton")
        self.convert_btn.setEnabled(False)
        self.convert_btn.setToolTip("Generate liberty files first.")
        self.convert_btn.clicked.connect(self._on_convert_clicked)
        center_column.addWidget(self.convert_btn)
        self.db_status_label = QLabel("")
        self.db_status_label.setWordWrap(True)
        self.db_status_label.setAlignment(Qt.AlignHCenter)
        self.db_status_label.setFixedWidth(150)
        self.db_status_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        center_column.addWidget(self.db_status_label)
        center_column.addStretch(1)
        columns_row.addLayout(center_column)

        columns_row.addWidget(self._build_vline())

        right_column = QVBoxLayout()
        right_column.setSpacing(8)
        self.db_header = QLabel("DB Files")
        self.db_header.setObjectName("sectionLabel")
        right_column.addWidget(self.db_header)

        self.db_progress_bar = QProgressBar()
        self.db_progress_bar.setMinimum(0)
        self.db_progress_bar.setMaximum(1)
        self.db_progress_bar.setTextVisible(False)
        self.db_progress_bar.setFixedHeight(10)
        right_column.addWidget(self.db_progress_bar)

        self.db_progress_label = QLabel("")
        self.db_progress_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        right_column.addWidget(self.db_progress_label)

        self.db_grid_scroll = QScrollArea()
        self.db_grid_scroll.setWidgetResizable(True)
        self.db_grid_scroll.setFrameShape(QFrame.NoFrame)
        self.db_grid_container = QWidget()
        self.db_grid_layout = QGridLayout(self.db_grid_container)
        self.db_grid_layout.setSpacing(8)
        self.db_grid_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.db_grid_scroll.setWidget(self.db_grid_container)
        right_column.addWidget(self.db_grid_scroll, stretch=1)
        columns_row.addLayout(right_column, 1)

        outer.addLayout(columns_row, stretch=1)

        self.back_btn = build_back_button(self.on_back)
        outer.addLayout(build_bottom_button_row(self.back_btn))

    @staticmethod
    def _build_vline() -> QFrame:
        divider = QFrame()
        divider.setFrameShape(QFrame.VLine)
        divider.setStyleSheet(f"color: {BORDER_COLOR};")
        return divider

    def _update_back_lock(self) -> None:
        """
        liberty 생성 또는 db 변환이 진행되는 동안에는 Back을 잠근다 - 생성 도중에는
        예약된 tick이 어중간한 상태에서 파일을 계속 쓰게 되고, 변환 도중에는
        백그라운드에서 도는 lc_sub 잡과 화면 상태가 어긋날 수 있기 때문. 둘 다 끝나면
        다시 열린다.
        """
        locked = self._generating or self._db_running
        if self._generating:
            tooltip = "Generation in progress..."
        elif self._db_running:
            tooltip = "DB conversion in progress..."
        else:
            tooltip = ""
        self.back_btn.setEnabled(not locked)
        self.back_btn.setToolTip(tooltip)

    def _set_running(self, running: bool) -> None:
        self._generating = running
        self._update_back_lock()

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

        self._clear_layout(self.grid_layout)
        self._tiles = []
        self._succeeded_jobs = []
        self.liberty_header.setText("Liberty Files")

        # 재생성(다시 Generate) 대비 db 변환 쪽 상태도 초기화한다. Back 버튼이 변환
        # 도중에는 잠겨 있어 이 경로로 재진입할 일은 없지만, 안전하게 타이머도 멈춘다.
        self._db_poll_timer.stop()
        self._db_spinner_timer.stop()
        self._clear_layout(self.db_grid_layout)
        self._db_tiles = []
        self._db_pending = {}
        self._db_failed = 0
        self._db_running = False
        self.db_header.setText("DB Files")
        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("Convert to .db")
        self.convert_btn.setToolTip("Generate liberty files first.")
        self.db_progress_bar.setMaximum(1)
        self.db_progress_bar.setValue(0)
        self.db_progress_label.setText("")
        self.db_status_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        self.db_status_label.setText("")

        self.subtitle.setText(f"Output path: {output_path}")
        self.progress_label.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")

        udc_state = udc_manager.load_state()

        settings = settings_manager.load_settings()
        port_bit_values = list_port_bit_values(port_list_file)
        power_ground_pins = list_power_ground_pins(port_list_file)
        port_pins = list_port_pins_detailed(port_list_file)
        # DBS output pin bit 분할(2026-08 추가)이 Related Pin의 Bits/범위를 찾는 데
        # 쓴다 - Port 타입 무관 전체 pin을 본다(list_port_pins_detailed는 PORT만).
        pin_bit_info = list_all_pin_bit_info(port_list_file)

        self._jobs, self._prep_errors = liberty_assembler.build_jobs(
            udc_manager.get_entries(udc_state), udc_state["common"],
            pdk_folder, dbs_folder, settings["scalars"], settings["voltage_map"], port_bit_values,
            power_ground_pins, settings["pins"], port_pins, pin_bit_info,
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
        if success:
            self._succeeded_jobs.append(job)
        else:
            self._failed += 1

        tile = _FileTile(
            output_file.name, success, error_message or "", str(output_file), self._open_file,
        )
        self._tiles.append(tile)
        self._reflow_grid(self.grid_scroll, self.grid_layout, self._tiles)
        tile.animate_in()
        self.liberty_header.setText(f"Liberty Files ({self._done})")

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
            self.convert_btn.setEnabled(bool(self._succeeded_jobs))
            self.convert_btn.setToolTip(
                "" if self._succeeded_jobs else "No liberty files were generated."
            )
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

    # ------------------------------------------------------------------
    # 반응형 그리드 (2026-08 추가): 타일 열 개수를 고정 상수 대신 그리드가 실제로
    # 그려지는 폭(viewport)에서 계산한다.
    # ------------------------------------------------------------------
    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _columns_for_width(self, width: int) -> int:
        unit = _TILE_WIDTH + self.grid_layout.spacing()
        if unit <= 0:
            return 1
        return max(1, width // unit)

    def _reflow_grid(self, scroll_area: QScrollArea, grid_layout: QGridLayout, tiles: list) -> None:
        """tiles 순서 그대로, 지금 scroll_area의 실제 폭에 맞는 열 개수로 다시 배치한다."""
        columns = self._columns_for_width(scroll_area.viewport().width())
        for index, tile in enumerate(tiles):
            row, col = divmod(index, columns)
            grid_layout.removeWidget(tile)
            grid_layout.addWidget(tile, row, col)

    def _reflow_all_grids(self) -> None:
        self._reflow_grid(self.grid_scroll, self.grid_layout, self._tiles)
        self._reflow_grid(self.db_grid_scroll, self.db_grid_layout, self._db_tiles)

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().resizeEvent(event)
        # 리사이즈 도중 매 이벤트마다 다시 배치하지 않도록 짧게 디바운스한다.
        self._resize_debounce.start()

    # ------------------------------------------------------------------
    # db 변환 (2026-08 추가): liberty 생성이 끝나고 성공한 파일이 있으면 Convert
    # 버튼이 열린다. 실제 lc_sub/lc_shell 잡은 백그라운드 스레드에서 돌리고, 그동안
    # 폴링 타이머가 output 폴더에 .db 파일이 생기는 대로 하나씩 타일로 보여준다.
    # .lib 파일은 이 과정에서 전혀 건드리지 않는다(지우지 않음).
    # ------------------------------------------------------------------
    def _on_convert_clicked(self) -> None:
        if not self._succeeded_jobs or self._db_running:
            return

        self._db_running = True
        self._update_back_lock()
        self.convert_btn.setEnabled(False)
        self.convert_btn.setText("Converting…")

        self._clear_layout(self.db_grid_layout)
        self._db_tiles = []
        self._db_failed = 0
        self.db_header.setText("DB Files")
        self._db_pending = {job["library_name"]: job for job in self._succeeded_jobs}

        total = len(self._succeeded_jobs)
        self.db_progress_bar.setMaximum(total)
        self.db_progress_bar.setValue(0)
        self.db_progress_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        self.db_progress_label.setText(f"0 of {total} db files converted")

        self._db_spinner_index = 0
        self.db_status_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-weight: 600; font-size: 11px;")
        self._advance_db_spinner()
        self._db_spinner_timer.start()

        output_path = self._output_path
        library_names = [job["library_name"] for job in self._succeeded_jobs]

        def work() -> tuple[int, str]:
            return db_converter.run_make_db(output_path, library_names)

        self._db_poll_timer.start()
        run_task(self, work, self._on_convert_finished, self._on_convert_error)

    def _advance_db_spinner(self) -> None:
        frame = _DB_SPINNER_FRAMES[self._db_spinner_index]
        self._db_spinner_index = (self._db_spinner_index + 1) % len(_DB_SPINNER_FRAMES)
        self.db_status_label.setText(
            f"{frame} Running lc_shell (lc_sub job)...\nthis can take a while."
        )

    def _poll_db_files(self) -> None:
        """output 폴더를 훑어 아직 안 만든 .db 중 새로 생긴 게 있으면 타일로 추가한다."""
        if not self._db_pending:
            return
        output_dir = Path(self._output_path)
        for library_name in list(self._db_pending.keys()):
            db_path = output_dir / f"{library_name}.db"
            if db_path.exists() and db_path.stat().st_size > 0:
                job = self._db_pending.pop(library_name)
                self._add_db_tile(job, True)

    def _add_db_tile(self, job: dict, success: bool, error_message: str = "") -> None:
        db_filename = f"{job['library_name']}.db"
        # on_open을 안 넘긴다 - .db는 바이너리라 liberty 뷰어(텍스트 전용)로 열 수 없다.
        tile = _FileTile(db_filename, success, error_message)
        if not success:
            self._db_failed += 1
        self._db_tiles.append(tile)
        self._reflow_grid(self.db_grid_scroll, self.db_grid_layout, self._db_tiles)
        tile.animate_in()
        self.db_header.setText(f"DB Files ({len(self._db_tiles)})")

        done = len(self._db_tiles)
        total = len(self._succeeded_jobs)
        self.db_progress_bar.setValue(done)
        if self._db_failed:
            self.db_progress_label.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            self.db_progress_label.setText(
                f"{done} of {total} db files converted ({self._db_failed} failed)"
            )
        else:
            self.db_progress_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
            self.db_progress_label.setText(f"{done} of {total} db files converted")

    def _finish_convert(self, log_path: str = "", error_message: str = "") -> None:
        self._db_poll_timer.stop()
        self._db_spinner_timer.stop()

        # 잡이 끝났는데도 여전히 안 만들어진 .db가 있으면 실패로 표시한다.
        for library_name, job in list(self._db_pending.items()):
            self._db_pending.pop(library_name)
            reason = error_message or (
                f"lc_shell did not produce this .db file. See {log_path}."
                if log_path else "lc_shell did not produce this .db file."
            )
            self._add_db_tile(job, False, reason)

        self._db_running = False
        self._update_back_lock()
        self.convert_btn.setText("Convert to .db")
        self.convert_btn.setEnabled(True)

        total = len(self._succeeded_jobs)
        if error_message:
            self.db_status_label.setStyleSheet(f"color: {ERROR_COLOR}; font-weight: 600; font-size: 11px;")
            self.db_status_label.setText(f"Conversion failed: {error_message}")
        elif self._db_failed:
            self.db_status_label.setStyleSheet(f"color: {ERROR_COLOR}; font-weight: 600; font-size: 11px;")
            self.db_status_label.setText(f"{self._db_failed} of {total} failed. Log: {log_path}")
        else:
            self.db_status_label.setStyleSheet(f"color: {SUCCESS_COLOR}; font-weight: 700; font-size: 11px;")
            self.db_status_label.setText(f"All {total} .db files converted.")

    def _on_convert_finished(self, result: tuple[int, str]) -> None:
        _returncode, log_path = result
        self._finish_convert(log_path=log_path)

    def _on_convert_error(self, message: str) -> None:
        self._finish_convert(error_message=message)
