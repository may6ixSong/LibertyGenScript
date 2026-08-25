"""
settings_view.py

'Constants & Pin Settings' 화면 (Step 3, 2026-08 재설계): 상수 값(class/process_prefix/
output_prefix/DFF Cell Name/LUT Table/Worst case primitive liberty)과 Voltage Map
(BST/WST/TIV x Power Type1..N, power type 개수 조절 + Power Type별 voltage name),
Pin 설정을 입력받는다.

2026-08 Voltage Map 재설계: 예전에는 BST/WST/TIV x High/Mid/Low 9칸을 가로 한 줄
테이블로 입력받았으나, "High/Mid/Low"가 정확한 용어가 아니라는 피드백에 따라
Power Type1/2/3으로 이름을 바꾸고, BST/WST/TIV 세 그룹을 세로로 나열해 그룹마다
Power Type별 전압 값을 입력받는 형태로 바꿨다. Power Type 개수는 과제에 따라 2개
(High/Low만 있는 경우)일 수도 있어 화면에서 2~3 사이로 조절 가능하다(스핀박스).
Power Type마다 리버티에 쓸 voltage name도 별도로 입력받는다(BST/WST/TIV 공통,
Power Type당 하나).

2026-08 추가 - 연계 입력(linked group):
  Virtual Power / Power down control signal / DBS output pin 세 개는 각각 "그 pin을
  입력했기 때문에 추가로 같이 입력해야 하는" 하위 필드들을 갖는다. 화면에서도 상위 pin
  바로 아래에 세로선 + 들여쓰기로 묶어서(_build_linked_group) 연계 관계가 한눈에
  보이도록 한다.

2026-08 추가 - DBS output pin은 Validate 전에 반드시 Check 먼저:
  Port List 파일이 바뀌면 같은 와일드카드라도 인식되는 pin 집합이 달라지므로,
  "1) Check DBS Output Pins" 버튼을 눌러 현재 Port List 기준으로 pin을 다시 펼친 뒤에야
  각 pin의 related pin을 입력할 수 있고, 그 다음에야 "2) Validate" 버튼이 열린다.
  DBS output pin 입력을 고치거나 화면을 다시 열면 Check 결과는 무효가 되고 Validate가
  다시 잠긴다.

기존의 기술(technology)별 다중 행 Voltage Condition 테이블과 PDK 폴더 파일명으로부터의
공정 자동 감지/하이라이트는 폐기되었다.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QPushButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem,
    QVBoxLayout, QWidget,
)

from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step1_setup.port_list_reader import list_pins_by_port_type
from step2_udc.udc_field_defs import compute_pairs
from step3_settings import settings_manager
from step3_settings.constants_field_defs import (
    POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_MAX, POWER_TYPE_COUNT_MIN, SCALAR_CONSTANT_DEFS,
    VOLTAGE_MAP_GROUPS, power_type_label, voltage_map_name_key, voltage_map_value_key,
)
from step3_settings.pin_field_defs import (
    DBS_OUTPUT_KEY, DBS_RELATED_PINS_KEY, DBS_TIMING_SENSE_KEY, DBS_TIMING_TYPE_KEY,
    ENABLE_SIGNAL_KEY, POWER_DOWN_FALL_POWER_KEY, POWER_DOWN_KEY, POWER_DOWN_RISE_POWER_KEY,
    POWER_DOWN_WHEN_KEY, VIRTUAL_POWER_KEY, VIRTUAL_POWER_PG_FUNCTION_KEY,
    VIRTUAL_POWER_PORT_TYPE, VIRTUAL_POWER_SWITCH_FUNCTION_KEY, expand_dbs_output_pins,
    split_pattern_and_range,
)
from step3_settings.settings_validator import validate_constants, validate_pin_settings
from ui.theme import (
    ERROR_COLOR, MUTED_TEXT_COLOR, PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR,
    WARNING_BG, WARNING_BORDER, WARNING_TEXT,
)
from ui.ui_common import NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row

_HINT_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 11px;"
_RELATED_PIN_TABLE_MAX_HEIGHT = 240


class SettingsView(QWidget):
    def __init__(
        self,
        get_pdk_folder: Callable[[], str],
        get_dbs_folder: Callable[[], str],
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
                             'Worst case primitive liberty' 드롭다운 후보를 채우는 데 사용)
            get_dbs_folder: 최신 DBS Simulation Folder 경로를 즉시 조회하는 콜백
                             (PDK와 1:1 pair가 성립하는 파일만 위 드롭다운 후보가 됨)
            get_port_list_file: 최신 Port List 파일 경로를 즉시 조회하는 콜백 (Step 1 값 재사용)
            on_generate: Generate 버튼을 눌렀을 때 호출되는 콜백(output_path: str)
            show_loading / hide_loading: Validate처럼 시간이 걸릴 수 있는 작업 전후에
                                          전역 로딩 오버레이를 보여주고 숨기는 콜백
            on_back: Back 버튼을 눌렀을 때 호출되는 콜백 (이전 Step으로 이동)
        """
        super().__init__(parent)
        self.get_pdk_folder = get_pdk_folder
        self.get_dbs_folder = get_dbs_folder
        self.get_port_list_file = get_port_list_file
        self.on_generate = on_generate
        self.show_loading = show_loading
        self.hide_loading = hide_loading
        self.on_back = on_back
        self.settings: dict = settings_manager.load_settings()

        self.scalar_widgets: dict[str, QWidget] = {}
        self.power_type_count_spin: QSpinBox | None = None
        self.voltage_value_edits: dict[str, QLineEdit] = {}
        self.voltage_name_edits: dict[str, QLineEdit] = {}
        # Power Type3 행(값/이름 둘 다) - power type 개수가 2일 때 숨길 대상.
        # (라벨 위젯, 입력 위젯) 쌍의 목록.
        self._power_type3_rows: list[tuple[QLabel, QLineEdit]] = []
        # "Check DBS Output Pins"를 눌러 현재 Port List로 pin을 펼친 상태인지 여부.
        # False인 동안에는 Validate 버튼이 잠겨 있다.
        self._dbs_check_done = False

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

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------
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
        for key, label, kind, default in SCALAR_CONSTANT_DEFS:
            saved = self.settings["scalars"].get(key, default)
            if kind == "pdk_dropdown":
                combo = NoWheelComboBox()
                self.scalar_widgets[key] = combo
                scalar_form.addRow(label, combo)
            else:
                edit = QLineEdit(str(saved))
                self.scalar_widgets[key] = edit
                scalar_form.addRow(label, edit)
        layout.addLayout(scalar_form)
        self._populate_worst_case_pdk_combo()

        layout.addWidget(self._hint(
            "Note: class, process_prefix, output_prefix, DFF Cell Name, LUT Table and "
            "Worst case primitive liberty are all required. process_prefix / class are "
            "used in block4's cell attributes (e.g. {process_prefix}_class)."
        ))
        layout.addWidget(self._hint(
            "DFF Cell Name / LUT Table: used to locate the lu_table_template "
            "index_1/index_2 lines in the PDK/DK file - the first 'cell (DFF Cell Name)' "
            "declaration is found, then the first line after it containing the LUT Table "
            "name (its cell_rise/cell_fall block) supplies the index_1/index_2 values."
        ))
        layout.addWidget(self._hint(
            "Worst case primitive liberty: the lu_table_template above is read from THIS "
            "PDK file only, and the same table is reused for every generated liberty - "
            "the other paired PDK files are never searched for it. Only PDK files that "
            "currently form a 1:1 pair with a DBS output file (Step 2) are listed."
        ))

        table_title = QLabel("Voltage Map")
        table_title.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")
        layout.addWidget(table_title)

        layout.addWidget(self._build_voltage_map_section())

        layout.addWidget(self._hint(
            "Enter numeric values only (no unit suffix). Each pair in Step 2 selects "
            "BST / WST / TIV, and its voltage_map values are taken from that group's "
            "Power Type1..N values here."
        ))

        return card

    def _build_voltage_map_section(self) -> QWidget:
        """
        Voltage Map: power type 개수 조절(2~3) + BST/WST/TIV 세로 그룹(그룹마다 Power
        Type1..N 값) + Power Type별 voltage name(그룹 공통, 하나씩).
        """
        self.voltage_value_edits = {}
        self.voltage_name_edits = {}
        self._power_type3_rows = []

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        voltage_map = self.settings["voltage_map"]
        saved_count = voltage_map.get(POWER_TYPE_COUNT_KEY, POWER_TYPE_COUNT_MAX)
        saved_values = voltage_map.get("values", {})
        saved_names = voltage_map.get("names", {})

        count_row = QHBoxLayout()
        count_row.addWidget(QLabel("Power Type Count"))
        self.power_type_count_spin = QSpinBox()
        self.power_type_count_spin.setRange(POWER_TYPE_COUNT_MIN, POWER_TYPE_COUNT_MAX)
        self.power_type_count_spin.setValue(saved_count)
        self.power_type_count_spin.valueChanged.connect(self._on_power_type_count_changed)
        count_row.addWidget(self.power_type_count_spin)
        count_row.addStretch()
        layout.addLayout(count_row)

        for group in VOLTAGE_MAP_GROUPS:
            group_frame = QFrame()
            group_frame.setObjectName("card")
            group_layout = QVBoxLayout(group_frame)
            group_layout.setContentsMargins(12, 10, 12, 10)
            group_layout.setSpacing(4)

            group_title = QLabel(group)
            group_title.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")
            group_layout.addWidget(group_title)

            group_form = QFormLayout()
            group_form.setSpacing(6)
            for type_index in range(1, POWER_TYPE_COUNT_MAX + 1):
                key = voltage_map_value_key(group, type_index)
                edit = QLineEdit(str(saved_values.get(key, "")))
                self.voltage_value_edits[key] = edit
                row_label = QLabel(power_type_label(type_index))
                group_form.addRow(row_label, edit)
                if type_index == POWER_TYPE_COUNT_MAX:
                    self._power_type3_rows.append((row_label, edit))
            group_layout.addLayout(group_form)

            layout.addWidget(group_frame)

        name_frame = QFrame()
        name_frame.setObjectName("card")
        name_layout = QVBoxLayout(name_frame)
        name_layout.setContentsMargins(12, 10, 12, 10)
        name_layout.setSpacing(4)

        name_title = QLabel("Voltage Name")
        name_title.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 600;")
        name_layout.addWidget(name_title)

        name_form = QFormLayout()
        name_form.setSpacing(6)
        for type_index in range(1, POWER_TYPE_COUNT_MAX + 1):
            key = voltage_map_name_key(type_index)
            edit = QLineEdit(str(saved_names.get(key, "")))
            self.voltage_name_edits[key] = edit
            row_label = QLabel(power_type_label(type_index))
            name_form.addRow(row_label, edit)
            if type_index == POWER_TYPE_COUNT_MAX:
                self._power_type3_rows.append((row_label, edit))
        name_layout.addLayout(name_form)

        layout.addWidget(name_frame)

        self._apply_power_type_count_visibility(saved_count)

        return container

    def _on_power_type_count_changed(self, value: int) -> None:
        self._apply_power_type_count_visibility(value)

    def _apply_power_type_count_visibility(self, count: int) -> None:
        """Power Type3 행(BST/WST/TIV 값 + voltage name)을 count에 따라 보이거나 숨긴다."""
        visible = count >= POWER_TYPE_COUNT_MAX
        for row_label, edit in self._power_type3_rows:
            row_label.setVisible(visible)
            edit.setVisible(visible)

    def _populate_worst_case_pdk_combo(self) -> None:
        """
        'Worst case primitive liberty' 드롭다운을 현재 PDK/DBS 폴더 기준으로 다시 채운다.
        후보는 Step2와 동일한 규칙(compute_pairs)으로 DBS output과 1:1 pair가 성립한
        PDK 파일들뿐이다.
        """
        combo = self.scalar_widgets.get("worst_case_pdk")
        if combo is None:
            return

        combo.blockSignals(True)
        combo.clear()
        combo.addItem("(None)", "")
        for pdk_file in self.paired_pdk_files():
            combo.addItem(pdk_file, pdk_file)

        current = self.settings["scalars"].get("worst_case_pdk", "")
        idx = combo.findData(current) if current else 0
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.blockSignals(False)

    def paired_pdk_files(self) -> list[str]:
        """Step2에서 DBS output과 1:1 pair가 성립한 PDK 파일명 목록 (항상 새로 계산)."""
        pdk_files = list_pdk_lib_files(self.get_pdk_folder())
        dbs_files = list_dbs_mt0_files(self.get_dbs_folder())
        pair_result = compute_pairs(pdk_files, dbs_files)
        return [pair["pdk_file"] for pair in pair_result["pairs"]]

    # ------------------------------------------------------------------
    # Pin Settings
    # ------------------------------------------------------------------
    def _build_pins_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(4)

        title = QLabel("Pin Settings")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)

        pins = self.settings["pins"]

        # ---- 1) Virtual Power (power gate) + 연계 입력 3개 ----
        top_form = QFormLayout()
        top_form.setSpacing(10)
        self.virtual_power_combo = NoWheelComboBox()
        self._populate_virtual_power_combo()
        top_form.addRow("Virtual Power (power gate)", self.virtual_power_combo)
        layout.addLayout(top_form)

        vp_group = self._build_linked_group(
            layout, "These are required because a Virtual Power (power gate) pin is used."
        )
        vp_form = self._add_form(vp_group)
        self.enable_signal_edit, self.enable_signal_badge = self._build_wildcard_field(
            vp_form, "Enable Signal for power gate", pins.get(ENABLE_SIGNAL_KEY, ""),
        )
        self.switch_function_edit, self.switch_function_badge = self._build_plain_pin_field(
            vp_form, "Virtual Power Switch Function",
            pins.get(VIRTUAL_POWER_SWITCH_FUNCTION_KEY, ""),
        )
        self.pg_function_edit, self.pg_function_badge = self._build_plain_pin_field(
            vp_form, "Virtual Power PG Function",
            pins.get(VIRTUAL_POWER_PG_FUNCTION_KEY, ""),
        )
        vp_group.addWidget(self._hint(
            "Switch Function / PG Function do not allow wildcards (*). They are written "
            "as-is into block4's pg_pin switch_function / pg_function for the Virtual "
            "Power pin. Enable Signal keeps its existing wildcard behaviour."
        ))

        # ---- 2) Power down control signal + 연계 입력 3개 ----
        pd_form = QFormLayout()
        pd_form.setSpacing(10)
        self.power_down_edit, self.power_down_badge = self._build_wildcard_field(
            pd_form, "Power down control signal", pins.get(POWER_DOWN_KEY, ""),
        )
        layout.addLayout(pd_form)

        pd_group = self._build_linked_group(
            layout, "These are required because a Power down control signal is used."
        )
        pd_inner_form = self._add_form(pd_group)
        self.power_down_rise_edit = QLineEdit(str(pins.get(POWER_DOWN_RISE_POWER_KEY, "")))
        self.power_down_fall_edit = QLineEdit(str(pins.get(POWER_DOWN_FALL_POWER_KEY, "")))
        self.power_down_when_edit = QLineEdit(str(pins.get(POWER_DOWN_WHEN_KEY, "")))
        pd_inner_form.addRow("rise power", self.power_down_rise_edit)
        pd_inner_form.addRow("fall power", self.power_down_fall_edit)
        pd_inner_form.addRow("when", self.power_down_when_edit)
        pd_group.addWidget(self._hint(
            "Written into block5's {process_prefix}_acore_internal_power block of every "
            "pin matching the Power down control signal ({prefix}_acore_rise_power / "
            "_acore_fall_power / _acore_when). The values shown are the previous "
            "hard-coded defaults."
        ))

        # ---- 3) DBS output pin + Check + 연계 입력 ----
        dbs_form = QFormLayout()
        dbs_form.setSpacing(10)
        self.dbs_output_edit, self.dbs_output_badge = self._build_wildcard_field(
            dbs_form, "DBS output pin", pins.get(DBS_OUTPUT_KEY, ""),
        )
        self.dbs_output_edit.textChanged.connect(lambda _text: self._invalidate_dbs_check())
        layout.addLayout(dbs_form)

        dbs_group_layout = self._build_linked_group(
            layout, "These are required because a DBS output pin is used."
        )

        # (1) 먼저 Check - 이게 Validate보다 앞서야 한다는 걸 배치 순서로도 드러낸다
        dbs_group_layout.addWidget(self._build_dbs_check_banner())

        check_row = QHBoxLayout()
        self.dbs_check_btn = QPushButton("1) Check DBS Output Pins")
        self.dbs_check_btn.setObjectName("primaryButton")
        self.dbs_check_btn.clicked.connect(self._on_check_dbs_pins)
        check_row.addWidget(self.dbs_check_btn)
        self.dbs_check_status = QLabel("")
        self.dbs_check_status.setWordWrap(True)
        check_row.addWidget(self.dbs_check_status, stretch=1)
        dbs_group_layout.addLayout(check_row)

        self.dbs_related_table = QTableWidget(0, 2)
        self.dbs_related_table.setHorizontalHeaderLabels(["DBS Output Pin (from Port List)", "Related Pin"])
        self.dbs_related_table.verticalHeader().setVisible(False)
        self.dbs_related_table.verticalHeader().setDefaultSectionSize(26)
        self.dbs_related_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dbs_related_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dbs_related_table.setMaximumHeight(_RELATED_PIN_TABLE_MAX_HEIGHT)
        self.dbs_related_table.setVisible(False)
        dbs_group_layout.addWidget(self.dbs_related_table)

        self.dbs_related_hint = self._hint(
            "Each Related Pin must be a pin that exists in the Port List AND must match "
            "that DBS output pin's 'Related Pin' column value exactly. It is written into "
            "block5's timing() related_bus_pins."
        )
        dbs_group_layout.addWidget(self.dbs_related_hint)

        # (2) 그 다음 timing_sense / timing_type (인식된 pin 전체 공통 1쌍)
        dbs_inner_form = self._add_form(dbs_group_layout)
        self.dbs_timing_sense_edit = QLineEdit(str(pins.get(DBS_TIMING_SENSE_KEY, "")))
        self.dbs_timing_type_edit = QLineEdit(str(pins.get(DBS_TIMING_TYPE_KEY, "")))
        dbs_inner_form.addRow("timing_sense", self.dbs_timing_sense_edit)
        dbs_inner_form.addRow("timing_type", self.dbs_timing_type_edit)
        dbs_group_layout.addWidget(self._hint(
            "timing_sense / timing_type are shared by every recognized DBS output pin and "
            "are written into block5's timing() block. The values shown are the previous "
            "hard-coded defaults."
        ))

        return card

    def _build_dbs_check_banner(self) -> QLabel:
        banner = QLabel(
            "⚠  Run this check BEFORE Validate. The pins recognized by the wildcard "
            "change whenever the Port List file changes, so the Related Pin list below must "
            "be rebuilt from the current Port List first. Validate stays locked until then."
        )
        banner.setWordWrap(True)
        banner.setStyleSheet(
            f"background-color: {WARNING_BG}; border: 1px solid {WARNING_BORDER}; "
            f"color: {WARNING_TEXT}; border-radius: 6px; padding: 8px; font-size: 11px;"
        )
        return banner

    def _build_linked_group(self, parent_layout: QVBoxLayout, caption: str) -> QVBoxLayout:
        """
        바로 위 pin 입력에 연계된 하위 필드들을 담는 프레임. 왼쪽 세로선 + 들여쓰기로
        "위 pin을 입력했기 때문에 이어서 입력해야 하는 값들"임을 시각적으로 표현한다.

        Returns: 하위 위젯/폼을 순서대로 넣을 프레임 내부 QVBoxLayout
                 (폼이 필요하면 _add_form()으로 그 자리에 하나 만들어 쓴다)
        """
        frame = QFrame()
        frame.setObjectName("linkedGroup")
        frame.setStyleSheet(
            f"QFrame#linkedGroup {{ border: none; border-left: 2px solid {PRIMARY_COLOR}; "
            f"background: transparent; }}"
        )
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(14, 6, 0, 10)
        frame_layout.setSpacing(6)

        caption_label = QLabel(f"↳  {caption}")
        caption_label.setWordWrap(True)
        caption_label.setStyleSheet(f"color: {PRIMARY_COLOR}; font-size: 11px; font-weight: 600;")
        frame_layout.addWidget(caption_label)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addSpacing(18)
        row.addWidget(frame, stretch=1)
        parent_layout.addLayout(row)
        return frame_layout

    def _add_form(self, layout: QVBoxLayout) -> QFormLayout:
        """지금 위치에 QFormLayout을 하나 만들어 붙이고 돌려준다(배치 순서 제어용)."""
        form = QFormLayout()
        form.setSpacing(8)
        layout.addLayout(form)
        return form

    def _hint(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(_HINT_STYLE)
        label.setWordWrap(True)
        return label

    def _build_wildcard_field(self, form: QFormLayout, label: str, initial: str) -> tuple[QLineEdit, QLabel]:
        edit, badge = self._build_field_with_badge(form, label, initial)
        edit.textChanged.connect(lambda: self._update_wildcard_badge(edit, badge))
        self._update_wildcard_badge(edit, badge)
        return edit, badge

    def _build_plain_pin_field(self, form: QFormLayout, label: str, initial: str) -> tuple[QLineEdit, QLabel]:
        """와일드카드를 허용하지 않는 pin 입력 (입력에 '*'가 있으면 즉시 빨간 안내)."""
        edit, badge = self._build_field_with_badge(form, label, initial)
        edit.textChanged.connect(lambda: self._update_no_wildcard_badge(edit, badge))
        self._update_no_wildcard_badge(edit, badge)
        return edit, badge

    def _build_field_with_badge(self, form: QFormLayout, label: str, initial: str) -> tuple[QLineEdit, QLabel]:
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        edit = QLineEdit(initial)
        badge = QLabel("")
        badge.setStyleSheet("font-size: 11px;")
        container_layout.addWidget(edit)
        container_layout.addWidget(badge)

        form.addRow(label, container)
        return edit, badge

    def _update_wildcard_badge(self, edit: QLineEdit, badge: QLabel) -> None:
        pattern, range_part = split_pattern_and_range(edit.text())
        if "*" in pattern:
            text = "✓ Wildcard pattern detected"
            if range_part:
                text += f" · Range {range_part}"
            badge.setStyleSheet(f"color: {SUCCESS_COLOR}; font-size: 11px;")
            badge.setText(text)
        else:
            badge.setText("")

    def _update_no_wildcard_badge(self, edit: QLineEdit, badge: QLabel) -> None:
        if "*" in edit.text():
            badge.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            badge.setText("✗ Wildcard (*) is not allowed here - enter one exact pin.")
        else:
            badge.setText("")

    def _build_bottom_bar(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(10)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.validate_btn = QPushButton("2) Validate")
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

        self._invalidate_dbs_check()
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
    # DBS output pin Check (Validate보다 항상 먼저)
    # ------------------------------------------------------------------
    def _invalidate_dbs_check(self) -> None:
        """
        Check 결과를 무효화하고 Validate를 다시 잠근다. DBS output pin 입력이 바뀌거나
        화면을 다시 열었을 때(= Port List가 바뀌었을 수 있을 때) 호출된다.
        """
        self._dbs_check_done = False
        if hasattr(self, "dbs_related_table"):
            self.dbs_related_table.setRowCount(0)
            self.dbs_related_table.setVisible(False)
        if hasattr(self, "dbs_check_status"):
            self.dbs_check_status.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
            self.dbs_check_status.setText("Not checked yet - Validate is locked.")
        if hasattr(self, "validate_btn"):
            self.validate_btn.setEnabled(False)
            self.validate_btn.setToolTip("Run '1) Check DBS Output Pins' first.")
        if hasattr(self, "output_path_edit"):
            self.output_path_edit.setEnabled(False)
            self.output_browse_btn.setEnabled(False)
            self.generate_btn.setEnabled(False)

    def _on_check_dbs_pins(self) -> None:
        if self.show_loading:
            self.show_loading("Checking DBS output pins against the Port List...")

        dbs_text = self.dbs_output_edit.text().strip()
        recognized = expand_dbs_output_pins(self.get_port_list_file(), dbs_text) if dbs_text else []

        if self.hide_loading:
            self.hide_loading()

        if not dbs_text:
            self._invalidate_dbs_check()
            self.dbs_check_status.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            self.dbs_check_status.setText("DBS output pin is empty - nothing to check.")
            return

        if not recognized:
            self._invalidate_dbs_check()
            self.dbs_check_status.setStyleSheet(f"color: {ERROR_COLOR}; font-size: 11px;")
            self.dbs_check_status.setText(
                f"'{dbs_text}' matched no PORT pins in the current Port List."
            )
            return

        self._fill_related_pin_table(recognized)
        self._dbs_check_done = True
        self.dbs_check_status.setStyleSheet(f"color: {SUCCESS_COLOR}; font-size: 11px;")
        self.dbs_check_status.setText(
            f"✓ {len(recognized)} DBS output pin(s) recognized. "
            "Fill in every Related Pin, then Validate."
        )
        self.validate_btn.setEnabled(True)
        self.validate_btn.setToolTip("")

    def _fill_related_pin_table(self, recognized: list[str]) -> None:
        """
        인식된 pin마다 한 행씩. Related Pin 칸은 이전에 저장해 둔 값이 있으면 그대로
        되살리고, 없으면 빈 칸으로 둔다(사용자가 직접 확인해서 입력해야 하는 값이므로
        Port List 값을 미리 채워넣지 않는다).
        """
        saved = self.settings["pins"].get(DBS_RELATED_PINS_KEY) or {}
        table = self.dbs_related_table
        table.setRowCount(len(recognized))
        for row, pin_name in enumerate(recognized):
            name_item = QTableWidgetItem(pin_name)
            name_item.setFlags(Qt.ItemIsEnabled)  # 읽기 전용
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, QTableWidgetItem(str(saved.get(pin_name, ""))))
        table.setVisible(True)
        table.setEditTriggers(QAbstractItemView.AllEditTriggers)

    def _collect_dbs_related_pins(self) -> dict:
        """
        Check가 끝난 상태면 표에서 읽고, 아직 Check 전이면 저장돼 있던 값을 그대로
        유지한다(화면을 다시 열었다는 이유만으로 이미 입력해 둔 값이 날아가지 않도록).
        """
        if not self._dbs_check_done:
            saved = self.settings["pins"].get(DBS_RELATED_PINS_KEY) or {}
            return dict(saved)

        result: dict[str, str] = {}
        for row in range(self.dbs_related_table.rowCount()):
            name_item = self.dbs_related_table.item(row, 0)
            value_item = self.dbs_related_table.item(row, 1)
            if name_item is None:
                continue
            result[name_item.text()] = value_item.text().strip() if value_item else ""
        return result

    # ------------------------------------------------------------------
    # 값 수집 / 저장
    # ------------------------------------------------------------------
    def _collect_constants(self) -> dict:
        scalars = {}
        for key, _label, kind, _default in SCALAR_CONSTANT_DEFS:
            widget = self.scalar_widgets[key]
            if kind == "pdk_dropdown":
                scalars[key] = widget.currentData() or ""
            else:
                scalars[key] = widget.text().strip()

        voltage_map = {
            POWER_TYPE_COUNT_KEY: self.power_type_count_spin.value(),
            "values": {key: edit.text().strip() for key, edit in self.voltage_value_edits.items()},
            "names": {key: edit.text().strip() for key, edit in self.voltage_name_edits.items()},
        }

        return {"scalars": scalars, "voltage_map": voltage_map}

    def _collect_pins(self) -> dict:
        return {
            VIRTUAL_POWER_KEY: self.virtual_power_combo.currentData() or "",
            ENABLE_SIGNAL_KEY: self.enable_signal_edit.text().strip(),
            VIRTUAL_POWER_SWITCH_FUNCTION_KEY: self.switch_function_edit.text().strip(),
            VIRTUAL_POWER_PG_FUNCTION_KEY: self.pg_function_edit.text().strip(),
            POWER_DOWN_KEY: self.power_down_edit.text().strip(),
            POWER_DOWN_RISE_POWER_KEY: self.power_down_rise_edit.text().strip(),
            POWER_DOWN_FALL_POWER_KEY: self.power_down_fall_edit.text().strip(),
            POWER_DOWN_WHEN_KEY: self.power_down_when_edit.text().strip(),
            DBS_OUTPUT_KEY: self.dbs_output_edit.text().strip(),
            DBS_TIMING_SENSE_KEY: self.dbs_timing_sense_edit.text().strip(),
            DBS_TIMING_TYPE_KEY: self.dbs_timing_type_edit.text().strip(),
            DBS_RELATED_PINS_KEY: self._collect_dbs_related_pins(),
        }

    def _collect_all(self) -> dict:
        constants = self._collect_constants()
        return {
            "scalars": constants["scalars"],
            "voltage_map": constants["voltage_map"],
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
        if not self._dbs_check_done:
            # 버튼이 잠겨 있으므로 보통은 여기 오지 않지만, 방어적으로 한 번 더 막는다.
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText("• Run '1) Check DBS Output Pins' before validating.")
            return

        if self.show_loading:
            self.show_loading("Validating settings...")

        self._persist()
        errors = validate_constants(
            self.settings["scalars"], self.settings["voltage_map"], self.paired_pdk_files(),
        )
        errors += validate_pin_settings(self.settings["pins"], self.get_port_list_file())

        if self.hide_loading:
            self.hide_loading()

        if errors:
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText("\n".join(f"• {e}" for e in errors))
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
    # 화면이 다시 보일 때마다 (Step 1에서 돌아왔을 때 등) 최신 pin/PDK 정보 반영
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._populate_virtual_power_combo()
        self._populate_worst_case_pdk_combo()
        # Step1에서 Port List 파일이 바뀌었을 수 있으므로, 화면에 다시 들어올 때마다
        # DBS output pin Check 결과는 무효로 보고 다시 Check하게 한다.
        self._invalidate_dbs_check()
