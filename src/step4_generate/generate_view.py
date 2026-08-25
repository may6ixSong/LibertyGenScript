"""
generate_view.py

Step 4: Step2에서 유효하게 매칭된 pair 개수만큼 1초에 하나씩 실제 liberty 파일을
생성하며 진행 상황을 보여준다 (2026-08 전면 재설계 - UDC 항목 목록 대신 Step2의
자동 페어링 + Voltage Condition 선택값을 기반으로 job을 만든다). 결과는 파일
탐색기처럼 아이콘 그리드로 표시되고, 파일이 생성될 때마다 하나씩 페이드인 애니메이션
으로 나타난다.

liberty_writter.write_liberty_file()가 block1~5를 실제 파일에 쓴다.

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

from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step1_setup.port_list_reader import (
    list_port_bit_values, list_port_pins_detailed, list_power_ground_pins,
)
from step2_udc import udc_manager
from step2_udc.udc_field_defs import compute_pairs
from step3_settings import settings_manager
from step4_generate import liberty_assembler
from step4_generate.liberty_writter import write_liberty_file
from step4_generate.pdk_stream_reader import new_lut_sections, read_lut_table_sections
from ui.theme import ERROR_COLOR, SUCCESS_COLOR, TEXT_COLOR
from ui.ui_common import add_shadow

_GRID_COLUMNS = 6
_TICK_INTERVAL_MS = 1000


class _FileTile(QWidget):
    """파일 탐색기 아이콘 뷰 느낌의 타일 하나 (아이콘 + 파일명, 실패 시 다른 색/아이콘)."""

    def __init__(self, filename: str, success: bool, error_message: str = "", parent=None):
        super().__init__(parent)
        self.setFixedWidth(96)
        if error_message:
            self.setToolTip(error_message)

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

        name_label = QLabel(filename)
        name_label.setAlignment(Qt.AlignHCenter)
        name_label.setWordWrap(True)
        color = TEXT_COLOR if success else ERROR_COLOR
        name_label.setStyleSheet(f"font-size: 11px; color: {color};")
        layout.addWidget(name_label)

        self._opacity = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._opacity)
        self._opacity.setOpacity(0.0)
        self._anim = None

    def animate_in(self) -> None:
        anim = QPropertyAnimation(self._opacity, b"opacity", self)
        anim.setDuration(350)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.start()
        self._anim = anim  # 참조 유지 (GC 방지)


class GenerateView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
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

    def start(self, output_path: str, pdk_folder: str, dbs_folder: str, port_list_file: str) -> None:
        """
        생성을 시작. Step2의 pair(자동 페어링 + Voltage Condition 선택)를 다시 계산해서
        job을 만들고, 1초에 하나씩 실제 liberty 파일을 쓴다.

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
        pdk_files = list_pdk_lib_files(pdk_folder)
        dbs_files = list_dbs_mt0_files(dbs_folder)
        pair_result = compute_pairs(pdk_files, dbs_files)

        settings = settings_manager.load_settings()
        port_bit_values = list_port_bit_values(port_list_file)
        power_ground_pins = list_power_ground_pins(port_list_file)
        port_pins = list_port_pins_detailed(port_list_file)

        self._jobs, self._prep_errors = liberty_assembler.build_jobs(
            pair_result["pairs"], udc_state["pair_settings"], udc_state["common"],
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
            return

        if self._prep_errors:
            self.progress_label.setText(
                f"0 of {self._total} files generated "
                f"({len(self._prep_errors)} pair(s) skipped due to errors)"
            )
        else:
            self.progress_label.setText(f"0 of {self._total} files generated")

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
        tile = _FileTile(output_file.name, success, error_message or "")
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
            return

        self._schedule_tick(token, _TICK_INTERVAL_MS)

    def _generate_one(self, job: dict, output_file: Path) -> tuple[bool, str | None]:
        """job 하나를 실제 liberty 파일로 생성. (성공 여부, 에러 메시지)를 반환."""
        try:
            write_liberty_file(job, str(output_file), self._lut_sections)
        except Exception as e:  # noqa: BLE001 - Step4에서는 모든 실패를 화면에 보여줘야 함
            return False, str(e)
        return True, None
