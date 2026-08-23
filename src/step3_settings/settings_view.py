"""
settings_view.py

'Constants & Pin Settings' 화면 (Step 3, 2026-08 재설계): 상수 값(class/process_prefix/
output_prefix)과 단일 행 Voltage Condition 테이블(BST/WST/TIV x High/Mid/Low 9칸),
Pin 설정을 입력받는다. Validate는 Pin 설정만 검사한다(Constants는 검사 대상 아님).
통과하면 Output Path를 지정할 수 있게 되고, Output Path가 채워지면 Generate 버튼이
활성화된다.

기존의 기술(technology)별 다중 행 Voltage Condition 테이블과 PDK 폴더 파일명으로부터의
공정 자동 감지/하이라이트는 폐기되었다 - 이제 단일 행이라 하이라이트할 대상이 없다.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtWidgets import (
    QFileDialog, QFormLayout, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QScrollArea, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from step1_setup.port_list_reader import list_pins_by_port_type
from step3_settings import settings_manager
from step3_settings.constants_field_defs import SCALAR_CONSTANT_DEFS, VOLTAGE_CONDITION_FIELD_DEFS
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, ENABLE_SIGNAL_KEY, POWER_DOWN_KEY,
    VIRTUAL_POWER_KEY, VIRTUAL_POWER_PORT_TYPE, split_pattern_and_range,
)
from step3_settings.settings_validator import validate_constants, validate_pin_settings
from ui.theme import ERROR_COLOR, MUTED_TEXT_COLOR, SUCCESS_COLOR, TEXT_COLOR
from ui.ui_common import NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row


class SettingsView(QWidget):
    def __init__(
        self,
        get_pdk_folder: Callable[[], str],
        get_port_list_file: Callable[[], str],
        on_generate: Callable[[str], None] | None = None,
        show_loading: Callable[[str], None] | None = None,
        hide_loading: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
        parent=None,
    ):
        """
        Args:
            get_pdk_folder: 최신 PDK Folder 경로를 즉시 조회하는 콜백 (Step 1 값 재사용,
                             현재 Constants 섹션에서는 쓰이지 않지만 다음 라운드
                             (cell/pin 작성)를 위해 시그니처를 유지함)
            get_port_list_file: 최신 Port List 파일 경로를 즉시 조회하는 콜백 (Step 1 값 재사용)
            on_generate: Generate 버튼을 눌렀을 때 호출되는 콜백(output_path: str)
            show_loading / hide_loading: Validate처럼 시간이 걸릴 수 있는 작업 전후에
                                          전역 로딩 오버레이를 보여주고 숨기는 콜백
            on_back: Back 버튼을 눌렀을 때 호출되는 콜백 (이전 Step으로 이동)
        """
        super().__init__(parent)
        self.get_pdk_folder = get_pdk_folder
        self.get_port_list_file = get_port_list_file
        self.on_generate = on_generate
        self.show_loading = show_loading
        self.hide_loading = hide_loading
        self.on_back = on_back
        self.settings: dict = settings_manager.load_settings()

        self.scalar_widgets: dict[str, QWidget] = {}
        self.voltage_table: QTableWidget | None = None

        self._build_layout()

    # ------------------------------------------------------------------
    # 레이아웃
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel("Constants & Pin Settings")
        title.setObjectName("titleLabel")
        subtitle = QLabel("Configure constants and pin settings, then validate before generating.")
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.addWidget(self._build_constants_card())
        content_layout.addWidget(self._build_pins_card())
        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

        outer.addLayout(self._build_bottom_bar())

    def _build_constants_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("Constants")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)

        scalar_form = QFormLayout()
        scalar_form.setSpacing(8)
        for key, label, _kind, default in SCALAR_CONSTANT_DEFS:
            saved = self.settings["scalars"].get(key, default)
            edit = QLineEdit(str(saved))
            self.scalar_widgets[key] = edit
            scalar_form.addRow(label, edit)
        layout.addLayout(scalar_form)

        process_prefix_hint = QLabel(
            "Note: class, process_prefix, output_prefix, DFF Cell Name, and Primitive "
            "Cell Name are all required. process_prefix / class are used in block4's "
            "cell attributes (e.g. {process_prefix}_class)."
        )
        process_prefix_hint.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        process_prefix_hint.setWordWrap(True)
        layout.addWidget(process_prefix_hint)

        dff_hint = QLabel(
            "DFF Cell Name / Primitive Cell Name: used to locate the lu_table_template "
            "index_1/index_2 lines in the PDK/DK file - the first 'cell (DFF Cell Name)' "
            "declaration is found, then the first line after it containing the Primitive "
            "Cell Name (its cell_rise/cell_fall block) supplies the index_1/index_2 values."
        )
        dff_hint.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        dff_hint.setWordWrap(True)
        layout.addWidget(dff_hint)

        table_title = QLabel("Voltage Condition")
        table_title.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")
        layout.addWidget(table_title)

        self.voltage_table = self._build_voltage_table()
        layout.addWidget(self.voltage_table)

        hint = QLabel(
            "Enter numeric values only (no unit suffix). Each pair in Step 2 selects "
            "BST / WST / TIV, and its voltage_map values are taken from this single row."
        )
        hint.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        return card

    def _build_voltage_table(self) -> QTableWidget:
        """단일 행(BST/WST/TIV x High/Mid/Low = 9칸) Voltage Condition 테이블."""
        column_labels = [label for _key, label in VOLTAGE_CONDITION_FIELD_DEFS]
        table = QTableWidget(1, len(VOLTAGE_CONDITION_FIELD_DEFS))
        table.setHorizontalHeaderLabels(column_labels)
        table.verticalHeader().setVisible(False)
        table.verticalHeader().setDefaultSectionSize(26)
        table.setFixedHeight(26 * 2 + 6)

        saved_voltage = self.settings["voltage_condition"]
        for col, (key, _label) in enumerate(VOLTAGE_CONDITION_FIELD_DEFS):
            table.setItem(0, col, QTableWidgetItem(saved_voltage.get(key, "")))

        return table

    def _build_pins_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Pin Settings")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        self.virtual_power_combo = NoWheelComboBox()
        self._populate_virtual_power_combo()
        form.addRow("Virtual Power (power gate)", self.virtual_power_combo)

        self.enable_signal_edit, self.enable_signal_badge = self._build_wildcard_field(
            form, "Enable signal for power gate", self.settings["pins"].get(ENABLE_SIGNAL_KEY, "")
        )

        self.power_down_edit, self.power_down_badge = self._build_wildcard_field(
            form, "Power down control signal", self.settings["pins"].get(POWER_DOWN_KEY, "")
        )
        self.dbs_output_edit, self.dbs_output_badge = self._build_wildcard_field(
            form, "DBS output signal", self.settings["pins"].get(DBS_OUTPUT_KEY, "")
        )

        layout.addLayout(form)
        return card

    def _build_wildcard_field(self, form: QFormLayout, label: str, initial: str) -> tuple[QLineEdit, QLabel]:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        edit = QLineEdit(initial)
        badge = QLabel("")
        badge.setStyleSheet("font-size: 11px;")
        container_layout.addWidget(edit)
        container_layout.addWidget(badge)

        edit.textChanged.connect(lambda: self._update_wildcard_badge(edit, badge))
        self._update_wildcard_badge(edit, badge)

        form.addRow(label, container)
        return edit, badge

    def _update_wildcard_badge(self, edit: QLineEdit, badge: QLabel) -> None:
        pattern, range_part = split_pattern_and_range(edit.text())
        if "*" in pattern:
            text = "\u2713 Wildcard pattern detected"
            if range_part:
                text += f" \u00b7 Range {range_part}"
            badge.setStyleSheet(f"color: {SUCCESS_COLOR}; font-size: 11px;")
            badge.setText(text)
        else:
            badge.setText("")

    def _build_bottom_bar(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.validate_btn = QPushButton("Validate")
        self.validate_btn.setObjectName("primaryButton")
        self.validate_btn.clicked.connect(self._on_validate)
        btn_row.addWidget(self.validate_btn)
        layout.addLayout(btn_row)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output Path"))
        self.output_path_edit = QLineEdit(self.settings.get("output_path", ""))
        self.output_path_edit.setEnabled(False)
        self.output_path_edit.textChanged.connect(self._update_generate_button_state)
        output_row.addWidget(self.output_path_edit, stretch=1)
        self.output_browse_btn = QPushButton("Browse...")
        self.output_browse_btn.setEnabled(False)
        self.output_browse_btn.clicked.connect(self._on_browse_output)
        output_row.addWidget(self.output_browse_btn)
        layout.addLayout(output_row)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)

        self.back_btn = build_back_button(self.on_back)
        layout.addLayout(build_bottom_button_row(self.back_btn, self.generate_btn))

        return layout

    # ------------------------------------------------------------------
    # Virtual Power 콤보 (Port List의 PWR pin들로 채움)
    # ------------------------------------------------------------------
    def _populate_virtual_power_combo(self) -> None:
        self.virtual_power_combo.blockSignals(True)
        self.virtual_power_combo.clear()

        pwr_pins = list_pins_by_port_type(self.get_port_list_file(), VIRTUAL_POWER_PORT_TYPE)
        self.virtual_power_combo.addItem("(None)", "")
        for pin in pwr_pins:
            self.virtual_power_combo.addItem(pin, pin)

        current = self.settings["pins"].get(VIRTUAL_POWER_KEY, "")
        idx = self.virtual_power_combo.findData(current) if current else 0
        self.virtual_power_combo.setCurrentIndex(idx if idx >= 0 else 0)

        self.virtual_power_combo.blockSignals(False)

    # ------------------------------------------------------------------
    # 값 수집 / 저장
    # ------------------------------------------------------------------
    def _collect_constants(self) -> dict:
        scalars = {}
        for key, _label, _kind, _default in SCALAR_CONSTANT_DEFS:
            scalars[key] = self.scalar_widgets[key].text().strip()

        voltage_condition = {}
        for col, (key, _label) in enumerate(VOLTAGE_CONDITION_FIELD_DEFS):
            item = self.voltage_table.item(0, col)
            voltage_condition[key] = item.text().strip() if item else ""

        return {"scalars": scalars, "voltage_condition": voltage_condition}

    def _collect_pins(self) -> dict:
        return {
            VIRTUAL_POWER_KEY: self.virtual_power_combo.currentData() or "",
            ENABLE_SIGNAL_KEY: self.enable_signal_edit.text().strip(),
            POWER_DOWN_KEY: self.power_down_edit.text().strip(),
            DBS_OUTPUT_KEY: self.dbs_output_edit.text().strip(),
        }

    def _collect_all(self) -> dict:
        constants = self._collect_constants()
        return {
            "scalars": constants["scalars"],
            "voltage_condition": constants["voltage_condition"],
            "pins": self._collect_pins(),
            "output_path": self.output_path_edit.text().strip(),
        }

    def _persist(self) -> None:
        self.settings = self._collect_all()
        settings_manager.save_settings(self.settings)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    def _on_validate(self) -> None:
        if self.show_loading:
            self.show_loading("Validating settings...")

        self._persist()
        errors = validate_constants(self.settings["scalars"], self.settings["voltage_condition"])
        errors += validate_pin_settings(self.settings["pins"], self.get_port_list_file())

        if self.hide_loading:
            self.hide_loading()

        if errors:
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText("\n".join(f"\u2022 {e}" for e in errors))
            self.output_path_edit.setEnabled(False)
            self.output_browse_btn.setEnabled(False)
            self.generate_btn.setEnabled(False)
        else:
            self.result_label.setStyleSheet(f"color: {SUCCESS_COLOR};")
            self.result_label.setText("Settings passed validation. Choose an output path to continue.")
            self.output_path_edit.setEnabled(True)
            self.output_browse_btn.setEnabled(True)
            self._update_generate_button_state()

    def _update_generate_button_state(self) -> None:
        can_generate = self.output_path_edit.isEnabled() and bool(self.output_path_edit.text().strip())
        self.generate_btn.setEnabled(can_generate)

    def _on_browse_output(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Output Path")
        if path:
            self.output_path_edit.setText(path)

    def _on_generate_clicked(self) -> None:
        output_path = self.output_path_edit.text().strip()
        if not output_path:
            return
        self._persist()
        if self.on_generate:
            self.on_generate(output_path)

    # ------------------------------------------------------------------
    # 화면이 다시 보일 때마다 (Step 1에서 돌아왔을 때 등) 최신 pin 정보 반영
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._populate_virtual_power_combo()
