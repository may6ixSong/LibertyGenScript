"""
settings_view.py

'Constants & Pin Settings' 화면 (Step 3, 2026-08 재설계 -> 2026-08 레이아웃 개편):
상수 값(class/process_prefix/output_prefix/DFF Cell Name/LUT Table/Worst case primitive
liberty)과 Pin 설정을 입력받는다.

2026-08 Voltage Map 이동: Voltage Map은 **Step 2 왼쪽 열**로 옮겨졌다(사용자가 voltage
condition을 직접 추가/삭제하고 이름도 정하는 형태로 바뀜, step2_udc/voltage_map_view.py).
저장 위치는 예전 그대로 step3_settings.json의 voltage_map key이므로, 이 화면이 설정을
저장할 때는 그 부분을 화면 값으로 덮어쓰지 않고 파일에서 다시 읽어 그대로 둔다.

2026-08 레이아웃 개편 - "Check가 안 보인다" 문제 해결:
  이전에는 Constants 카드와 Pin Settings 카드를 세로로 이어 붙이고 각 항목마다 설명
  문단(hint)을 그대로 깔아둬서, 정작 Validate보다 먼저 눌러야 하는
  "1) Check DBS Output Pins" 버튼이 한참 스크롤을 내려야 보였다. 그래서:
    - 화면을 좌우 2단(왼쪽 Constants / 오른쪽 Pin Settings)으로 나눴고,
    - Pin Settings 안에서도 DBS output pin + Check 블록을 **맨 위**로 올렸으며,
    - 모든 설명 문단은 제목/라벨 옆 hover 정보 아이콘(InfoIcon)의 툴팁으로 옮겼다.
  창 기본 너비도 함께 넓혔다 (ui/theme.py의 WINDOW_DEFAULT_WIDTH).

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
  다시 잠긴다. Step4에서 Back으로 돌아온 경우도 마찬가지다(showEvent).
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView, QFileDialog, QFormLayout, QFrame, QGraphicsOpacityEffect,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QScrollArea,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from step1_setup.port_list_reader import list_pins_by_port_type, list_port_pins_detailed
from step2_udc import udc_manager
from step2_udc.udc_validator import selected_pdk_files
from step3_settings import settings_manager
from step3_settings.constants_field_defs import SCALAR_CONSTANT_DEFS
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
from ui.ui_common import (
    NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row,
    build_label_with_info, build_section_header, run_export_config_dialog,
)

_HINT_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 11px;"
_RELATED_PIN_TABLE_MAX_HEIGHT = 200

# 2026-08: Pin Settings의 상위 pin 3개(DBS output pin / Virtual Power / Power down
# control signal)는 "여기가 상위단"이라는 게 한눈에 보이도록 아래 연계 필드보다 크고
# 굵게 쓴다. 반대로 연계 그룹의 보라색 안내 문구("These are required because ...")는
# 입력값보다 덜 튀도록 투명도를 낮춘다.
_TOP_PIN_LABEL_STYLE = f"color: {TEXT_COLOR}; font-size: 15px; font-weight: 700;"
_LINKED_CAPTION_OPACITY = 0.55


def _build_top_pin_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(_TOP_PIN_LABEL_STYLE)
    return label


# ---------------------------------------------------------------------------
# 설명 문구 - 화면에 문단으로 깔지 않고 hover 정보 아이콘 툴팁으로만 보여준다
# (2026-08 레이아웃 개편).
# ---------------------------------------------------------------------------
_CONSTANTS_INFO = (
    "class, process_prefix, output_prefix, DFF Cell Name, LUT Table and Worst case "
    "primitive liberty are all required.\n\n"
    "process_prefix / class are used in block4's cell attributes "
    "(e.g. {process_prefix}_class).\n"
    "output_prefix is used in the output filename: "
    "{output_prefix}lpv_{cell_name}_{dbs stem}.lib"
)

_SCALAR_FIELD_INFO = {
    "dff_cell_name": (
        "Used with LUT Table to locate the lu_table_template index_1/index_2 lines in the "
        "PDK/DK file: the first 'cell (DFF Cell Name)' declaration is found, then the first "
        "line after it containing the LUT Table name (its cell_rise/cell_fall block) "
        "supplies the index_1/index_2 values."
    ),
    "primitive_cell_name": (
        "The cell_rise/cell_fall block name searched for after the DFF Cell Name "
        "declaration; its index_1/index_2 lines become block3's lu_table_template."
    ),
    "worst_case_pdk": (
        "The lu_table_template is read from THIS PDK file only, once per run, and the same "
        "table is reused for every generated liberty - the other PDK files are never "
        "searched for it.\n\n"
        "Candidates are the PDK files selected by the Step 2 liberty settings."
    ),
}

_DBS_CHECK_INFO = (
    "Run this check BEFORE Validate. The pins recognized by the wildcard change whenever "
    "the Port List file changes, so the Related Pin list must be rebuilt from the current "
    "Port List first. Validate stays locked until then.\n\n"
    "Related Pin is auto-filled from the Port List's 'Related Pin' column for each "
    "recognized DBS output pin - edit any row if you want to use a different pin. Every "
    "Related Pin must still be a pin that exists in the Port List. It is written into "
    "block5's timing() related_bus_pins as entered here."
)

_DBS_TIMING_INFO = (
    "timing_sense / timing_type are shared by every recognized DBS output pin and are "
    "written into block5's timing() block. The values shown are the previous hard-coded "
    "defaults (non_unate / combinational)."
)

_VIRTUAL_POWER_INFO = (
    "Switch Function / PG Function do not allow wildcards (*). They are written as-is into "
    "block4's pg_pin switch_function / pg_function for the Virtual Power pin.\n\n"
    "Enable Signal keeps its wildcard behaviour."
)

_POWER_DOWN_INFO = (
    "Written into block5's {process_prefix}_acore_internal_power block of every pin "
    "matching the Power down control signal (_acore_rise_power / _acore_fall_power / "
    "_acore_when). The values shown are the previous hard-coded defaults."
)


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
            get_pdk_folder / get_dbs_folder: 최신 폴더 경로를 즉시 조회하는 콜백
                (Step 1 값 재사용). 'Worst case primitive liberty' 후보 자체는 Step2에서
                고른 PDK 파일 목록에서 오지만, 앞으로의 확장을 위해 그대로 받아둔다.
            get_port_list_file: 최신 Port List 파일 경로를 즉시 조회하는 콜백
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
        # "Check DBS Output Pins"를 눌러 현재 Port List로 pin을 펼친 상태인지 여부.
        # False인 동안에는 Validate 버튼이 잠겨 있다.
        self._dbs_check_done = False
        # 2) Validate를 통과했는지 여부. Output Path의 Browse를 눌렀는데 아직
        # 통과하지 못했으면, 그냥 잠긴 버튼으로 두는 대신 눌렀을 때 먼저 Check(1)와
        # Validate(2)를 진행하라는 안내창을 띄운다 (2026-08 추가 - 사용자들이 버튼이
        # 왜 안 눌리는지 몰랐다는 피드백 반영).
        self._settings_validated = False

        self._build_layout()

    # ------------------------------------------------------------------
    # 레이아웃 (좌: Constants / 우: Pin Settings)
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        title = QLabel("Constants & Pin Settings")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Configure constants and pin settings. Check the DBS output pins first, then "
            "validate before generating."
        )
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        columns = QHBoxLayout()
        columns.setSpacing(16)
        columns.addWidget(self._wrap_in_scroll(self._build_constants_card()), stretch=1)
        columns.addWidget(self._wrap_in_scroll(self._build_pins_card()), stretch=1)
        outer.addLayout(columns, stretch=1)

        outer.addLayout(self._build_bottom_bar())

    def _wrap_in_scroll(self, widget: QWidget) -> QScrollArea:
        """
        2단 중 한쪽이 길어져도 다른 쪽은 그대로 보이도록, 열마다 따로 스크롤을 준다.
        (전체를 하나의 스크롤로 감싸면 오른쪽 열의 Check 버튼이 다시 밀려 내려간다)
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        # 가로 스크롤은 끈다 - 열 폭에 맞춰 내용이 줄어들어야지, 가로로 넘쳐서
        # 입력칸 오른쪽이 잘리면 안 된다.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("transparentRow")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(12)
        layout.addWidget(widget)
        layout.addStretch()
        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # Constants
    # ------------------------------------------------------------------
    def _build_constants_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(12)

        layout.addWidget(build_section_header("Constants", _CONSTANTS_INFO))

        scalar_form = QFormLayout()
        scalar_form.setSpacing(8)
        # 라벨이 길어도(예: "Worst case primitive liberty") 입력칸이 오른쪽으로 밀려
        # 열 밖으로 넘치지 않도록, 폭이 모자라면 라벨 아래로 접히게 한다.
        scalar_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        scalar_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        for key, label, kind, default in SCALAR_CONSTANT_DEFS:
            saved = self.settings["scalars"].get(key, default)
            if kind == "pdk_dropdown":
                widget: QWidget = NoWheelComboBox()
            else:
                widget = QLineEdit(str(saved))
            widget.setMinimumWidth(120)
            self.scalar_widgets[key] = widget

            info = _SCALAR_FIELD_INFO.get(key)
            scalar_form.addRow(build_label_with_info(label, info) if info else label, widget)
        layout.addLayout(scalar_form)
        self._populate_worst_case_pdk_combo()

        return card

    def _populate_worst_case_pdk_combo(self) -> None:
        """
        'Worst case primitive liberty' 드롭다운을 다시 채운다. 후보는 Step2의 liberty
        setting들이 실제로 고른 PDK 파일들뿐이다 (2026-08 2차 재설계 - 예전에는 파일명
        자동 페어링이 성립한 PDK 목록이었다).
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
        """Step2의 liberty setting들이 고른 PDK 파일명 목록 (항상 새로 읽음)."""
        return selected_pdk_files(udc_manager.load_state())

    # ------------------------------------------------------------------
    # Pin Settings
    #   2026-08 레이아웃 개편: DBS output pin + Check 블록을 맨 위로 올려서, 화면에
    #   들어오자마자 "1) Check DBS Output Pins" 버튼이 스크롤 없이 보이도록 한다.
    # ------------------------------------------------------------------
    def _build_pins_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(6)

        layout.addWidget(build_section_header("Pin Settings"))

        self._build_dbs_output_section(layout)
        self._build_virtual_power_section(layout)
        self._build_power_down_section(layout)

        return card

    def _build_dbs_output_section(self, layout: QVBoxLayout) -> None:
        pins = self.settings["pins"]

        dbs_form = QFormLayout()
        dbs_form.setSpacing(10)
        dbs_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        dbs_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.dbs_output_edit, self.dbs_output_badge = self._build_wildcard_field(
            dbs_form, _build_top_pin_label("DBS output pin"), pins.get(DBS_OUTPUT_KEY, ""),
        )
        self.dbs_output_edit.textChanged.connect(lambda _text: self._invalidate_dbs_check())
        layout.addLayout(dbs_form)

        group = self._build_linked_group(
            layout, "These are required because a DBS output pin is used."
        )

        check_row = QHBoxLayout()
        self.dbs_check_btn = QPushButton("1) Check DBS Output Pins")
        self.dbs_check_btn.setObjectName("primaryButton")
        self.dbs_check_btn.clicked.connect(self._on_check_dbs_pins)
        check_row.addWidget(self.dbs_check_btn)
        check_row.addWidget(self._build_dbs_check_badge())
        self.dbs_check_status = QLabel("")
        self.dbs_check_status.setWordWrap(True)
        check_row.addWidget(self.dbs_check_status, stretch=1)
        group.addLayout(check_row)

        self.dbs_related_table = QTableWidget(0, 2)
        self.dbs_related_table.setHorizontalHeaderLabels(
            ["DBS Output Pin (from Port List)", "Related Pin"]
        )
        self.dbs_related_table.verticalHeader().setVisible(False)
        self.dbs_related_table.verticalHeader().setDefaultSectionSize(26)
        self.dbs_related_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.dbs_related_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.dbs_related_table.setMaximumHeight(_RELATED_PIN_TABLE_MAX_HEIGHT)
        self.dbs_related_table.setVisible(False)
        group.addWidget(self.dbs_related_table)

        inner_form = self._add_form(group)
        self.dbs_timing_sense_edit = QLineEdit(str(pins.get(DBS_TIMING_SENSE_KEY, "")))
        self.dbs_timing_type_edit = QLineEdit(str(pins.get(DBS_TIMING_TYPE_KEY, "")))
        inner_form.addRow(build_label_with_info("timing_sense", _DBS_TIMING_INFO), self.dbs_timing_sense_edit)
        inner_form.addRow(build_label_with_info("timing_type", _DBS_TIMING_INFO), self.dbs_timing_type_edit)

    def _build_virtual_power_section(self, layout: QVBoxLayout) -> None:
        pins = self.settings["pins"]

        top_form = QFormLayout()
        top_form.setSpacing(10)
        top_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        top_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.virtual_power_combo = NoWheelComboBox()
        self._populate_virtual_power_combo()
        top_form.addRow(_build_top_pin_label("Virtual Power (power gate)"), self.virtual_power_combo)
        layout.addLayout(top_form)

        group = self._build_linked_group(
            layout, "These are required because a Virtual Power (power gate) pin is used."
        )
        form = self._add_form(group)
        self.enable_signal_edit, self.enable_signal_badge = self._build_wildcard_field(
            form, "Enable Signal for power gate", pins.get(ENABLE_SIGNAL_KEY, ""),
        )
        self.switch_function_edit, self.switch_function_badge = self._build_plain_pin_field(
            form, "Virtual Power Switch Function",
            pins.get(VIRTUAL_POWER_SWITCH_FUNCTION_KEY, ""), _VIRTUAL_POWER_INFO,
        )
        self.pg_function_edit, self.pg_function_badge = self._build_plain_pin_field(
            form, "Virtual Power PG Function",
            pins.get(VIRTUAL_POWER_PG_FUNCTION_KEY, ""), _VIRTUAL_POWER_INFO,
        )

    def _build_power_down_section(self, layout: QVBoxLayout) -> None:
        pins = self.settings["pins"]

        pd_form = QFormLayout()
        pd_form.setSpacing(10)
        pd_form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        pd_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.power_down_edit, self.power_down_badge = self._build_wildcard_field(
            pd_form, _build_top_pin_label("Power down control signal"),
            pins.get(POWER_DOWN_KEY, ""),
        )
        layout.addLayout(pd_form)

        group = self._build_linked_group(
            layout, "These are required because a Power down control signal is used."
        )
        form = self._add_form(group)
        self.power_down_rise_edit = QLineEdit(str(pins.get(POWER_DOWN_RISE_POWER_KEY, "")))
        self.power_down_fall_edit = QLineEdit(str(pins.get(POWER_DOWN_FALL_POWER_KEY, "")))
        self.power_down_when_edit = QLineEdit(str(pins.get(POWER_DOWN_WHEN_KEY, "")))
        form.addRow(build_label_with_info("rise power", _POWER_DOWN_INFO), self.power_down_rise_edit)
        form.addRow(build_label_with_info("fall power", _POWER_DOWN_INFO), self.power_down_fall_edit)
        form.addRow(build_label_with_info("when", _POWER_DOWN_INFO), self.power_down_when_edit)

    def _build_dbs_check_badge(self) -> QLabel:
        """
        "Validate보다 먼저"라는 경고를 문단 대신 한 칸짜리 배지 + 툴팁으로 보여준다
        (2026-08 레이아웃 개편 - 예전엔 세 줄짜리 배너였다).
        """
        badge = QLabel("⚠ required first")
        badge.setToolTip(_DBS_CHECK_INFO)
        badge.setStyleSheet(
            f"background-color: {WARNING_BG}; border: 1px solid {WARNING_BORDER}; "
            f"color: {WARNING_TEXT}; border-radius: 6px; padding: 4px 8px; font-size: 11px;"
        )
        return badge

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
        # 시스템 안내 문구는 입력값보다 덜 튀어야 하므로 투명도를 낮춘다 (2026-08).
        caption_opacity = QGraphicsOpacityEffect(caption_label)
        caption_opacity.setOpacity(_LINKED_CAPTION_OPACITY)
        caption_label.setGraphicsEffect(caption_opacity)
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
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        return form

    def _build_wildcard_field(
        self, form: QFormLayout, label, initial: str, info: str = "",
    ) -> tuple[QLineEdit, QLabel]:
        edit, badge = self._build_field_with_badge(form, label, initial, info)
        edit.textChanged.connect(lambda: self._update_wildcard_badge(edit, badge))
        self._update_wildcard_badge(edit, badge)
        return edit, badge

    def _build_plain_pin_field(
        self, form: QFormLayout, label, initial: str, info: str = "",
    ) -> tuple[QLineEdit, QLabel]:
        """와일드카드를 허용하지 않는 pin 입력 (입력에 '*'가 있으면 즉시 빨간 안내)."""
        edit, badge = self._build_field_with_badge(form, label, initial, info)
        edit.textChanged.connect(lambda: self._update_no_wildcard_badge(edit, badge))
        self._update_no_wildcard_badge(edit, badge)
        return edit, badge

    def _build_field_with_badge(
        self, form: QFormLayout, label, initial: str, info: str = "",
    ) -> tuple[QLineEdit, QLabel]:
        """label은 문자열 또는 위젯(예: 상위 pin용 굵은 라벨) 둘 다 가능하다."""
        container = QWidget()
        container.setObjectName("transparentRow")
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(2)

        edit = QLineEdit(initial)
        badge = QLabel("")
        badge.setStyleSheet("font-size: 11px;")
        container_layout.addWidget(edit)
        container_layout.addWidget(badge)

        form.addRow(build_label_with_info(label, info) if info else label, container)
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
        layout.setSpacing(8)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        output_row = QHBoxLayout()
        output_row.addWidget(QLabel("Output Path"))
        self.output_path_edit = QLineEdit(self.settings.get("output_path", ""))
        self.output_path_edit.setEnabled(False)
        self.output_path_edit.textChanged.connect(self._update_generate_button_state)
        output_row.addWidget(self.output_path_edit, stretch=1)
        # 2026-08 변경: 예전에는 Validate를 통과하기 전엔 이 버튼 자체가 disabled라서,
        # 사용자가 "왜 안 눌리는지" 모른다는 피드백이 있었다. 이제 버튼은 항상 눌리게
        # 두고, 클릭했는데 아직 Validate 전이면 그 자리에서 안내창을 띄운다
        # (self._on_browse_output).
        self.output_browse_btn = QPushButton("Browse...")
        self.output_browse_btn.clicked.connect(self._on_browse_output)
        output_row.addWidget(self.output_browse_btn)
        layout.addLayout(output_row)

        self.export_btn = QPushButton("Export Config")
        self.export_btn.clicked.connect(self._on_export_config)

        self.validate_btn = QPushButton("2) Validate")
        self.validate_btn.setObjectName("primaryButton")
        self.validate_btn.clicked.connect(self._on_validate)

        self.generate_btn = QPushButton("Generate")
        self.generate_btn.setObjectName("primaryButton")
        self.generate_btn.setEnabled(False)
        self.generate_btn.clicked.connect(self._on_generate_clicked)

        self.back_btn = build_back_button(self.on_back)
        layout.addLayout(build_bottom_button_row(
            self.back_btn, self.validate_btn, self.generate_btn,
            extra_left_buttons=(self.export_btn,),
        ))

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
        화면을 다시 열었을 때(= Port List가 바뀌었을 수 있을 때, Step4에서 Back으로
        돌아온 경우 포함) 호출된다.
        """
        self._dbs_check_done = False
        self._settings_validated = False
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
            self.output_browse_btn.setToolTip(
                "Run '1) Check DBS Output Pins' and '2) Validate' first."
            )
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
            f"✓ {len(recognized)} DBS output pin(s) recognized. Related Pin was auto-filled "
            "from the Port List - review and edit any row if you need a different pin, "
            "then Validate."
        )
        self.validate_btn.setEnabled(True)
        self.validate_btn.setToolTip("")

    def _fill_related_pin_table(self, recognized: list[str]) -> None:
        """
        인식된 pin마다 한 행씩. Related Pin 칸은 **Port List의 'Related Pin' 컬럼
        값으로 자동 채워진다**(2026-08 변경 - 예전엔 빈 칸으로 두고 사용자가 직접
        Port List를 보고 옮겨 적어야 했다). 이미 이 pin에 대해 저장해 둔 값(직접
        수정했던 값 포함)이 있으면 그걸 그대로 우선하고, 처음 보는 pin만 Port List
        값으로 채운다. 어느 쪽이든 표에서 바로 수정할 수 있다 - Port List와 다른
        pin을 쓰고 싶을 수도 있으므로 자동 채움은 기본값일 뿐 강제가 아니다.
        """
        saved = self.settings["pins"].get(DBS_RELATED_PINS_KEY) or {}
        port_list_related = {
            pin["pin_name"]: (pin.get("related_pin") or "").strip()
            for pin in list_port_pins_detailed(self.get_port_list_file())
        }
        table = self.dbs_related_table
        table.setRowCount(len(recognized))
        for row, pin_name in enumerate(recognized):
            name_item = QTableWidgetItem(pin_name)
            name_item.setFlags(Qt.ItemIsEnabled)  # 읽기 전용
            table.setItem(row, 0, name_item)
            default_value = saved[pin_name] if pin_name in saved else port_list_related.get(pin_name, "")
            table.setItem(row, 1, QTableWidgetItem(str(default_value)))
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

        return {"scalars": scalars}

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
            # Voltage Map은 Step 2에서 편집한다(화면만 옮겨졌고 저장 위치는 여기 그대로).
            # 이 화면이 들고 있던 옛 값으로 덮어쓰지 않도록 항상 파일에서 다시 읽는다.
            "voltage_map": settings_manager.load_voltage_map(),
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
        errors = validate_constants(self.settings["scalars"], self.paired_pdk_files())
        errors += validate_pin_settings(self.settings["pins"], self.get_port_list_file())

        if self.hide_loading:
            self.hide_loading()

        if errors:
            self._settings_validated = False
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText("\n".join(f"• {e}" for e in errors))
            self.output_path_edit.setEnabled(False)
            self.output_browse_btn.setToolTip(
                "Run '1) Check DBS Output Pins' and '2) Validate' first."
            )
            self.generate_btn.setEnabled(False)
        else:
            self._settings_validated = True
            self.result_label.setStyleSheet(f"color: {SUCCESS_COLOR};")
            self.result_label.setText("Settings passed validation. Choose an output path to continue.")
            self.output_path_edit.setEnabled(True)
            self.output_browse_btn.setToolTip("")
            self._update_generate_button_state()

    def _update_generate_button_state(self) -> None:
        can_generate = self.output_path_edit.isEnabled() and bool(self.output_path_edit.text().strip())
        self.generate_btn.setEnabled(can_generate)

    def _on_browse_output(self) -> None:
        # 2026-08 추가: Validate를 아직 통과하지 못했으면 대화상자를 열지 않고, 먼저
        # Check(1) + Validate(2)를 진행하라는 안내창을 띄운다 - 예전에는 버튼 자체가
        # disabled라서 사용자가 왜 안 눌리는지 몰랐다는 피드백을 반영.
        if not self._settings_validated:
            QMessageBox.information(
                self, "Validate First",
                "Run '1) Check DBS Output Pins' and '2) Validate' before choosing an "
                "output path.",
            )
            return

        # DontUseNativeDialog(2026-08 추가): OS 고유 대화상자는 네트워크 폴더를 훑느라
        # 느릴 수 있고, 이 앱의 Ctrl+C 강제 종료 단축키(ui/force_quit.py)가 닿지 않는
        # 별도 창이라 열려 있는 동안은 먹히지 않는다. Qt 자체 대화상자를 쓰면 같은
        # 이벤트 루프 안에서 열리므로 열려 있는 동안에도 Ctrl+C가 그대로 동작한다.
        #
        # 시작 폴더(2026-08 추가): 힌트 없이 열면 OS/Qt가 홈 디렉터리(사내 HPC망에서는
        # 대개 네트워크 마운트)부터 훑어야 해서 대화상자를 여는 것 자체가 느려질 수
        # 있다. 이미 골라 둔 Output Path, 없으면 Step1의 PDK Folder(이미 접근 가능하다고
        # 확인된 위치)를 힌트로 준다.
        start_dir = self.output_path_edit.text().strip() or self.get_pdk_folder()
        path = QFileDialog.getExistingDirectory(
            self, "Select Output Path", start_dir, QFileDialog.DontUseNativeDialog,
        )
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
    # Config export (2026-08 추가)
    # ------------------------------------------------------------------
    def _on_export_config(self) -> None:
        self._persist()
        run_export_config_dialog(self, self.get_pdk_folder())

    # ------------------------------------------------------------------
    # 화면이 다시 보일 때마다 (Step 2에서 왔을 때 / Step4에서 Back으로 돌아왔을 때)
    # 최신 pin/PDK 정보 반영 + Check 결과 무효화
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._populate_virtual_power_combo()
        self._populate_worst_case_pdk_combo()
        # Step1에서 Port List 파일이 바뀌었을 수 있고, Step4에서 Back으로 돌아온 경우도
        # 처음부터 다시 밟아야 하므로, 화면에 들어올 때마다 Check 결과는 무효로 본다.
        self._invalidate_dbs_check()
