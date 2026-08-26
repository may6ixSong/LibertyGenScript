"""
udc_view.py

'UDC Settings' 화면 (Step 2, 2026-08 전면 재설계 -> 2026-08 2차 재설계).

  - 위쪽 "Common Fields" 카드에 이번에 생성할 모든 조합이 공유하는 값을 한 번만 입력.
  - 아래쪽 "Liberty Settings" 카드에서 **liberty 파일 1개당 setting 1개**를 직접 추가한다.
    각 setting은 corner / beol inform / voltage / temperature / condition 을 입력받고,
    그 값들로 PDK 폴더에서 맞을 것 같은 파일을 자동으로 찾아 드롭다운 맨 위에 추천으로
    올려 준다. PDK를 고르면 같은 corner/voltage/temperature를 가진 DBS output 파일이
    자동으로 엮이고, 자동으로 못 고르면 사용자가 직접 선택한다.

PDK 파일명의 beol inform 토큰은 사용자가 고른 beol inform과 다를 확률이 크기 때문에
(2026-08 확인), 추천의 필수 조건은 corner + voltage + temperature 세 가지이고 beol은
순위 가산점으로만 쓴다 (udc_field_defs.match_pdk_file 참고).

Validate 버튼을 누르면 PDK/DBS 폴더를 다시 스캔해서, 공통 필드와 모든 setting이 빈 값
없이 채워졌는지 + 고른 파일들이 실제로 존재하는지를 검사한다.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QRegExp, Qt
from PyQt5.QtGui import QBrush, QColor, QFont, QRegExpValidator
from PyQt5.QtWidgets import (
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
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
from ui.theme import (
    ERROR_COLOR, MUTED_TEXT_COLOR, RECOMMEND_BG, RECOMMEND_TEXT, SUCCESS_COLOR, TEXT_COLOR,
)
from ui.ui_common import (
    NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row,
    build_hint, build_section_header,
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
        "Selects which group (BST / WST / TIV) of Step 3's Voltage Map supplies this "
        "liberty's voltage_map values."
    ),
}


def _apply_number_validator(edit: QLineEdit) -> None:
    edit.setValidator(QRegExpValidator(_NUMBER_REGEX, edit))


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
        remove_btn.clicked.connect(lambda: self._on_remove(self))
        row.addWidget(remove_btn)
        return row

    def _build_setting_row(self, entry: dict) -> QGridLayout:
        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)

        for column, (key, label, kind, extra) in enumerate(ENTRY_FIELD_DEFS):
            caption = QLabel(label)
            caption.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
            caption.setToolTip(_ENTRY_FIELD_INFO.get(key, ""))
            grid.addWidget(caption, 0, column)

            if kind == "select":
                combo = NoWheelComboBox()
                combo.addItem(_SELECT_LABEL, "")
                for option in extra:
                    combo.addItem(option, option)
                saved = str(entry.get(key, ""))
                found = combo.findData(saved) if saved else 0
                combo.setCurrentIndex(found if found >= 0 else 0)
                combo.setToolTip(_ENTRY_FIELD_INFO.get(key, ""))
                combo.currentIndexChanged.connect(lambda _i: self._on_changed(self))
                self.select_widgets[key] = combo
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
            "Enter the common fields once, then add one setting per liberty file you want "
            "to generate."
        )
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        outer.addWidget(self._build_common_card())
        outer.addWidget(self._build_entries_card(), stretch=1)

        self.validate_btn = QPushButton("Validate")
        self.validate_btn.setObjectName("primaryButton")
        self.validate_btn.clicked.connect(self._on_validate)

        self.next_btn = QPushButton("Next")
        self.next_btn.setObjectName("primaryButton")
        self.next_btn.setEnabled(False)
        self.next_btn.clicked.connect(self._on_next_clicked)

        self.back_btn = build_back_button(self.on_back)
        outer.addLayout(build_bottom_button_row(self.back_btn, self.validate_btn, self.next_btn))

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        outer.addWidget(self.result_label)

    def _build_common_card(self) -> QFrame:
        """
        공통 필드 8개를 세로로 길게 늘어놓지 않고 4열 그리드로 배치한다 - 아래쪽
        Liberty Settings 목록이 화면에서 차지할 세로 공간을 확보하기 위해서
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
        columns = 4
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

        for index, entry in enumerate(entries):
            card = _EntryCard(
                entry, index, self._on_entry_changed, self._on_entry_pdk_selected,
                self._on_remove_entry,
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

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    def _on_validate(self) -> None:
        self._rescan_files()
        self._persist()

        entries = udc_manager.get_entries(self.state)
        errors = validate_common_fields(self.state["common"])
        errors += validate_entries(entries, self.pdk_files, self.dbs_files)

        summary = f"{len(entries)} liberty file(s) configured"
        if errors:
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText(summary + "\n" + "\n".join(f"• {e}" for e in errors))
            self.next_btn.setEnabled(False)
        else:
            self.result_label.setStyleSheet(f"color: {SUCCESS_COLOR};")
            self.result_label.setText(summary + "\nAll liberty settings passed validation.")
            self.next_btn.setEnabled(True)

    def _on_next_clicked(self) -> None:
        self._persist()
        if self.on_next:
            self.on_next()

    # ------------------------------------------------------------------
    # 화면이 다시 보일 때마다 (Step 1에서 돌아왔을 때 등) 최신 파일 목록 반영
    # ------------------------------------------------------------------
    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._commit_current_ui()
        self._rescan_files()
        # PDK/DBS 폴더가 바뀌었을 수 있으므로 추천 목록을 전부 다시 계산한다.
        for card in self.entry_cards:
            self._refresh_entry_files(card)
