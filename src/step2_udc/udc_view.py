"""
udc_view.py

'UDC Settings' 화면 (Step 2, 2026-08 전면 재설계 -> 2026-08 2차 재설계).

2026-08 레이아웃 개편: 화면을 좌우 2단으로 나눴다.
  - **왼쪽**: "Common Fields"(이번에 생성할 모든 조합이 공유하는 값, 한 번만 입력) +
    "Voltage Map"(Step 3에서 이리로 옮겨옴 - 사용자가 voltage condition을 직접 추가/
    삭제하고 이름도 정한다. voltage_map_view.VoltageMapPanel).
  - **오른쪽**: "Liberty Settings" 카드에서 **liberty 파일 1개당 setting 1개**를 직접 추가한다.
    각 setting은 corner / beol inform / voltage / temperature / condition 을 입력받고,
    그 값들로 PDK 폴더에서 맞을 것 같은 파일을 자동으로 찾아 드롭다운 맨 위에 추천으로
    올려 준다. PDK를 고르면 같은 corner/voltage/temperature를 가진 DBS output 파일이
    자동으로 엮이고, 자동으로 못 고르면 사용자가 직접 선택한다.

PDK 파일명의 beol inform 토큰은 사용자가 고른 beol inform과 다를 확률이 크기 때문에
(2026-08 확인), 추천의 필수 조건은 corner + voltage + temperature 세 가지이고 beol은
순위 가산점으로만 쓴다 (udc_field_defs.match_pdk_file 참고).

각 setting의 Condition 드롭다운 선택지는 코드에 고정된 bst/wst/tiv가 아니라 **왼쪽
Voltage Map에 정의된 condition 이름들**이다. condition을 추가/삭제하거나 이름을 고치면
즉시 모든 setting의 드롭다운이 다시 채워진다(_on_voltage_conditions_changed).

Validate 버튼을 누르면 PDK/DBS 폴더를 다시 스캔해서, 공통 필드/Voltage Map/모든 setting이
빈 값 없이 채워졌는지 + 고른 파일들이 실제로 존재하는지를 검사한다. 화면에 다시 들어오면
(Step1/Step3에서 돌아오면) 검사 결과는 무효가 되고 Next가 다시 잠긴다.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QRegExp, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QRegExpValidator
from PyQt5.QtWidgets import (
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSizePolicy, QSplitter, QVBoxLayout, QWidget,
)

from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step2_udc import udc_manager
from step2_udc.udc_field_defs import (
    COMMON_FIELD_DEFS, ENTRY_BEOL_KEY, ENTRY_CONDITION_KEY, ENTRY_CORNER_KEY,
    ENTRY_DBS_KEY, ENTRY_FIELD_DEFS, ENTRY_ID_KEY, ENTRY_PDK_KEY, ENTRY_TEMPERATURE_KEY,
    ENTRY_VOLTAGE_KEY, MATCH_EXACT, TIMING_STATE_OPTIONS, auto_select_dbs_file,
    format_temperature_token, format_voltage_token, new_entry, recommend_dbs_files,
    recommend_pdk_files,
)
from step2_udc.udc_validator import validate_common_fields, validate_entries
from step2_udc.voltage_map_view import VoltageMapPanel
from step3_settings import settings_manager
from step3_settings.settings_validator import validate_voltage_map
from ui.theme import (
    ERROR_COLOR, MUTED_TEXT_COLOR, RECOMMEND_BG, RECOMMEND_TEXT, SUCCESS_COLOR, TEXT_COLOR,
)
from ui.ui_common import (
    NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row,
    build_hint, build_section_header, run_export_config_dialog,
)

_NUMBER_REGEX = QRegExp(r"^-?\d*\.?\d*$")
_SELECT_LABEL = "(Select)"
_NONE_LABEL = "(None)"
_RECOMMEND_PREFIX = "★ "  # ★

_COMMON_FIELDS_INFO = (
    "These values are shared by every liberty file generated in this run.\n"
    "Area / Width / Height / Static Current must be numbers; Cell Name is used in the "
    "output filename ({output_prefix}lpv_{cell_name}_{dbs stem}.lib)."
)

_LIBERTY_SETTINGS_INFO = (
    "One liberty file is generated per setting below.\n\n"
    "Corner / BEOL Inform / Voltage / Temperature are used to search the PDK Folder for "
    "the file that most likely matches: candidates are moved to the top of the "
    "'Primitive liberty file' dropdown and highlighted (★).\n\n"
    "A PDK filename's BEOL token often differs from the BEOL Inform you select, so the "
    "search only requires corner + voltage + temperature to match; a BEOL match just "
    "ranks the file higher.\n\n"
    "Choosing a PDK file auto-selects the DBS output file with the same corner / voltage "
    "/ temperature. If no single file matches, pick one yourself."
)

_ENTRY_FIELD_INFO = {
    ENTRY_CORNER_KEY: "Appears verbatim in both the PDK and DBS filenames (e.g. ..._ffpg_...).",
    ENTRY_BEOL_KEY: (
        "The BEOL token in the actual PDK filename is often different from this value, so "
        "it is not required to match - it only ranks a candidate higher."
    ),
    ENTRY_VOLTAGE_KEY: "Written as 0p####v in filenames (0.72 → 0p7200v).",
    ENTRY_TEMPERATURE_KEY: "Written as ##c / m##c in filenames (40 → 40c, -40 → m40c).",
    ENTRY_CONDITION_KEY: (
        "Selects which voltage condition of the Voltage Map (left column) supplies this "
        "liberty's voltage_map values. Add / rename conditions there - the list here "
        "follows it."
    ),
}


def _apply_number_validator(edit: QLineEdit) -> None:
    edit.setValidator(QRegExpValidator(_NUMBER_REGEX, edit))


def _fill_option_combo(combo: NoWheelComboBox, options: list[str], current: str) -> None:
    """
    고정 선택지(corner/beol) 또는 Voltage Map에서 온 condition 이름으로 드롭다운을 채운다.
    current가 목록에 없으면 (Select) 상태가 되지만, 대소문자만 다른 값이면 목록에 있는
    이름으로 정규화해서 선택을 살린다 - 예전 config의 'bst'가 기본 condition 이름
    'BST'와 그대로 이어지도록.
    """
    combo.clear()
    combo.addItem(_SELECT_LABEL, "")
    for option in options:
        combo.addItem(option, option)

    current = str(current or "").strip()
    if not current:
        combo.setCurrentIndex(0)
        return
    index = combo.findData(current)
    if index < 0:
        lowered = current.lower()
        for option in options:
            if option.lower() == lowered:
                index = combo.findData(option)
                break
    combo.setCurrentIndex(index if index >= 0 else 0)


def _populate_file_combo(
    combo: NoWheelComboBox, all_files: list[str], recommended: list[tuple[str, int]], current: str,
) -> None:
    """
    파일 선택 드롭다운을 채운다. 추천 파일은 맨 위로 올리고 ★ + 초록 배경으로
    highlight하며, 구분선 아래에 나머지 전체 목록을 그대로 둔다 (추천이 틀렸을 때
    사용자가 직접 다른 파일을 고를 수 있어야 하므로).
    """
    combo.blockSignals(True)
    combo.clear()
    combo.addItem(_SELECT_LABEL, "")

    recommended_names = [name for name, _rank in recommended]
    highlight_brush = QBrush(QColor(RECOMMEND_BG))
    text_brush = QBrush(QColor(RECOMMEND_TEXT))
    bold = QFont()
    bold.setBold(True)

    for name, rank in recommended:
        combo.addItem(_RECOMMEND_PREFIX + name, name)
        index = combo.count() - 1
        combo.setItemData(index, highlight_brush, Qt.BackgroundRole)
        combo.setItemData(index, text_brush, Qt.ForegroundRole)
        if rank == MATCH_EXACT:
            combo.setItemData(index, bold, Qt.FontRole)
        combo.setItemData(
            index,
            "Matches this setting" + (" (BEOL matches too)" if rank == MATCH_EXACT else ""),
            Qt.ToolTipRole,
        )

    others = [name for name in all_files if name not in recommended_names]
    if recommended and others:
        combo.insertSeparator(combo.count())
    for name in others:
        combo.addItem(name, name)

    index = combo.findData(current) if current else 0
    combo.setCurrentIndex(index if index >= 0 else 0)
    combo.blockSignals(False)


class _EntryCard(QFrame):
    """
    liberty 1개분 setting 카드. corner/beol/voltage/temperature/condition 입력이 바뀌면
    on_changed를 호출해서 부모가 PDK/DBS 추천을 다시 계산하도록 한다.
    """

    def __init__(
        self,
        entry: dict,
        index: int,
        condition_names: list[str],
        on_changed: Callable[["_EntryCard"], None],
        on_pdk_selected: Callable[["_EntryCard"], None],
        on_remove: Callable[["_EntryCard"], None],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("entryCard")
        self.entry_id = entry.get(ENTRY_ID_KEY, "")
        self._on_changed = on_changed
        self._on_pdk_selected = on_pdk_selected
        self._on_remove = on_remove
        self._condition_names = list(condition_names)
        self.select_widgets: dict[str, NoWheelComboBox] = {}
        self.number_widgets: dict[str, QLineEdit] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        layout.addLayout(self._build_header_row(index))
        layout.addLayout(self._build_setting_row(entry))
        layout.addLayout(self._build_file_row(entry))

        self.match_label = QLabel("")
        self.match_label.setWordWrap(True)
        self.match_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(self.match_label)

    # -- 구성 ---------------------------------------------------------------
    def _build_header_row(self, index: int) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)
        self.index_label = QLabel(f"Liberty #{index + 1}")
        self.index_label.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 700;")
        row.addWidget(self.index_label)
        row.addStretch()
        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(self._confirm_remove)
        row.addWidget(remove_btn)
        return row

    def _confirm_remove(self) -> None:
        # 2026-08 추가: 실수로 setting을 지우는 것을 막기 위해 삭제 전에 확인창을
        # 띄운다. 되돌릴 방법이 없으므로(입력값이 즉시 사라짐) 기본 선택지는 No.
        answer = QMessageBox.question(
            self, "Remove Liberty Setting",
            f"Remove {self.index_label.text()}? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._on_remove(self)

    def _build_setting_row(self, entry: dict) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        for column, (key, label, kind, extra) in enumerate(ENTRY_FIELD_DEFS):
            caption = QLabel(label)
            caption.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
            caption.setToolTip(_ENTRY_FIELD_INFO.get(key, ""))
            grid.addWidget(caption, 0, column)

            if kind in ("select", "condition_select"):
                combo = NoWheelComboBox()
                combo.setToolTip(_ENTRY_FIELD_INFO.get(key, ""))
                options = self._condition_names if kind == "condition_select" else list(extra)
                _fill_option_combo(combo, options, str(entry.get(key, "")))
                combo.currentIndexChanged.connect(lambda _i: self._on_changed(self))
                self.select_widgets[key] = combo
                if kind == "condition_select":
                    self.condition_combo = combo
                grid.addWidget(combo, 1, column)
            else:
                grid.addWidget(self._build_number_field(key, extra, entry), 1, column)
            grid.setColumnStretch(column, 1)

        return grid

    def _build_number_field(self, key: str, unit: str, entry: dict) -> QWidget:
        container = QWidget()
        container.setObjectName("transparentRow")
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)

        edit = QLineEdit(str(entry.get(key, "")))
        _apply_number_validator(edit)
        edit.setToolTip(_ENTRY_FIELD_INFO.get(key, ""))
        edit.textChanged.connect(lambda _t: self._on_changed(self))
        self.number_widgets[key] = edit
        row.addWidget(edit, stretch=1)

        unit_label = QLabel(unit)
        unit_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-weight: 600;")
        row.addWidget(unit_label)
        return container

    def _build_file_row(self, entry: dict) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        pdk_caption = QLabel("Primitive liberty file (PDK)")
        pdk_caption.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        grid.addWidget(pdk_caption, 0, 0)
        self.pdk_combo = NoWheelComboBox()
        self.pdk_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.pdk_combo.currentIndexChanged.connect(lambda _i: self._on_pdk_selected(self))
        grid.addWidget(self.pdk_combo, 1, 0)

        dbs_caption = QLabel("DBS output file (auto-mapped)")
        dbs_caption.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        grid.addWidget(dbs_caption, 0, 1)
        self.dbs_combo = NoWheelComboBox()
        self.dbs_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        grid.addWidget(self.dbs_combo, 1, 1)

        grid.setColumnStretch(0, 3)
        grid.setColumnStretch(1, 2)
        return grid

    # -- 값 읽기/쓰기 -------------------------------------------------------
    def set_condition_names(
        self, condition_names: list[str], rename: tuple | None = None,
    ) -> None:
        """
        Voltage Map의 condition이 추가/삭제/이름변경될 때마다 Condition 드롭다운을 다시
        채운다. 지금 고른 값은 (대소문자 무시로) 살아남는 한 그대로 유지되고, rename
        (직전 이름, 새 이름)이 주어지면 그 이름을 고르고 있었을 때 새 이름으로 따라간다.
        """
        self._condition_names = list(condition_names)
        combo = getattr(self, "condition_combo", None)
        if combo is None:
            return
        current = combo.currentData() or ""
        if rename and current == rename[0]:
            current = rename[1]
        combo.blockSignals(True)
        _fill_option_combo(combo, self._condition_names, current)
        combo.blockSignals(False)

    def set_index(self, index: int) -> None:
        self.index_label.setText(f"Liberty #{index + 1}")

    def collect(self) -> dict:
        entry = {ENTRY_ID_KEY: self.entry_id}
        for key, combo in self.select_widgets.items():
            entry[key] = combo.currentData() or ""
        for key, edit in self.number_widgets.items():
            entry[key] = edit.text().strip()
        entry[ENTRY_PDK_KEY] = self.pdk_combo.currentData() or ""
        entry[ENTRY_DBS_KEY] = self.dbs_combo.currentData() or ""
        return entry

    def set_match_status(self, text: str, status: str = "info") -> None:
        color = {
            "success": SUCCESS_COLOR, "error": ERROR_COLOR,
        }.get(status, MUTED_TEXT_COLOR)
        self.match_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self.match_label.setText(text)


class UDCView(QWidget):
    def __init__(
        self,
        get_pdk_folder: Callable[[], str],
        get_dbs_folder: Callable[[], str],
        on_next: Callable[[], None] | None = None,
        on_back: Callable[[], None] | None = None,
        parent=None,
    ):
        """
        Args:
            get_pdk_folder: 최신 PDK Folder 경로를 즉시 조회하는 콜백 (Step 1 값 재사용)
            get_dbs_folder: 최신 DBS Simulation Folder 경로를 즉시 조회하는 콜백
            on_next: 모든 검사를 통과한 뒤 Next 버튼을 눌렀을 때 호출되는 콜백
            on_back: Back 버튼을 눌렀을 때 호출되는 콜백 (이전 Step으로 이동)
        """
        super().__init__(parent)
        self.get_pdk_folder = get_pdk_folder
        self.get_dbs_folder = get_dbs_folder
        self.on_next = on_next
        self.on_back = on_back

        self.state: dict = udc_manager.load_state()
        # Voltage Map은 화면만 여기(Step 2 왼쪽 열)로 옮겨왔을 뿐, 저장 위치는 예전
        # 그대로 config/step3_settings.json의 voltage_map key다.
        self.voltage_map: dict = settings_manager.load_voltage_map()
        self.common_widgets: dict[str, QWidget] = {}
        self.entry_cards: list[_EntryCard] = []
        self.pdk_files: list[str] = []
        self.dbs_files: list[str] = []

        self._build_layout()
        self._rescan_files()
        self._rebuild_entry_cards(udc_manager.get_entries(self.state))

    # ------------------------------------------------------------------
    # 레이아웃
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(14)

        title = QLabel("UDC Settings")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Enter the common fields and the voltage map on the left, then add one liberty "
            "setting per file you want to generate on the right."
        )
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        # 2026-08 레이아웃 개편: Step3처럼 좌우 2단으로 나눈다.
        #   왼쪽  = Common Fields + Voltage Map (Voltage Map이 Step3에서 여기로 옮겨옴)
        #   오른쪽 = Liberty Settings (setting 1개 = liberty 파일 1개)
        # 2026-08 추가: 오른쪽 Liberty Settings 쪽 setting이 많아질수록 왼쪽보다 훨씬
        # 넓은 공간이 필요하다는 피드백을 반영해, 기본 폭 비율을 1:1 대신 왼쪽을 1/4
        # 줄인 3:5로 시작한다. 또한 QHBoxLayout 대신 QSplitter를 써서 사용자가 두 열
        # 사이 경계에 마우스를 올리면 커서가 좌우 조절 아이콘으로 바뀌며 드래그로 폭을
        # 직접 조절할 수 있게 한다(QSplitter 기본 동작).
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(self._build_common_card())
        left.addWidget(self._build_voltage_map_panel(), stretch=1)
        left_container = QWidget()
        left_container.setObjectName("transparentRow")
        left_container.setLayout(left)

        self.column_splitter = QSplitter(Qt.Horizontal)
        self.column_splitter.setObjectName("columnSplitter")
        self.column_splitter.setChildrenCollapsible(False)
        self.column_splitter.addWidget(left_container)
        self.column_splitter.addWidget(self._build_entries_card())
        self.column_splitter.setStretchFactor(0, 3)
        self.column_splitter.setStretchFactor(1, 5)
        outer.addWidget(self.column_splitter, stretch=1)
        # setSizes()를 지금(생성자 안, 아직 화면에 실제로 표시되기 전) 호출하면 위젯
        # 폭이 아직 0에 가까워 요청한 비율이 무시되고 나중에 실제 창 크기로 보일 때
        # 엉뚱한 비율(왼쪽이 더 넓어짐)로 굳어지는 것을 실측으로 확인했다. 그래서 실제
        # 폭을 알 수 있는 첫 showEvent에서 한 번만 적용한다(_apply_default_column_sizes).
        self._column_sizes_applied = False

        self.export_btn = QPushButton("Export Config")
        self.export_btn.clicked.connect(self._on_export_config)

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.setObjectName("primaryButton")
        self.validate_btn.clicked.connect(self._on_validate)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("primaryButton")
        self.next_btn.setEnabled(False)
        self.next_btn.setToolTip("Run Validate first.")
        self.next_btn.clicked.connect(self._on_next_clicked)

        self.back_btn = build_back_button(self.on_back)
        outer.addLayout(build_bottom_button_row(
            self.back_btn, self.validate_btn, self.next_btn,
            extra_left_buttons=(self.export_btn,),
        ))

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        outer.addWidget(self.result_label)

    def _build_common_card(self) -> QFrame:
        """
        공통 필드 8개를 세로로 길게 늘어놓지 않고 2열 그리드로 배치한다 - 같은 열
        아래쪽의 Voltage Map이 차지할 세로 공간을 확보하기 위해서
        (2026-08 레이아웃 개편).
        """
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(build_section_header("Common Fields", _COMMON_FIELDS_INFO))

        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        # 2026-08 레이아웃 개편으로 이 카드가 화면 왼쪽 절반만 쓰게 되어 4열 -> 2열.
        columns = 2
        common = self.state["common"]

        for position, (key, label, kind) in enumerate(COMMON_FIELD_DEFS):
            row, column = divmod(position, columns)
            form = QFormLayout()
            form.setContentsMargins(0, 0, 0, 0)
            form.setSpacing(4)
            form.setLabelAlignment(Qt.AlignLeft)

            if kind == "dropdown":
                widget: QWidget = NoWheelComboBox()
                widget.addItems(TIMING_STATE_OPTIONS)
                current = common.get(key, "")
                if current:
                    index = widget.findText(current)
                    if index >= 0:
                        widget.setCurrentIndex(index)
            else:
                widget = QLineEdit(str(common.get(key, "")))
                if kind == "number":
                    _apply_number_validator(widget)

            self.common_widgets[key] = widget
            form.addRow(label, widget)
            grid.addLayout(form, row, column)
            grid.setColumnStretch(column, 1)

        layout.addLayout(grid)
        return card

    def _build_voltage_map_panel(self) -> VoltageMapPanel:
        self.voltage_map_panel = VoltageMapPanel(
            self.voltage_map, self._on_voltage_conditions_changed,
        )
        return self.voltage_map_panel

    def _on_voltage_conditions_changed(self, rename: tuple | None = None) -> None:
        """
        Voltage Map의 condition이 추가/삭제되거나 이름이 바뀌면, 오른쪽 liberty
        setting들의 Condition 드롭다운을 즉시 다시 채운다.

        rename이 주어지면("직전 이름", "새 이름") 그 이름을 고르고 있던 setting의 선택은
        새 이름으로 따라간다 - 이름만 고쳤을 뿐인데 선택이 풀리면 안 되기 때문.

        패널을 만드는 도중(생성자 안)에도 한 번 불리므로, 아직 패널 참조가 없거나
        entry 카드가 만들어지기 전이면 조용히 넘어간다 - 카드가 만들어질 때
        _rebuild_entry_cards가 어차피 현재 이름 목록을 넘겨준다.
        """
        if not hasattr(self, "voltage_map_panel"):
            return
        names = self.voltage_map_panel.condition_names()
        for card in self.entry_cards:
            card.set_condition_names(names, rename)

    def _build_entries_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(build_section_header("Liberty Settings", _LIBERTY_SETTINGS_INFO))
        header.addStretch()
        self.entries_summary_label = QLabel("")
        self.entries_summary_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        header.addWidget(self.entries_summary_label)
        add_btn = QPushButton("+ Add Liberty Setting")
        add_btn.setObjectName("primaryButton")
        add_btn.clicked.connect(self._on_add_entry)
        header.addWidget(add_btn)
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        container.setObjectName("transparentRow")
        self.entries_layout = QVBoxLayout(container)
        self.entries_layout.setContentsMargins(0, 0, 8, 0)
        self.entries_layout.setSpacing(10)
        self.entries_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        self.entries_empty_label = build_hint(
            "No liberty settings yet. Click '+ Add Liberty Setting' to add one - "
            "each setting produces exactly one liberty file."
        )
        layout.addWidget(self.entries_empty_label)
        return card

    # ------------------------------------------------------------------
    # 파일 목록 / entry 카드 관리
    # ------------------------------------------------------------------
    def _rescan_files(self) -> None:
        self.pdk_files = list_pdk_lib_files(self.get_pdk_folder())
        self.dbs_files = list_dbs_mt0_files(self.get_dbs_folder())

    def _rebuild_entry_cards(self, entries: list[dict]) -> None:
        for card in self.entry_cards:
            self.entries_layout.removeWidget(card)
            card.deleteLater()
        self.entry_cards = []

        condition_names = (
            self.voltage_map_panel.condition_names()
            if hasattr(self, "voltage_map_panel") else []
        )
        for index, entry in enumerate(entries):
            card = _EntryCard(
                entry, index, condition_names, self._on_entry_changed,
                self._on_entry_pdk_selected, self._on_remove_entry,
            )
            # 카드를 만든 직후에는 PDK/DBS 콤보가 비어 있으므로, 저장돼 있던 선택값을
            # 살려서 채워 넣는다.
            self._refresh_entry_files(card, entry.get(ENTRY_PDK_KEY, ""), entry.get(ENTRY_DBS_KEY, ""))
            self.entries_layout.insertWidget(self.entries_layout.count() - 1, card)
            self.entry_cards.append(card)

        self._refresh_entries_summary()

    def _refresh_entries_summary(self) -> None:
        count = len(self.entry_cards)
        self.entries_summary_label.setText(f"{count} liberty file(s) to generate")
        self.entries_empty_label.setVisible(count == 0)
        for index, card in enumerate(self.entry_cards):
            card.set_index(index)

    def _refresh_entry_files(
        self, card: _EntryCard, keep_pdk: str = "", keep_dbs: str = "",
    ) -> None:
        """
        카드의 현재 입력값으로 PDK/DBS 드롭다운을 다시 채운다. keep_* 가 주어지면 그
        선택을 유지하고, 아니면 카드에 지금 선택돼 있는 값을 유지한다.
        """
        entry = card.collect()
        current_pdk = keep_pdk or entry.get(ENTRY_PDK_KEY, "")
        current_dbs = keep_dbs or entry.get(ENTRY_DBS_KEY, "")

        pdk_recommended = recommend_pdk_files(self.pdk_files, entry)
        dbs_recommended = recommend_dbs_files(self.dbs_files, entry)

        _populate_file_combo(card.pdk_combo, self.pdk_files, pdk_recommended, current_pdk)
        _populate_file_combo(card.dbs_combo, self.dbs_files, dbs_recommended, current_dbs)

        self._update_match_status(card, entry, pdk_recommended, dbs_recommended)

    def _update_match_status(
        self,
        card: _EntryCard,
        entry: dict,
        pdk_recommended: list[tuple[str, int]],
        dbs_recommended: list[tuple[str, int]],
    ) -> None:
        corner = entry.get(ENTRY_CORNER_KEY, "")
        voltage_token = format_voltage_token(entry.get(ENTRY_VOLTAGE_KEY, ""))
        temperature_token = format_temperature_token(entry.get(ENTRY_TEMPERATURE_KEY, ""))

        if not corner or not voltage_token or not temperature_token:
            card.set_match_status(
                "Fill in Corner, Voltage and Temperature to search for matching files."
            )
            return

        looking_for = f"Looking for *_{corner}_*_{voltage_token}_{temperature_token}*"
        if not pdk_recommended:
            card.set_match_status(
                f"{looking_for} - no PDK file matched; pick one from the full list manually.",
                "error",
            )
            return

        message = (
            f"{looking_for} - {len(pdk_recommended)} PDK candidate(s), "
            f"{len(dbs_recommended)} DBS candidate(s)."
        )
        status = "success" if dbs_recommended else "error"
        if not dbs_recommended:
            message += " No DBS output file matched; pick one manually."
        card.set_match_status(message, status)

    # ------------------------------------------------------------------
    # 카드 이벤트
    # ------------------------------------------------------------------
    def _on_add_entry(self) -> None:
        entries = self._collect_entries()
        entries.append(new_entry())
        self._rebuild_entry_cards(entries)

    def _on_remove_entry(self, card: _EntryCard) -> None:
        entries = [e for e in self._collect_entries() if e.get(ENTRY_ID_KEY) != card.entry_id]
        self._rebuild_entry_cards(entries)

    def _on_entry_changed(self, card: _EntryCard) -> None:
        """corner/beol/voltage/temperature/condition이 바뀌면 추천을 다시 계산한다."""
        self._refresh_entry_files(card)
        self._auto_map_dbs(card)

    def _on_entry_pdk_selected(self, card: _EntryCard) -> None:
        """PDK를 고르면 그 옆의 DBS output 파일을 자동으로 엮어준다."""
        self._auto_map_dbs(card)

    def _auto_map_dbs(self, card: _EntryCard) -> None:
        """
        DBS output 파일 자동 매핑. 이미 사용자가 고른 값이 지금 조건에도 유효하면 그대로
        두고, 비어 있거나 더 이상 후보가 아니게 된 경우에만 자동 선택을 시도한다.
        후보가 하나로 좁혀지지 않으면 비워 두고 사용자가 직접 고르게 한다.
        """
        entry = card.collect()
        if not entry.get(ENTRY_PDK_KEY):
            return

        candidates = [name for name, _rank in recommend_dbs_files(self.dbs_files, entry)]
        current = entry.get(ENTRY_DBS_KEY, "")
        if current and current in candidates:
            return

        auto = auto_select_dbs_file(self.dbs_files, entry)
        if not auto:
            return
        index = card.dbs_combo.findData(auto)
        if index >= 0:
            card.dbs_combo.setCurrentIndex(index)

    # ------------------------------------------------------------------
    # 값 수집 (화면 -> 상태)
    # ------------------------------------------------------------------
    def _collect_entries(self) -> list[dict]:
        return [card.collect() for card in self.entry_cards]

    def _commit_current_ui(self) -> None:
        common = self.state["common"]
        for key, widget in self.common_widgets.items():
            if isinstance(widget, NoWheelComboBox):
                common[key] = widget.currentText().strip()
            else:
                common[key] = widget.text().strip()
        self.state[udc_manager.LIBERTY_SETTINGS_KEY] = self._collect_entries()

    def _persist(self) -> None:
        self._commit_current_ui()
        udc_manager.save_state(self.state)
        # Voltage Map은 step3_settings.json 안에 있으므로 그 부분만 갈아끼운다
        # (Step3에서 입력한 다른 값은 건드리지 않음).
        self.voltage_map = self.voltage_map_panel.collect()
        settings_manager.save_voltage_map(self.voltage_map)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    def _on_validate(self) -> None:
        self._rescan_files()
        self._persist()

        entries = udc_manager.get_entries(self.state)
        errors = validate_common_fields(self.state["common"])
        # Voltage Map이 먼저다 - liberty setting의 Condition이 여기 정의된 이름이어야
        # 하므로, Voltage Map 자체가 성립하는지부터 검사한다.
        errors += validate_voltage_map(self.voltage_map)
        errors += validate_entries(
            entries, self.pdk_files, self.dbs_files, self.voltage_map_panel.condition_names(),
        )

        summary = (
            f"{len(entries)} liberty file(s) configured, "
            f"{len(self.voltage_map_panel.condition_names())} voltage condition(s)"
        )
        if errors:
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText(summary + "\n" + "\n".join(f"• {e}" for e in errors))
            self._lock_next()
        else:
            self.result_label.setStyleSheet(f"color: {SUCCESS_COLOR};")
            self.result_label.setText(
                summary + "\nThe voltage map and all liberty settings passed validation."
            )
            self.next_btn.setEnabled(True)
            self.next_btn.setToolTip("")

    def _on_next_clicked(self) -> None:
        self._persist()
        if self.on_next:
            self.on_next()

    # ------------------------------------------------------------------
    # Config export (2026-08 추가)
    # ------------------------------------------------------------------
    def _on_export_config(self) -> None:
        self._persist()
        run_export_config_dialog(self, self.get_pdk_folder())

    # ------------------------------------------------------------------
    # 화면이 다시 보일 때마다 (Step 1에서 돌아왔을 때 등) 최신 파일 목록 반영
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._apply_default_column_sizes()
        self._commit_current_ui()
        self._rescan_files()
        # PDK/DBS 폴더가 바뀌었을 수 있으므로 추천 목록을 전부 다시 계산한다.
        for card in self.entry_cards:
            self._refresh_entry_files(card)
        # Step1/Step3에서 돌아온 경우 입력이 달라졌을 수 있으므로 검사 결과를 무효화
        # 한다 - Next는 다시 Validate를 통과해야만 열린다 (2026-08 확정).
        self._lock_next()

    def _lock_next(self) -> None:
        self.next_btn.setEnabled(False)
        self.next_btn.setToolTip("Run Validate first.")

    def _apply_default_column_sizes(self) -> None:
        """
        왼쪽(Common+Voltage Map) : 오른쪽(Liberty Settings) 기본 폭 비율을 3:5로
        맞춘다. 위젯이 실제로 표시되어 진짜 폭을 알 수 있게 된 첫 showEvent에서 딱
        한 번만 적용하고, 그 뒤로는 사용자가 직접 드래그해서 조절한 폭을 그대로
        존중한다(다시 덮어쓰지 않음).
        """
        if self._column_sizes_applied:
            return
        width = self.column_splitter.width()
        if width <= 0:
            return
        left_width = width * 3 // 8
        self.column_splitter.setSizes([left_width, width - left_width])
        self._column_sizes_applied = True
