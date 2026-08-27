"""
setup_view.py

'Setup & Validate' 화면: PDK 폴더 + Port List 엑셀 파일 + DBS 폴더 입력을 받고,
Validate 버튼으로 3단계(PDK -> Port List -> DBS)를 순서대로 검사한다.
각 단계는 상단 가로 스텝 인디케이터에 진행 상태(pending/running/success/error)로
표시되고, 세부 메시지는 하단 Details 패널(읽기 전용, 선택 불가)에 나열된다.
모든 단계가 통과하면 Next 버튼이 활성화된다.

2026-08 성능 개선: port_list 단계는 큰 Excel 파일을 열 수 있어 느릴 수 있으므로
`ui/background_task.py`의 `run_task()`로 백그라운드 스레드에서 돌린다 - 그동안에도
창이 계속 응답하고 Ctrl+C 강제 종료(ui/force_quit.py)도 즉시 먹힌다. `_validate_run_token`
으로 재진입(그 사이 Validate를 다시 누르거나 화면을 벗어난 경우)을 감지해 오래된
실행의 결과가 새 실행의 화면 상태를 덮어쓰지 않게 막는다. Port List 파싱 자체는
`port_list_reader.py`가 파일당 캐싱 + 조기 종료 규칙으로 이미 크게 빨라져 있다
(자세한 내용은 src/CLAUDE.md의 "Port List 파싱 성능 최적화" 절 참고).
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from step1_setup import config_manager
from step1_setup.field_defs import (
    INPUT_PATH_FIELDS, PORT_LIST_FILE_EXTENSIONS, is_port_list_filename,
)
from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step1_setup.port_list_reader import read_port_list
from ui.theme import (
    BORDER_COLOR, ERROR_COLOR, MUTED_TEXT_COLOR, PENDING_COLOR,
    PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR,
)
from ui.background_task import run_task
from ui.ui_common import (
    DetailsList, add_shadow, build_section_header, run_export_config_dialog,
    run_import_config_dialog,
)

# 2026-08 순서 변경: 화면의 입력 순서(PDK Folder -> Port List -> DBS Simulation)와
# Validate 단계 순서를 동일하게 맞춘다 (field_defs.INPUT_PATH_FIELDS 참고).
STEP_DEFS = [
    ("pdk", "PDK Folder"),
    ("port_list", "Port List"),
    ("dbs", "DBS Simulation"),
]

_STEP_DELAY_MS = 350

# 2026-08 레이아웃 개편: 예전에는 이 문구를 노란 배너로 화면에 깔아뒀지만, 세로 공간만
# 차지해서 "Input Paths" 제목 옆 hover 정보 아이콘의 툴팁으로 옮겼다.
_INPUT_PATHS_INFO = (
    "The PDK Folder must contain only files whose extension starts with .lib "
    "(e.g. .lib, .lib_css_tn), and the DBS Simulation Folder must contain only .mt0 files.\n\n"
    "Extra files may lead to incorrect results.\n\n"
    "The Port List must be an "
    + " / ".join(PORT_LIST_FILE_EXTENSIONS)
    + " file."
)


class _StepChip(QWidget):
    """단계 하나를 나타내는 원형 인디케이터 + 제목 + 짧은 결과 요약."""

    _STATE_COLORS = {
        "pending": PENDING_COLOR,
        "running": PRIMARY_COLOR,
        "success": SUCCESS_COLOR,
        "error": ERROR_COLOR,
    }
    _STATE_SYMBOLS = {
        "pending": None,  # 인덱스 숫자를 그대로 사용
        "running": "\u22EF",
        "success": "\u2713",
        "error": "\u2715",
    }

    def __init__(self, index: int, title: str, parent=None):
        super().__init__(parent)
        self.index = index

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignHCenter)

        self.circle = QLabel(str(index))
        self.circle.setFixedSize(36, 36)
        self.circle.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.circle, alignment=Qt.AlignHCenter)

        self.title_label = QLabel(title)
        self.title_label.setAlignment(Qt.AlignHCenter)
        self.title_label.setStyleSheet(f"font-weight: 600; color: {TEXT_COLOR};")
        layout.addWidget(self.title_label)

        self.detail_label = QLabel("")
        self.detail_label.setAlignment(Qt.AlignHCenter)
        self.detail_label.setWordWrap(True)
        self.detail_label.setFixedWidth(170)
        self.detail_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(self.detail_label)

        self.set_state("pending")

    def set_state(self, state: str, detail: str = "") -> None:
        color = self._STATE_COLORS.get(state, PENDING_COLOR)
        self.circle.setStyleSheet(
            f"background-color: {color}; color: white; border-radius: 18px; "
            f"font-weight: 700; font-size: 14px;"
        )
        symbol = self._STATE_SYMBOLS.get(state)
        self.circle.setText(symbol if symbol else str(self.index))
        self.detail_label.setText(detail)


class _StepLine(QFrame):
    """스텝 사이를 잇는 연결선. 왼쪽 스텝의 진행 상태에 따라 색이 바뀜."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(2)
        self.set_status("pending")

    def set_status(self, status: str) -> None:
        color = {"success": SUCCESS_COLOR, "error": ERROR_COLOR}.get(status, BORDER_COLOR)
        self.setStyleSheet(f"background-color: {color}; border: none;")


class SetupView(QWidget):
    def __init__(
        self, existing_config: dict, on_config_changed, on_next=None,
        on_config_imported=None, parent=None,
    ):
        """
        Args:
            existing_config: 저장된 입력 경로 값
            on_config_changed: 값이 바뀔 때 저장을 요청하는 콜백(dict) -> None
            on_next: 모든 단계 통과 후 Next 버튼을 눌렀을 때 호출되는 콜백(선택)
            on_config_imported: Import Config로 config 3종이 통째로 바뀐 뒤 호출되는
                콜백(선택) - Step2/3 화면이 이미 예전 config로 만들어져 있으므로, 그
                화면들을 새로 만들어 반영하도록 상위(MainWindow)에 알린다.
        """
        super().__init__(parent)
        self.on_config_changed = on_config_changed
        self.on_next = on_next
        self.on_config_imported = on_config_imported
        self.path_edits: dict[str, QLineEdit] = {}
        self.step_chips: dict[str, _StepChip] = {}
        self.step_lines: list[_StepLine] = []
        self._all_passed = False
        self._details_anim = None  # QPropertyAnimation 참조 유지용 (GC 방지)
        # 2026-08 추가: port_list 단계가 백그라운드 스레드로 도는 동안에도 창이
        # 응답하므로, 그 사이 Validate를 다시 누르면(재진입) 이전 실행의 백그라운드
        # 결과가 나중에 도착해 새 실행의 화면 상태를 덮어쓸 수 있다. 매 Validate
        # 실행마다 토큰을 새로 발급해서, 완료 콜백이 지금 실행과 다른 토큰이면
        # 조용히 무시한다(GenerateView._run_token과 같은 패턴).
        self._validate_run_token = 0

        self._build_layout(existing_config)
        self._update_validate_button_state()

    # ------------------------------------------------------------------
    # 레이아웃
    # ------------------------------------------------------------------
    def _build_layout(self, existing_config: dict) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        title = QLabel("Liberty Generator")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Set up your input paths, then validate before generating.")
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        outer.addWidget(self._build_input_card(existing_config))
        outer.addLayout(self._build_action_row())
        outer.addWidget(self._build_steps_card())

        details_label = QLabel("Details")
        details_label.setObjectName("sectionLabel")
        outer.addWidget(details_label)
        outer.addWidget(self._build_details_list(), stretch=1)

    def _build_input_card(self, existing_config: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        card_layout = QGridLayout(card)
        card_layout.setContentsMargins(20, 20, 20, 20)
        card_layout.setHorizontalSpacing(10)
        card_layout.setVerticalSpacing(12)

        card_layout.addWidget(build_section_header("Input Paths", _INPUT_PATHS_INFO), 0, 0, 1, 3)

        for row, (key, label, kind, extensions) in enumerate(INPUT_PATH_FIELDS, start=1):
            card_layout.addWidget(QLabel(label), row, 0)

            edit = QLineEdit(existing_config.get(key, ""))
            edit.textChanged.connect(self._update_validate_button_state)
            self.path_edits[key] = edit
            card_layout.addWidget(edit, row, 1)

            btn = QPushButton("Browse...")
            btn.clicked.connect(
                lambda _checked, k=key, lbl=label, kd=kind, ext=extensions, e=edit:
                self._browse(k, lbl, kd, ext, e)
            )
            card_layout.addWidget(btn, row, 2)

        card_layout.setColumnStretch(1, 1)
        return card

    def _build_action_row(self) -> QHBoxLayout:
        btn_row = QHBoxLayout()

        self.export_btn = QPushButton("Export Config")
        self.export_btn.clicked.connect(self._on_export_config)
        btn_row.addWidget(self.export_btn)

        self.import_btn = QPushButton("Import Config")
        self.import_btn.clicked.connect(self._on_import_config)
        btn_row.addWidget(self.import_btn)

        btn_row.addStretch()

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.setObjectName("primaryButton")
        self.validate_btn.clicked.connect(self._on_validate)
        btn_row.addWidget(self.validate_btn)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("primaryButton")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._on_next_clicked)
        btn_row.addWidget(self.next_btn)

        return btn_row

    def _build_steps_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(0)

        self.step_chips = {}
        self.step_lines = []

        for i, (key, label) in enumerate(STEP_DEFS):
            chip = _StepChip(i + 1, label)
            self.step_chips[key] = chip
            layout.addWidget(chip)

            if i < len(STEP_DEFS) - 1:
                line = _StepLine()
                self.step_lines.append(line)
                layout.addWidget(line, stretch=1)

        return card

    def _build_details_list(self) -> DetailsList:
        self.details_list = DetailsList()
        return self.details_list

    # ------------------------------------------------------------------
    # 입력 처리
    # ------------------------------------------------------------------
    def _browse(self, key: str, label: str, kind: str, extensions, edit: QLineEdit) -> None:
        # DontUseNativeDialog(2026-08 추가): OS 고유 대화상자는 네트워크 폴더를 훑느라
        # 느릴 수 있고, 이 앱의 Ctrl+C 강제 종료 단축키(ui/force_quit.py)가 닿지 않는
        # 별도 창이라 열려 있는 동안은 먹히지 않는다. Qt 자체 대화상자를 쓰면 같은 이벤트
        # 루프 안에서 열리므로 열려 있는 동안에도 Ctrl+C가 그대로 동작한다.
        #
        # 시작 폴더(2026-08 추가): 힌트 없이 열면 OS/Qt가 마지막 사용 위치나 홈
        # 디렉터리(사내 HPC망에서는 대개 네트워크 마운트)부터 훑어야 해서 대화상자를
        # 여는 것 자체가 느려질 수 있다. 이미 입력돼 있는 값(재선택)이나 이미 채워진
        # 다른 입력 경로의 폴더를 우선 힌트로 준다 - 사용자가 최근에 실제로 접근했다고
        # 확인된 위치이므로 훑기 자체가 느릴 가능성이 낮다.
        start_dir = self._browse_start_dir(edit)
        if kind == "dir":
            path = QFileDialog.getExistingDirectory(
                self, f"Select {label}", start_dir, QFileDialog.DontUseNativeDialog,
            )
        else:
            filter_str = (
                f"Excel Files ({' '.join('*' + ext for ext in extensions)})"
                if extensions else "All Files (*)"
            )
            path, _ = QFileDialog.getOpenFileName(
                self, f"Select {label}", start_dir, filter_str,
                options=QFileDialog.DontUseNativeDialog,
            )
        if path:
            edit.setText(path)

    def _browse_start_dir(self, edit: QLineEdit) -> str:
        """
        파일 대화상자를 열 시작 폴더 힌트. 이미 채워진 경로가 있으면 그 폴더를,
        없으면 이미 채워진 다른 입력 경로(폴더면 그대로, 파일이면 부모 폴더)를 쓴다 -
        전부 비어 있으면 빈 문자열(OS/Qt 기본값)로 둔다.
        """
        current = edit.text().strip()
        if current:
            path = Path(current)
            return str(path if path.is_dir() else path.parent)

        for other_edit in self.path_edits.values():
            if other_edit is edit:
                continue
            value = other_edit.text().strip()
            if not value:
                continue
            path = Path(value)
            if path.is_dir():
                return str(path)
            if path.is_file():
                return str(path.parent)
        return ""

    def _update_validate_button_state(self) -> None:
        values = self._current_values()
        port_list_file = values.get("port_list_file", "")
        valid_extension = is_port_list_filename(port_list_file)
        all_filled = all(values.values())
        self.validate_btn.setEnabled(all_filled and valid_extension)
        self.next_btn.setEnabled(False)

    def _current_values(self) -> dict:
        return {key: edit.text().strip() for key, edit in self.path_edits.items()}

    # ------------------------------------------------------------------
    # Details 패널
    # ------------------------------------------------------------------
    def _clear_details(self) -> None:
        self.details_list.clear()

    def _add_detail(self, message: str, status: str = "info") -> None:
        self.details_list.add_message(message, status)

    def _animate_details_in(self) -> None:
        self.details_list.animate_in()

    @staticmethod
    def _truncate(text: str, limit: int = 42) -> str:
        return text if len(text) <= limit else text[: limit - 1] + "\u2026"

    # ------------------------------------------------------------------
    # 단계별 검사 로직 (GUI 상태와 분리된 순수 판단 부분)
    # ------------------------------------------------------------------
    def _evaluate_step(self, step_key: str) -> tuple[bool, list[tuple[str, str]]]:
        values = self._current_values()

        if step_key == "pdk":
            folder = values["pdk_folder"]
            if not Path(folder).is_dir():
                return False, [(f"PDK Folder does not exist: {folder}", "error")]
            lib_files = list_pdk_lib_files(folder)
            status = "success" if lib_files else "error"
            return bool(lib_files), [(f"{len(lib_files)} .lib file(s) found", status)]

        if step_key == "dbs":
            folder = values["dbs_folder"]
            if not Path(folder).is_dir():
                return False, [(f"DBS Simulation Folder does not exist: {folder}", "error")]
            mt0_files = list_dbs_mt0_files(folder)
            status = "success" if mt0_files else "error"
            return bool(mt0_files), [(f"{len(mt0_files)} .mt0 file(s) found", status)]

        if step_key == "port_list":
            file_path = values["port_list_file"]
            if not Path(file_path).is_file():
                return False, [(f"Port List file does not exist: {file_path}", "error")]

            try:
                result = read_port_list(file_path)
            except Exception as e:  # noqa: BLE001 - Validate 화면에서는 모든 예외를 표시해야 함
                return False, [(f"Failed to read Port List file: {e}", "error")]

            if result["sheet_name"] is None:
                return False, [("No sheet found with a name containing 'Port list'.", "error")]

            passed = True
            messages: list[tuple[str, str]] = [
                (
                    f"Sheet found: '{result['sheet_name']}' (header row {result['header_row']})",
                    "success",
                )
            ]

            if result["missing_required_columns"]:
                messages.append((
                    "Missing required column(s): " + ", ".join(result["missing_required_columns"]),
                    "error",
                ))
                passed = False

            for row_error in result["row_errors"]:
                messages.append((row_error, "error"))
                passed = False

            if result["port_count"] == 0:
                passed = False
            messages.append((
                f"{result['port_count']} port(s) found",
                "success" if result["port_count"] > 0 else "error",
            ))

            return passed, messages

        return False, [("Unknown step.", "error")]

    # ------------------------------------------------------------------
    # Validate: 3단계를 순서대로(A -> B -> C) 처리
    # ------------------------------------------------------------------
    def _on_validate(self) -> None:
        self.on_config_changed(self._current_values())
        self._clear_details()
        self.next_btn.setEnabled(False)
        self._all_passed = True
        self._validate_run_token += 1

        for chip in self.step_chips.values():
            chip.set_state("pending")
        for line in self.step_lines:
            line.set_status("pending")

        self._run_step_at(0, self._validate_run_token)

    def _run_step_at(self, index: int, token: int) -> None:
        if token != self._validate_run_token:
            return  # 그 사이 Validate가 다시 눌려 이 실행은 더 이상 유효하지 않음
        if index >= len(STEP_DEFS):
            self._finish_validation()
            return

        step_key, _ = STEP_DEFS[index]
        self.step_chips[step_key].set_state("running")
        QTimer.singleShot(_STEP_DELAY_MS, lambda: self._execute_step(index, token))

    def _execute_step(self, index: int, token: int) -> None:
        if token != self._validate_run_token:
            return
        step_key, _ = STEP_DEFS[index]

        # 2026-08 추가: port_list 단계만 큰 Excel 파일을 읽을 수 있어 느릴 수 있으므로
        # 백그라운드 스레드로 돌린다(ui/background_task.py) - 그래야 파싱 도중에도
        # 창이 계속 응답하고(다른 단계처럼 애니메이션도 살아있고), Ctrl+C 강제 종료의
        # 이벤트 필터 경로도 그 순간에 바로 먹힌다. PDK/DBS 단계는 폴더 목록만 나열하는
        # 가벼운 작업이라 그대로 동기 처리한다. run_task는 백그라운드 스레드에서 돌지만
        # 완료 콜백은 항상 메인 스레드에서 호출되므로 화면 갱신이 안전하다.
        if step_key == "port_list":
            run_task(
                self, lambda: self._evaluate_step(step_key),
                lambda result: self._finish_step(index, step_key, result, token),
                lambda message: self._finish_step(
                    index, step_key, (False, [(f"Unexpected error: {message}", "error")]), token,
                ),
            )
            return

        result = self._evaluate_step(step_key)
        self._finish_step(index, step_key, result, token)

    def _finish_step(self, index: int, step_key: str, result: tuple, token: int) -> None:
        if token != self._validate_run_token:
            return  # 백그라운드로 도는 사이 Validate가 다시 눌린 경우 - 조용히 버림
        passed, messages = result

        summary = self._truncate(messages[-1][0] if messages else "")
        self.step_chips[step_key].set_state("success" if passed else "error", summary)

        if index < len(self.step_lines):
            self.step_lines[index].set_status("success" if passed else "error")

        for message, status in messages:
            self._add_detail(message, status)

        if not passed:
            self._all_passed = False

        self._run_step_at(index + 1, token)

    def _finish_validation(self) -> None:
        self.next_btn.setEnabled(self._all_passed)
        self.next_btn.setToolTip("" if self._all_passed else "Run Validate first.")
        self._animate_details_in()

    # ------------------------------------------------------------------
    # Next
    # ------------------------------------------------------------------
    def _on_next_clicked(self) -> None:
        if self.on_next:
            self.on_next()

    # ------------------------------------------------------------------
    # Config export / import (2026-08 추가)
    # ------------------------------------------------------------------
    def _on_export_config(self) -> None:
        self.on_config_changed(self._current_values())
        run_export_config_dialog(self, self._current_values().get("pdk_folder", ""))

    def _on_import_config(self) -> None:
        if not run_import_config_dialog(self):
            return
        # config 3종이 디스크에서 전부 바뀌었으므로, 이 화면의 경로 입력을 새 값으로
        # 채우고 검사 결과를 무효화한다. Step2/3 화면은 이미 예전 config로 만들어져
        # 있으므로, 그 화면들도 새로 만들도록 상위(MainWindow)에 알린다.
        self.load_from_config(config_manager.load_config())
        if self.on_config_imported:
            self.on_config_imported()

    def load_from_config(self, config: dict) -> None:
        """Import 직후, 저장된 경로 값으로 입력칸을 다시 채운다."""
        for key, edit in self.path_edits.items():
            edit.setText(config.get(key, ""))
        self._invalidate_validation()

    # ------------------------------------------------------------------
    # 화면이 다시 보일 때마다 (Step2에서 Back으로 돌아왔을 때) 검사 결과를 무효화
    # 한다 - 경로를 고쳤을 수 있으므로 Next는 다시 Validate를 통과해야만 열린다
    # (2026-08 확정: 모든 Step에서 Back으로 돌아오면 반드시 다시 Validate).
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._invalidate_validation()

    def _invalidate_validation(self) -> None:
        self._all_passed = False
        # 백그라운드로 도는 중이었을 port_list 단계의 결과가 나중에 도착해도 이 화면
        # 상태를 건드리지 않도록 토큰을 새로 발급한다.
        self._validate_run_token += 1
        self.next_btn.setEnabled(False)
        self.next_btn.setToolTip("Run Validate first.")
        for chip in self.step_chips.values():
            chip.set_state("pending")
        for line in self.step_lines:
            line.set_status("pending")
        self._clear_details()
        self._update_validate_button_state()