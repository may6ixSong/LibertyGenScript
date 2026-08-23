"""
udc_view.py

'UDC Settings' 화면 (Step 2, 2026-08 전면 재설계).

더 이상 UDC 항목을 하나하나 수동으로 만들지 않는다:
  - 위쪽 "Common Fields" 카드에 이번에 생성할 모든 조합이 공유하는 값을 한 번만 입력.
  - 아래쪽 "Auto-Paired Files" 카드는 PDK Folder(.lib/.lib_css_tn)와 DBS Simulation
    Folder(.mt0)에서 파일명이 voltage+temperature 기준으로 자동으로 짝지어진 pair
    목록(=liberty 1개 생성 대상)을 보여준다. 각 pair마다 Voltage Condition(bst/wst/tiv)
    을 자유롭게 선택한다.
  - 1:1이 안 되는 파일은 별도 warning 배너에 표시되고 생성 대상에서 제외된다.

Validate 버튼을 누르면 PDK/DBS 폴더를 다시 스캔해 pair를 재계산하고, 공통 필드 +
Voltage Condition 선택값을 검사한다.
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import QRegExp, Qt
from PyQt5.QtGui import QRegExpValidator
from PyQt5.QtWidgets import (
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)

from step1_setup.file_scanner import list_dbs_mt0_files, list_pdk_lib_files
from step2_udc import udc_manager
from step2_udc.udc_field_defs import (
    COMMON_FIELD_DEFS, TIMING_STATE_OPTIONS, VOLTAGE_CONDITION_OPTIONS, compute_pairs,
)
from step2_udc.udc_validator import validate_common_fields, validate_pairs
from ui.theme import BORDER_COLOR, ERROR_COLOR, MUTED_TEXT_COLOR, SUCCESS_COLOR
from ui.ui_common import NoWheelComboBox, add_shadow, build_back_button, build_bottom_button_row

_NUMBER_REGEX = QRegExp(r"^-?\d*\.?\d*$")
_SELECT_LABEL = "(Select)"


def _apply_number_validator(edit: QLineEdit) -> None:
    edit.setValidator(QRegExpValidator(_NUMBER_REGEX, edit))


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
            get_dbs_folder: 최신 DBS Simulation Folder 경로를 즉시 조회하는 콜백 (Step 1 값 재사용)
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
        self._condition_combos: dict[str, NoWheelComboBox] = {}
        self.current_pairs: list[dict] = []
        self.current_unmatched_pdk: list[tuple[str, str]] = []
        self.current_unmatched_dbs: list[tuple[str, str]] = []

        self._build_layout()
        self._rescan_and_render()

    # ------------------------------------------------------------------
    # 레이아웃
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 24, 24, 24)
        outer.setSpacing(16)

        title = QLabel("UDC Settings")
        title.setObjectName("titleLabel")
        subtitle = QLabel(
            "Enter the common fields once, then choose a Voltage Condition for each "
            "automatically paired PDK/DK <-> DBS output file."
        )
        subtitle.setObjectName("subtitleLabel")
        outer.addWidget(title)
        outer.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setSpacing(16)
        content_layout.addWidget(self._build_common_card())
        content_layout.addWidget(self._build_pairs_card())
        content_layout.addWidget(self._build_unmatched_banner())
        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll, stretch=1)

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
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("Common Fields")
        title.setObjectName("sectionLabel")
        layout.addWidget(title)

        hint = QLabel("Shared by every UDC/liberty combination generated in this run.")
        hint.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(hint)

        form = QFormLayout()
        form.setSpacing(8)
        common = self.state["common"]
        for key, label, kind in COMMON_FIELD_DEFS:
            if kind == "dropdown":
                combo = NoWheelComboBox()
                combo.addItems(TIMING_STATE_OPTIONS)
                current = common.get(key, "")
                if current:
                    idx = combo.findText(current)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                self.common_widgets[key] = combo
                form.addRow(label, combo)
            else:
                edit = QLineEdit(str(common.get(key, "")))
                if kind == "number":
                    _apply_number_validator(edit)
                self.common_widgets[key] = edit
                form.addRow(label, edit)
        layout.addLayout(form)
        return card

    def _build_pairs_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("Auto-Paired Files")
        title.setObjectName("sectionLabel")
        header.addWidget(title)
        header.addStretch()
        self.pairs_summary_label = QLabel("")
        self.pairs_summary_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        header.addWidget(self.pairs_summary_label)
        layout.addLayout(header)

        hint = QLabel(
            "One liberty file will be generated per pair below. Voltage/Temperature are "
            "parsed from the filenames; choose a Voltage Condition for each pair to select "
            "which row of Step 3's Voltage Condition table supplies its voltage_map values."
        )
        hint.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.pairs_list_container = QWidget()
        self.pairs_list_layout = QVBoxLayout(self.pairs_list_container)
        self.pairs_list_layout.setContentsMargins(0, 0, 0, 0)
        self.pairs_list_layout.setSpacing(8)
        layout.addWidget(self.pairs_list_container)

        self.pairs_empty_label = QLabel(
            "No valid pairs found yet. Click Validate after checking the PDK Folder / "
            "DBS Simulation Folder set in Step 1."
        )
        self.pairs_empty_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px;")
        self.pairs_empty_label.setWordWrap(True)
        layout.addWidget(self.pairs_empty_label)

        return card

    def _build_pair_row(self, pair: dict, current_condition: str) -> QFrame:
        row = QFrame()
        row.setObjectName("pairRow")
        row.setStyleSheet(
            f"QFrame#pairRow {{ background-color: #FAFBFF; border: 1px solid {BORDER_COLOR}; "
            f"border-radius: 8px; }}"
        )
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(12, 10, 12, 10)
        row_layout.setSpacing(12)

        info_label = QLabel(
            f"<b>{pair['pdk_file']}</b><br>"
            f"<span style='color:{MUTED_TEXT_COLOR}; font-size:11px;'>"
            f"\u2194 {pair['dbs_file']} &nbsp;\u00b7&nbsp; "
            f"{pair['voltage']:.3f} V \u00b7 {pair['temperature']}\u00b0C</span>"
        )
        info_label.setTextFormat(Qt.RichText)
        info_label.setWordWrap(True)
        row_layout.addWidget(info_label, stretch=1)

        combo = NoWheelComboBox()
        combo.addItem(_SELECT_LABEL, "")
        for option in VOLTAGE_CONDITION_OPTIONS:
            combo.addItem(option, option)
        idx = combo.findData(current_condition) if current_condition else 0
        combo.setCurrentIndex(idx if idx >= 0 else 0)
        combo.setFixedWidth(140)
        row_layout.addWidget(combo)

        self._condition_combos[pair["pdk_file"]] = combo
        return row

    def _build_unmatched_banner(self) -> QFrame:
        note = QFrame()
        note.setObjectName("noteBanner")
        layout = QVBoxLayout(note)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(4)
        header = QLabel("Excluded files (no 1:1 match)")
        header.setObjectName("noteLabel")
        header.setStyleSheet("font-weight: 600;")
        layout.addWidget(header)
        self.unmatched_label = QLabel("")
        self.unmatched_label.setObjectName("noteLabel")
        self.unmatched_label.setWordWrap(True)
        layout.addWidget(self.unmatched_label)
        self.unmatched_banner = note
        note.hide()
        return note

    # ------------------------------------------------------------------
    # Pair 재계산 / 화면 갱신
    # ------------------------------------------------------------------
    def _rescan_and_render(self) -> None:
        pdk_files = list_pdk_lib_files(self.get_pdk_folder())
        dbs_files = list_dbs_mt0_files(self.get_dbs_folder())
        result = compute_pairs(pdk_files, dbs_files)
        self.current_pairs = result["pairs"]
        self.current_unmatched_pdk = result["unmatched_pdk"]
        self.current_unmatched_dbs = result["unmatched_dbs"]

        self._refresh_pairs_list()
        self._refresh_unmatched_banner()

    def _refresh_pairs_list(self) -> None:
        while self.pairs_list_layout.count():
            item = self.pairs_list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        pair_settings = self.state["pair_settings"]
        self._condition_combos = {}

        for pair in self.current_pairs:
            current = pair_settings.get(pair["pdk_file"], {}).get("voltage_condition", "")
            row = self._build_pair_row(pair, current)
            self.pairs_list_layout.addWidget(row)

        self.pairs_empty_label.setVisible(len(self.current_pairs) == 0)
        self.pairs_summary_label.setText(f"{len(self.current_pairs)} pair(s) ready")

    def _refresh_unmatched_banner(self) -> None:
        total_excluded = len(self.current_unmatched_pdk) + len(self.current_unmatched_dbs)
        if total_excluded == 0:
            self.unmatched_banner.hide()
            return

        lines = [
            f"\u2022 {filename} (PDK/DK) \u2014 {reason}"
            for filename, reason in self.current_unmatched_pdk
        ]
        lines += [
            f"\u2022 {filename} (DBS) \u2014 {reason}"
            for filename, reason in self.current_unmatched_dbs
        ]
        self.unmatched_label.setText("\n".join(lines))
        self.unmatched_banner.show()

    # ------------------------------------------------------------------
    # 값 수집 (화면 -> 상태)
    # ------------------------------------------------------------------
    def _commit_current_ui(self) -> None:
        common = self.state["common"]
        for key, widget in self.common_widgets.items():
            if isinstance(widget, NoWheelComboBox):
                common[key] = widget.currentText().strip()
            else:
                common[key] = widget.text().strip()

        pair_settings = self.state["pair_settings"]
        for pdk_file, combo in self._condition_combos.items():
            value = combo.currentData() or ""
            pair_settings.setdefault(pdk_file, {})["voltage_condition"] = value

    def _persist(self) -> None:
        self._commit_current_ui()
        udc_manager.save_state(self.state)

    # ------------------------------------------------------------------
    # Validate
    # ------------------------------------------------------------------
    def _on_validate(self) -> None:
        self._persist()
        self._rescan_and_render()

        errors: list[str] = []
        errors += validate_common_fields(self.state["common"])
        errors += validate_pairs(self.current_pairs, self.state["pair_settings"])

        excluded_count = len(self.current_unmatched_pdk) + len(self.current_unmatched_dbs)
        summary = f"{len(self.current_pairs)} pairs ready / {excluded_count} files excluded (unmatched)"

        if errors:
            self.result_label.setStyleSheet(f"color: {ERROR_COLOR};")
            self.result_label.setText(summary + "\n" + "\n".join(f"\u2022 {e}" for e in errors))
            self.next_btn.setEnabled(False)
        else:
            self.result_label.setStyleSheet(f"color: {SUCCESS_COLOR};")
            self.result_label.setText(summary + "\nAll pairs passed validation.")
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
        self._rescan_and_render()
