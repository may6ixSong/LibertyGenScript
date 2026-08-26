"""
setup_view.py

'Setup & Validate' 화면: PDK/DBS 폴더 + Port List 엑셀 파일 입력을 받고,
Validate 버튼으로 3단계(PDK -> DBS -> Port List)를 순서대로 검사한다.
각 단계는 상단 가로 스텝 인디케이터에 진행 상태(pending/running/success/error)로
표시되고, 세부 메시지는 하단 Details 패널(읽기 전용, 선택 불가)에 나열된다.
모든 단계가 통과하면 Next 버튼이 활성화된다.
"""

from __future__ import annotations

from pathlib import Path

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from step1_setup.field_defs import INPUT_PATH_FIELDS
from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step1_setup.port_list_reader import read_port_list
from ui.theme import (
    BORDER_COLOR, ERROR_COLOR, MUTED_TEXT_COLOR, PENDING_COLOR,
    PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR,
)
from ui.ui_common import DetailsList, add_shadow

STEP_DEFS = [
    ("pdk", "PDK Folder"),
    ("dbs", "DBS Simulation"),
    ("port_list", "Port List"),
]

_STEP_DELAY_MS = 350


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
    def __init__(self, existing_config: dict, on_config_changed, on_next=None, parent=None):
        """
        Args:
            existing_config: 저장된 입력 경로 값
            on_config_changed: 값이 바뀔 때 저장을 요청하는 콜백(dict) -> None
            on_next: 모든 단계 통과 후 Next 버튼을 눌렀을 때 호출되는 콜백(선택)
        """
        super().__init__(parent)
        self.on_config_changed = on_config_changed
        self.on_next = on_next
        self.path_edits: dict[str, QLineEdit] = {}
        self.step_chips: dict[str, _StepChip] = {}
        self.step_lines: list[_StepLine] = []
        self._all_passed = False
        self._details_anim = None  # QPropertyAnimation 참조 유지용 (GC 방지)

        self._build_layout(existing_config)
        self._update_validate_button_state()

    # ------------------------------------------------------------------
    # 레이아웃
    # ------------------------------------------------------------------
    def _build_layout(self, existing_config: dict) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel("Liberty Generator")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Set up your input paths, then validate before generating.")
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        outer.addWidget(self._build_input_card(existing_config))
        outer.addWidget(self._build_note_banner())
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

        section_label = QLabel("Input Paths")
        section_label.setObjectName("sectionLabel")
        card_layout.addWidget(section_label, 0, 0, 1, 3)

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

    def _build_note_banner(self) -> QFrame:
        note = QFrame()
        note.setObjectName("noteBanner")
        note_layout = QHBoxLayout(note)
        note_layout.setContentsMargins(16, 12, 16, 12)
        note_label = QLabel(
            "Note: The PDK Folder must contain only files whose extension starts with .lib "
            "(e.g. .lib, .lib_css_tn), and the DBS Simulation Folder must contain only .mt0 "
            "files. Extra files may lead to incorrect results."
        )
        note_label.setObjectName("noteLabel")
        note_label.setWordWrap(True)
        note_layout.addWidget(note_label)
        return note

    def _build_action_row(self) -> QHBoxLayout:
        btn_row = QHBoxLayout()
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
        if kind == "dir":
            path = QFileDialog.getExistingDirectory(self, f"Select {label}")
        else:
            filter_str = (
                f"Excel Files ({' '.join('*' + ext for ext in extensions)})"
                if extensions else "All Files (*)"
            )
            path, _ = QFileDialog.getOpenFileName(self, f"Select {label}", "", filter_str)
        if path:
            edit.setText(path)

    def _update_validate_button_state(self) -> None:
        values = self._current_values()
        port_list_file = values.get("port_list_file", "")
        valid_extension = port_list_file.lower().endswith((".xls", ".xlsx"))
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

        for chip in self.step_chips.values():
            chip.set_state("pending")
        for line in self.step_lines:
            line.set_status("pending")

        self._run_step_at(0)

    def _run_step_at(self, index: int) -> None:
        if index >= len(STEP_DEFS):
            self._finish_validation()
            return

        step_key, _ = STEP_DEFS[index]
        self.step_chips[step_key].set_state("running")
        QTimer.singleShot(_STEP_DELAY_MS, lambda: self._execute_step(index))

    def _execute_step(self, index: int) -> None:
        step_key, _ = STEP_DEFS[index]
        passed, messages = self._evaluate_step(step_key)

        summary = self._truncate(messages[-1][0] if messages else "")
        self.step_chips[step_key].set_state("success" if passed else "error", summary)

        if index < len(self.step_lines):
            self.step_lines[index].set_status("success" if passed else "error")

        for message, status in messages:
            self._add_detail(message, status)

        if not passed:
            self._all_passed = False

        self._run_step_at(index + 1)

    def _finish_validation(self) -> None:
        self.next_btn.setEnabled(self._all_passed)
        self._animate_details_in()

    # ------------------------------------------------------------------
    # Next
    # ------------------------------------------------------------------
    def _on_next_clicked(self) -> None:
        if self.on_next:
            self.on_next()