"""
serial_set_editor.py

Step 3 - Serial Cluster "More than 1"(Split Serial)에서 인식된 DBS output pin 하나에
대한 입력 위젯 (2026-10 "Bit Set" 재설계).

    Related Pin (wildcard)  [RD_EN_*                         ]
                            ✓ 16 pins matched: RD_EN_0[13:0], RD_EN_1[13:0], ... RD_EN_15[13:0]
    Bit sets (LSB → MSB)
       #   Number of Col   Related Pin              DBS output pin bits
       1   [  672 ]        [RD_EN_15[13:0]   v]  →  OUT_ADC[671:0]          [✕]
       2   [ 1056 ]        [RD_EN_14[13:0]   v]  →  OUT_ADC[1727:672]       [✕]
       ...
       [+ Add set]  [Clear all]       ███████████████░░  15456 / 16480 bits · 1024 left

1) 사용자가 Related Pin 와일드카드를 입력하면, 시스템이 Port==PORT pin 중 매치되는
   pin 목록을 읽어온다('*'는 숫자만 - pin_field_defs.match_digit_wildcard).
2) set를 순서대로 추가한다 - set 하나 = Number of Col + 매치 목록 중 고른 Related Pin.
   set의 DBS output pin 범위(start~end bit)는 LSB부터 누적해서 시스템이 자동으로
   보여준다(pin_field_defs.compute_serial_set_ranges - Validate/block5와 같은 계산).
3) 누적 비트가 DBS output pin의 최대 bit를 넘는 set는 그 자리에서 바로 빨간 에러로
   표시하고, 아래 진행 막대/문구로 몇 비트가 남았는지(또는 넘었는지) 보여준다.

새 set를 추가할 때는 직전 set의 Number of Col을 기본값으로 쓰되 남은 비트보다 크면
남은 비트로 줄여 주고(예: 마지막 1024), Related Pin은 직전 두 set의 선택 방향(예:
RD_EN_15 → RD_EN_14 이면 내림차순)을 이어서 아직 안 쓴 다음 pin을 골라 둔다. 마지막
set의 Number of Col 칸에서 Enter를 누르면 비트가 남아 있을 때 다음 set가 추가된다.
"""

from __future__ import annotations

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from step3_settings.pin_field_defs import (
    SERIAL_SET_COLS_KEY, SERIAL_SET_RELATED_KEY, compute_serial_set_ranges,
    match_digit_wildcard, normalize_serial_sets,
)
from ui.theme import (
    BORDER_COLOR, ERROR_COLOR, MUTED_TEXT_COLOR, PRIMARY_COLOR, SUCCESS_COLOR, TEXT_COLOR,
    WARNING_TEXT,
)
from ui.ui_common import NoWheelComboBox, build_label_with_info

_REMOVE_SYMBOL = "✕"
_SELECT_TEXT = "(Select)"
_HEADER_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 11px; font-weight: 600;"
_INDEX_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 12px; font-weight: 600;"
_RANGE_OK_STYLE = f"color: {TEXT_COLOR}; font-size: 12px; font-family: monospace;"
_RANGE_PENDING_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 12px;"
_RANGE_ERROR_STYLE = f"color: {ERROR_COLOR}; font-size: 11px;"
_ARROW_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 13px;"
_MATCH_PREVIEW_COUNT = 3

_WILDCARD_INFO = (
    "Wildcard matched against Port==PORT pin names (e.g. 'RD_EN_*') - '*' matches digits "
    "only (a name where '*' would match letters is ignored). A trailing '[13:0]' is "
    "display-only and not used for matching. The matched pins become the choices for "
    "each set's Related Pin below. Independent per DBS output pin."
)
_SETS_INFO = (
    "Each set takes 'Number of Col' bits of this DBS output pin, starting from its LSB, "
    "in the order listed - the resulting bit range is filled in automatically. Each set "
    "becomes one pin() in block5, with the chosen Related Pin as its related_bus_pins. "
    "Sets may use different Number of Col values (e.g. 672, then 1056 x14, then 1024).\n\n"
    "A set that goes past this pin's max bit is shown as an error right away. All sets "
    "together must cover exactly this pin's Bits, and a Related Pin can be used only once."
)


class SerialSetEditor(QWidget):
    """인식된 DBS output pin 하나의 Split Serial 입력(와일드카드 + bit set 목록)."""

    changed = pyqtSignal()

    def __init__(
        self, pin_name: str, base_name: str, dbs_bits: int | None, dbs_lsb: int,
        candidate_pin_names: list[str], pattern: str = "", sets: list[dict] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("transparentRow")
        self._pin_name = pin_name
        self._base_name = base_name
        self._dbs_bits = dbs_bits
        self._dbs_lsb = dbs_lsb
        self._candidates_all = list(candidate_pin_names)
        self._matched: list[str] = []
        self._sets: list[dict] = normalize_serial_sets(sets or [])
        self._rows: list[dict] = []

        self._build()
        # 초기값은 시그널 없이 넣고 한 번만 계산한다(행을 두 번 만들지 않도록).
        self.pattern_edit.blockSignals(True)
        self.pattern_edit.setText(pattern)
        self.pattern_edit.blockSignals(False)
        self._on_pattern_changed()

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
    @property
    def can_split(self) -> bool:
        return self._dbs_bits is not None and self._dbs_bits > 1

    def pattern(self) -> str:
        return self.pattern_edit.text().strip()

    def sets(self) -> list[dict]:
        return [dict(item) for item in self._sets]

    def required_widgets(self) -> list[QWidget]:
        """Validate 때 비어 있으면 "Must fill"/"Must select"로 표시할 칸들."""
        if not self.can_split:
            return []
        widgets: list[QWidget] = [self.pattern_edit]
        for row in self._rows:
            widgets += [row["cols_edit"], row["combo"]]
        return widgets

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------
    def _build(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        pattern_row = QHBoxLayout()
        pattern_row.setSpacing(10)
        pattern_row.addWidget(build_label_with_info("Related Pin (wildcard)", _WILDCARD_INFO))
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("e.g. RD_EN_*")
        self.pattern_edit.setEnabled(self.can_split)
        self.pattern_edit.textChanged.connect(lambda _t: self._on_pattern_changed())
        pattern_row.addWidget(self.pattern_edit, stretch=1)
        layout.addLayout(pattern_row)

        self.match_label = QLabel("")
        self.match_label.setWordWrap(True)
        self.match_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.match_label)

        self.sets_header = build_label_with_info("Bit sets (LSB → MSB)", _SETS_INFO)
        layout.addWidget(self.sets_header)

        self.grid_host = QWidget()
        self.grid_host.setObjectName("transparentRow")
        self.grid = QGridLayout(self.grid_host)
        self.grid.setContentsMargins(0, 0, 0, 0)
        self.grid.setHorizontalSpacing(8)
        self.grid.setVerticalSpacing(4)
        self.grid.setColumnStretch(2, 2)
        self.grid.setColumnStretch(4, 3)
        layout.addWidget(self.grid_host)

        self.empty_label = QLabel("No sets yet - click '+ Add set' to map the first bits (from the LSB).")
        self.empty_label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px;")
        layout.addWidget(self.empty_label)

        footer = QHBoxLayout()
        footer.setSpacing(8)
        self.add_btn = QPushButton("+ Add set")
        self.add_btn.setStyleSheet(
            f"QPushButton {{ color: {PRIMARY_COLOR}; font-weight: 600; padding: 5px 14px; }}"
        )
        self.add_btn.clicked.connect(self._on_add_set)
        footer.addWidget(self.add_btn)
        self.clear_btn = QPushButton("Clear all")
        self.clear_btn.setStyleSheet("QPushButton { padding: 5px 14px; }")
        self.clear_btn.clicked.connect(self._on_clear_sets)
        footer.addWidget(self.clear_btn)
        footer.addSpacing(8)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setMinimumWidth(120)
        footer.addWidget(self.progress, stretch=1)
        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet("font-size: 11px;")
        footer.addWidget(self.summary_label)
        layout.addLayout(footer)

        if not self.can_split:
            for widget in (self.sets_header, self.grid_host, self.empty_label, self.add_btn,
                           self.clear_btn, self.progress, self.summary_label):
                widget.setVisible(False)

    # ------------------------------------------------------------------
    # wildcard
    # ------------------------------------------------------------------
    def _on_pattern_changed(self) -> None:
        if not self.can_split:
            self._set_match_text(
                "1 bit - written as a single pin()." if self._dbs_bits == 1
                else "DBS output pin Bits is unknown.",
                MUTED_TEXT_COLOR if self._dbs_bits == 1 else ERROR_COLOR,
            )
            return

        pattern = self.pattern()
        if not pattern:
            self._matched = []
            self._set_match_text("Enter a wildcard to list the Related Pin candidates.", MUTED_TEXT_COLOR)
        else:
            self._matched = [name for _v, name in match_digit_wildcard(pattern, self._candidates_all)]
            if not self._matched:
                self._set_match_text(f"'{pattern}' matched no PORT pins ('*' matches digits only).", ERROR_COLOR)
            else:
                names = self._matched
                if len(names) > _MATCH_PREVIEW_COUNT + 1:
                    preview = ", ".join(names[:_MATCH_PREVIEW_COUNT]) + ", … , " + names[-1]
                else:
                    preview = ", ".join(names)
                self._set_match_text(f"✓ {len(names)} pin(s) matched: {preview}", SUCCESS_COLOR)
                self.match_label.setToolTip("\n".join(names))

        self._rebuild_rows()
        self.changed.emit()

    def _set_match_text(self, text: str, color: str) -> None:
        self.match_label.setStyleSheet(f"color: {color}; font-size: 11px;")
        self.match_label.setText(text)
        self.match_label.setToolTip("")

    # ------------------------------------------------------------------
    # rows
    # ------------------------------------------------------------------
    def _clear_grid(self) -> None:
        while self.grid.count():
            item = self.grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # deleteLater만 하면 이벤트 루프가 돌기 전까지 옛 행이 새 행 위에 겹쳐
                # 그려질 수 있으므로, 먼저 숨기고 부모에서 떼어낸다.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self._rows = []

    def _rebuild_rows(self) -> None:
        """set 개수/후보 목록이 바뀔 때만 행 위젯을 다시 만든다(값 변경은 _refresh)."""
        if not self.can_split:
            return
        self._clear_grid()

        if self._sets:
            for col, text in enumerate(("#", "Number of Col", "Related Pin", "", "DBS output pin bits")):
                header = QLabel(text)
                header.setStyleSheet(_HEADER_STYLE)
                self.grid.addWidget(header, 0, col)

        for index, item in enumerate(self._sets):
            grid_row = index + 1
            index_label = QLabel(str(index + 1))
            index_label.setStyleSheet(_INDEX_STYLE)
            index_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            index_label.setMinimumWidth(18)

            cols_edit = QLineEdit(item[SERIAL_SET_COLS_KEY])
            cols_edit.setPlaceholderText("cols")
            cols_edit.setFixedWidth(90)
            cols_edit.setAlignment(Qt.AlignRight)
            cols_edit.textChanged.connect(lambda text, i=index: self._on_cols_changed(i, text))
            cols_edit.returnPressed.connect(lambda i=index: self._on_cols_return(i))

            combo = NoWheelComboBox()
            combo.setMinimumWidth(170)
            combo.addItem(_SELECT_TEXT, "")
            for name in self._matched:
                combo.addItem(name, name)
            current = item[SERIAL_SET_RELATED_KEY]
            if current and current not in self._matched:
                combo.addItem(f"{current}  (not matched)", current)
            combo.setCurrentIndex(max(0, combo.findData(current)) if current else 0)
            combo.currentIndexChanged.connect(lambda _i, i=index, c=combo: self._on_related_changed(i, c))

            arrow = QLabel("→")
            arrow.setStyleSheet(_ARROW_STYLE)

            range_label = QLabel("")
            range_label.setWordWrap(True)
            range_label.setTextInteractionFlags(Qt.TextSelectableByMouse)

            remove_btn = QPushButton(_REMOVE_SYMBOL)
            remove_btn.setObjectName("iconDangerButton")
            remove_btn.setFixedSize(26, 26)
            remove_btn.setToolTip(f"Remove set #{index + 1}")
            remove_btn.clicked.connect(lambda _c=False, i=index: self._on_remove_set(i))

            self.grid.addWidget(index_label, grid_row, 0)
            self.grid.addWidget(cols_edit, grid_row, 1)
            self.grid.addWidget(combo, grid_row, 2)
            self.grid.addWidget(arrow, grid_row, 3)
            self.grid.addWidget(range_label, grid_row, 4)
            self.grid.addWidget(remove_btn, grid_row, 5)
            self._rows.append({"cols_edit": cols_edit, "combo": combo, "range_label": range_label})

        self._refresh()

    def _refresh(self) -> None:
        """현재 set 값으로 범위/에러/진행 막대/콤보 표시만 다시 계산한다(위젯은 그대로)."""
        if not self.can_split:
            return
        computed = compute_serial_set_ranges(
            self._base_name, self._dbs_bits, self._dbs_lsb, self._sets,
            self._matched if self.pattern() else None,
        )

        used_by: dict[str, int] = {}
        for index, row in enumerate(computed["rows"], start=1):
            if row["related"] and row["related"] not in used_by:
                used_by[row["related"]] = index

        for index, (widgets, row) in enumerate(zip(self._rows, computed["rows"]), start=1):
            label = widgets["range_label"]
            if row["error"] and row["label"] is None and row["cols"] is not None:
                label.setStyleSheet(_RANGE_ERROR_STYLE)
                label.setText(f"✕ {row['error']}")
            elif row["label"] is None:
                label.setStyleSheet(_RANGE_PENDING_STYLE)
                label.setText("–")
            elif row["error"] and row["related"]:
                label.setStyleSheet(_RANGE_ERROR_STYLE)
                label.setText(f"{row['label']}   ✕ {row['error']}")
            else:
                label.setStyleSheet(_RANGE_OK_STYLE)
                label.setText(row["label"])

            # 다른 set에서 이미 쓴 pin은 콤보 목록에 "· set #k"로 표시한다.
            combo = widgets["combo"]
            combo.blockSignals(True)
            for item_index in range(1, combo.count()):
                name = combo.itemData(item_index)
                if name not in self._matched:
                    continue
                owner = used_by.get(name)
                suffix = f"   · set #{owner}" if owner is not None and owner != index else ""
                combo.setItemText(item_index, f"{name}{suffix}")
            combo.blockSignals(False)

        total = self._dbs_bits
        used = computed["used_bits"]
        self.progress.setMaximum(total)
        self.progress.setValue(min(used, total))
        if computed["overflow_bits"]:
            color = ERROR_COLOR
            text = f"{used} / {total} bits · exceeds max bit {computed['max_bit']} by {computed['overflow_bits']}"
        elif used == total:
            color = SUCCESS_COLOR
            text = f"✓ {used} / {total} bits mapped"
        else:
            color = WARNING_TEXT
            text = f"{used} / {total} bits · {total - used} left"
        self.summary_label.setStyleSheet(f"color: {color}; font-size: 11px; font-weight: 600;")
        self.summary_label.setText(text)
        self.progress.setStyleSheet(
            f"QProgressBar {{ border: none; border-radius: 4px; background: {BORDER_COLOR}; }}"
            f"QProgressBar::chunk {{ border-radius: 4px; background: {color}; }}"
        )

        self.empty_label.setVisible(not self._sets)
        self.clear_btn.setEnabled(bool(self._sets))
        remaining = total - used
        self.add_btn.setEnabled(remaining > 0)
        self.add_btn.setToolTip("" if remaining > 0 else "All bits of this DBS output pin are already mapped.")

    # ------------------------------------------------------------------
    # handlers
    # ------------------------------------------------------------------
    def _on_cols_changed(self, index: int, text: str) -> None:
        if index < len(self._sets):
            self._sets[index][SERIAL_SET_COLS_KEY] = text.strip()
            self._refresh()
            self.changed.emit()

    def _on_related_changed(self, index: int, combo) -> None:
        if index < len(self._sets):
            self._sets[index][SERIAL_SET_RELATED_KEY] = str(combo.currentData() or "")
            self._refresh()
            self.changed.emit()

    def _on_cols_return(self, index: int) -> None:
        if index == len(self._sets) - 1 and self.add_btn.isEnabled():
            self._on_add_set()

    def _on_remove_set(self, index: int) -> None:
        if index < len(self._sets):
            del self._sets[index]
            self._rebuild_rows()
            self.changed.emit()

    def _on_clear_sets(self) -> None:
        if not self._sets:
            return
        answer = QMessageBox.question(
            self, "Clear all sets",
            f"Remove all {len(self._sets)} bit set(s) of {self._pin_name}?",
        )
        if answer == QMessageBox.Yes:
            self._sets = []
            self._rebuild_rows()
            self.changed.emit()

    def _on_add_set(self) -> None:
        computed = compute_serial_set_ranges(self._base_name, self._dbs_bits, self._dbs_lsb, self._sets)
        remaining = self._dbs_bits - computed["used_bits"]
        if remaining <= 0:
            return
        cols = ""
        if self._sets:
            try:
                previous = int(self._sets[-1][SERIAL_SET_COLS_KEY])
            except ValueError:
                previous = 0
            if previous > 0:
                cols = str(min(previous, remaining))
        self._sets.append({SERIAL_SET_COLS_KEY: cols, SERIAL_SET_RELATED_KEY: self._suggest_related()})
        self._rebuild_rows()
        self.changed.emit()
        new_edit = self._rows[-1]["cols_edit"]
        new_edit.setFocus()
        new_edit.selectAll()

    def _suggest_related(self) -> str:
        """직전 선택들의 진행 방향을 이어서, 아직 안 쓴 다음 Related Pin을 고른다."""
        if not self._matched:
            return ""
        used = {item[SERIAL_SET_RELATED_KEY] for item in self._sets}
        picked = [self._matched.index(item[SERIAL_SET_RELATED_KEY])
                  for item in self._sets if item[SERIAL_SET_RELATED_KEY] in self._matched]
        if picked:
            last = picked[-1]
            if len(picked) >= 2 and picked[-2] != last:
                step = 1 if last > picked[-2] else -1
            else:
                # 첫 set가 맨 끝 번호(예: RD_EN_15)였다면 내림차순으로 이어간다.
                step = -1 if last == len(self._matched) - 1 and last > 0 else 1
            nxt = last + step
            while 0 <= nxt < len(self._matched):
                if self._matched[nxt] not in used:
                    return self._matched[nxt]
                nxt += step
        for name in self._matched:
            if name not in used:
                return name
        return ""
