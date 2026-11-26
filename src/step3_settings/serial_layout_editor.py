"""
serial_layout_editor.py

Step 3 - Serial Cluster "More than 1"(Split Serial)에서 인식된 DBS output pin 하나에 대한
입력 위젯 (2026-10 2차 재설계 - "Left / Center / Right" 레이아웃, 사용자 승인 시안 그대로).

    Related Pin (wildcard)  [RD_EN_*                                   ]
    ✓ 16 pin(s) matched: RD_EN_0[13:0], RD_EN_1[13:0], RD_EN_2[13:0], … , RD_EN_15[13:0]
    Cluster size (bit)
    Left [  672 ]   Center (each) [ 1056 ]   Right [ 1024 ]
    ✓ Center: (16480 − 672 − 1024) / 1056 = 14 clusters · Total 16 clusters
       Left            Center (14 × 1056 bit)                    Right
    ┌────┬────┬╌╌╌╌┬╌╌╌╌┬ … ┬────┐
    │ #1 │ #2 │ #3 │ #4 │   │#16 │      ← 칸 폭은 bit 크기에 비례, 입력하는 즉시 다시 그림
    └────┴────┴╌╌╌╌┴╌╌╌╌┴ … ┴────┘
    LSB OUT_ADC[0]                               OUT_ADC[16479] MSB
    Related Pin of cluster #1   ( ) First matched pin (… → ascending)  (•) Last matched pin (… → descending)
    #  Area    Bits  DBS output pin bits      Related Pin
    1  Left    672   OUT_ADC[671:0]           RD_EN_15[13:0]
    …  (앞 3줄 + ⋮ + 뒤 2줄)
    ✓ 16480 / 16480 bits mapped · 16 clusters ↔ 16 Related Pins

2026-11: Related Pin에 '*' 없이 bus 이름(예: 'CSEL')을 쓰면 그 bus를 cluster 개수로 균등
분할해 배정한다(bus 슬라이스 - "✓ Bus CSEL[719:0] (720 bit) / 45 clusters = 16 bit each: …").

계산은 전부 pin_field_defs.compute_serial_layout_for_related(+ compute_serial_set_ranges)이 하고, 이
위젯은 그 결과를 그리기만 한다 - Validate/block5와 같은 함수라 화면과 생성 결과가 어긋날 수
없다. 입력이 바뀔 때마다 changed 시그널을 내고, settings_view가 그 값을 저장용으로 받아 둔다.
"""

from __future__ import annotations

from PyQt5.QtCore import QPoint, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PyQt5.QtWidgets import (
    QButtonGroup, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QRadioButton, QToolTip,
    QVBoxLayout, QWidget,
)

from step3_settings.pin_field_defs import (
    SERIAL_FIRST_PIN_FIRST, SERIAL_FIRST_PIN_LAST, SERIAL_LAYOUT_CENTER_KEY,
    SERIAL_LAYOUT_FIRST_KEY, SERIAL_LAYOUT_LEFT_KEY, SERIAL_LAYOUT_RIGHT_KEY,
    SERIAL_RELATED_MODE_BUS, SERIAL_RELATED_MODE_WILDCARD, compute_serial_layout_for_related,
    compute_serial_set_ranges, normalize_serial_layout,
)
from ui.theme import ERROR_COLOR, MUTED_TEXT_COLOR, SUCCESS_COLOR, TEXT_COLOR, WARNING_TEXT
from ui.ui_common import build_label_with_info

_MATCH_PREVIEW_COUNT = 3
_PREVIEW_HEAD = 3
_PREVIEW_TAIL = 2

_EDGE_FILL = QColor("#E0E7FF")      # Left / Right 칸
_CENTER_FILL = QColor("#F5F6FB")    # Center 칸
_ERROR_FILL = QColor("#FEF2F2")     # 에러일 때 Center 칸
_REMAINDER_FILL = QColor("#FCA5A5") # 나누어떨어지지 않고 남는 bit
_LINE_COLOR = QColor("#9CA3AF")

_WILDCARD_INFO = (
    "Two ways (independent per DBS output pin):\n\n"
    "1) Wildcard - matched against Port==PORT pin names (e.g. 'RD_EN_*'). '*' matches "
    "digits only (a name where '*' would match letters is ignored). Each matched pin is "
    "one cluster's Related Pin.\n\n"
    "2) Bus name without '*' (e.g. 'CSEL' for Port List 'CSEL[719:0]') - the bus is "
    "split evenly by the number of clusters, from its LSB (720 bit / 45 clusters -> "
    "CSEL[15:0], CSEL[31:16], ...). Its Bits must divide evenly.\n\n"
    "A trailing '[13:0]' is display-only and not used for matching. The Related Pins are "
    "assigned to the clusters in order (see 'Related Pin of cluster #1')."
)
_SIZE_INFO = (
    "Left and Right are one cluster each (enter 0 to omit one). Center is the size of "
    "EACH center cluster - they are all the same size. The number of center clusters is "
    "(this pin's Bits - Left - Right) / Center and must divide evenly.\n\n"
    "Cluster #1 is Left and starts at this pin's LSB; Right is the last cluster (MSB). "
    "Each cluster becomes one pin() in block5."
)
_FIRST_INFO = (
    "Which matched pin goes to cluster #1. The other clusters follow automatically: "
    "'First matched pin' assigns the matched pins in ascending order (RD_EN_0, RD_EN_1, "
    "...), 'Last matched pin' in descending order (RD_EN_15, RD_EN_14, ...). The number "
    "of clusters must equal the number of matched pins."
)


def _text_width(metrics: QFontMetrics, text: str) -> int:
    """Qt 5.11+의 horizontalAdvance, 그 이전(사내 Anaconda 3.7의 PyQt5 5.9)은 width."""
    advance = getattr(metrics, "horizontalAdvance", None)
    return advance(text) if advance is not None else metrics.width(text)


class _ClusterBar(QWidget):
    """Left / Center / Right 직사각형 그림. 칸 폭은 bit 크기에 비례, 칸마다 cluster 번호."""

    _TOP = 22
    _HEIGHT = 46

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(self._TOP + self._HEIGHT + 22)
        self.setMouseTracking(True)
        self._clusters: list[dict] = []
        self._remainder = 0
        self._error = False
        self._center_text = ""
        self._lsb_text = ""
        self._msb_text = ""
        self._segments: list[tuple[QRectF, str]] = []

    def set_data(self, clusters: list[dict], remainder: int, error: bool,
                 center_text: str, lsb_text: str, msb_text: str) -> None:
        self._clusters = clusters
        self._remainder = remainder
        self._error = error
        self._center_text = center_text
        self._lsb_text = lsb_text
        self._msb_text = msb_text
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._segments = []
        width = self.width() - 2
        x0, top, height = 1.0, float(self._TOP), float(self._HEIGHT)
        items = [(c["cols"], c["area"], f"#{c['index']}", c) for c in self._clusters]
        if self._remainder:
            # 남는 bit는 Center 영역에 생기므로 Right 칸(있다면) 바로 앞에 그린다.
            leftover = (self._remainder, "Remainder", f"+{self._remainder}", None)
            if items and items[-1][1] == "Right":
                items.insert(len(items) - 1, leftover)
            else:
                items.append(leftover)
        total = sum(cols for cols, *_ in items)

        font = QFont(self.font())
        font.setPointSize(8)
        painter.setFont(font)
        metrics = QFontMetrics(font)

        if not total:
            painter.setPen(QPen(_LINE_COLOR, 1, Qt.DashLine))
            painter.drawRect(QRectF(x0, top, width, height))
            painter.setPen(QColor(MUTED_TEXT_COLOR))
            painter.drawText(QRectF(x0, top, width, height), Qt.AlignCenter,
                             "Enter Left / Center / Right sizes")
            return

        # 칸이 좁으면 번호를 일부만 쓴다(겹치지 않게) - 전부 보려면 마우스를 올린다.
        min_label_px = _text_width(metrics, "#000") + 6
        x = x0
        last_label_right = -1e9
        rects = []
        for cols, area, text, cluster in items:
            seg_w = width * cols / total
            rect = QRectF(x, top, seg_w, height)
            rects.append((rect, area))
            if area == "Remainder":
                fill = _REMAINDER_FILL
            elif area == "Center":
                fill = _ERROR_FILL if self._error else _CENTER_FILL
            else:
                fill = _EDGE_FILL
            painter.fillRect(rect, fill)
            is_edge = area in ("Left", "Right")
            if (seg_w >= min_label_px or is_edge) and rect.left() >= last_label_right:
                painter.setPen(QColor(ERROR_COLOR if area == "Remainder" else TEXT_COLOR))
                painter.drawText(rect, Qt.AlignCenter, text)
                last_label_right = rect.center().x() + _text_width(metrics, text) / 2 + 4
            tip = text if cluster is None else (
                f"Cluster #{cluster['index']} ({area})\n{cluster['cols']} bit · {cluster['label']}"
                + (f"\nRelated Pin: {cluster['related']}" if cluster.get("related") else "")
            )
            if cluster is None:
                tip = f"{cols} bit left over - not divisible by Center"
            self._segments.append((rect, tip))
            x += seg_w

        # 외곽선 + 칸 경계(Left/Right/Remainder 경계는 실선, Center끼리는 점선)
        painter.setPen(QPen(_LINE_COLOR, 1.2))
        painter.drawRect(QRectF(x0, top, width, height))
        for i in range(1, len(rects)):
            rect, area = rects[i]
            prev_area = rects[i - 1][1]
            dashed = area == "Center" and prev_area == "Center"
            painter.setPen(QPen(_LINE_COLOR, 1.0, Qt.DashLine if dashed else Qt.SolidLine))
            painter.drawLine(int(rect.left()), int(top), int(rect.left()), int(top + height))

        # 위쪽 영역 이름
        bold = QFont(font)
        bold.setBold(True)
        painter.setFont(bold)
        painter.setPen(QColor(MUTED_TEXT_COLOR))
        left_rects = [r for r, a in rects if a == "Left"]
        right_rects = [r for r, a in rects if a == "Right"]
        center_rects = [r for r, a in rects if a == "Center"]
        for name, group in (("Left", left_rects), ("Right", right_rects)):
            if group:
                r = group[0]
                painter.drawText(QRectF(r.left() - 20, 0, r.width() + 40, top - 2),
                                 Qt.AlignHCenter | Qt.AlignBottom, name)
        if center_rects:
            c_left, c_right = center_rects[0].left(), center_rects[-1].right()
            painter.drawText(QRectF(c_left, 0, c_right - c_left, top - 2),
                             Qt.AlignHCenter | Qt.AlignBottom, self._center_text)

        # 아래쪽 LSB / MSB
        painter.setFont(font)
        painter.drawText(QRectF(x0, top + height + 3, width / 2, 16), Qt.AlignLeft, self._lsb_text)
        painter.drawText(QRectF(x0 + width / 2, top + height + 3, width / 2, 16), Qt.AlignRight,
                         self._msb_text)

    def mouseMoveEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        for rect, tip in self._segments:
            if rect.contains(event.pos()):
                QToolTip.showText(self.mapToGlobal(event.pos() + QPoint(12, 12)), tip, self)
                return
        QToolTip.hideText()


class SerialLayoutEditor(QWidget):
    """인식된 DBS output pin 하나의 Split Serial 입력(와일드카드 + Left/Center/Right + 시작 pin)."""

    changed = pyqtSignal()

    def __init__(
        self, pin_name: str, base_name: str, dbs_bits: int | None, dbs_lsb: int,
        candidate_pin_names: list[str], pattern: str = "", layout: dict | None = None,
        parent=None, pin_bit_info: dict | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("transparentRow")
        self._pin_name = pin_name
        self._base_name = base_name
        self._dbs_bits = dbs_bits
        self._dbs_lsb = dbs_lsb
        self._candidates_all = list(candidate_pin_names)
        # 2026-11: bus 슬라이스 방식(Related Pin에 '*' 없음)에서 bus의 Bits/LSB를 읽는 데 쓴다
        # (port_list_reader.list_all_pin_bit_info 결과).
        self._pin_bit_info = pin_bit_info or {}
        self._matched: list[str] = []
        layout = normalize_serial_layout(layout)

        self._build(layout)
        self.pattern_edit.blockSignals(True)
        self.pattern_edit.setText(pattern)
        self.pattern_edit.blockSignals(False)
        self._on_pattern_changed(emit=False)

    # ------------------------------------------------------------------
    # public
    # ------------------------------------------------------------------
    @property
    def can_split(self) -> bool:
        return self._dbs_bits is not None and self._dbs_bits > 1

    def pattern(self) -> str:
        return self.pattern_edit.text().strip()

    def layout_value(self) -> dict:
        return {
            SERIAL_LAYOUT_LEFT_KEY: self.left_edit.text().strip(),
            SERIAL_LAYOUT_CENTER_KEY: self.center_edit.text().strip(),
            SERIAL_LAYOUT_RIGHT_KEY: self.right_edit.text().strip(),
            SERIAL_LAYOUT_FIRST_KEY: (
                SERIAL_FIRST_PIN_FIRST if self.first_radio.isChecked() else SERIAL_FIRST_PIN_LAST
            ),
        }

    def required_widgets(self) -> list[QWidget]:
        """Validate 때 비어 있으면 "Must fill"로 표시할 칸들."""
        if not self.can_split:
            return []
        return [self.pattern_edit, self.left_edit, self.center_edit, self.right_edit]

    # ------------------------------------------------------------------
    # layout
    # ------------------------------------------------------------------
    def _build(self, layout: dict) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)

        pattern_row = QHBoxLayout()
        pattern_row.setSpacing(10)
        pattern_row.addWidget(build_label_with_info("Related Pin (wildcard or bus)", _WILDCARD_INFO))
        self.pattern_edit = QLineEdit()
        self.pattern_edit.setPlaceholderText("e.g. RD_EN_*  or  CSEL")
        self.pattern_edit.setEnabled(self.can_split)
        self.pattern_edit.textChanged.connect(lambda _t: self._on_pattern_changed())
        pattern_row.addWidget(self.pattern_edit, stretch=1)
        root.addLayout(pattern_row)

        self.match_label = QLabel("")
        self.match_label.setWordWrap(True)
        root.addWidget(self.match_label)

        self.body = QWidget()
        self.body.setObjectName("transparentRow")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(6)
        root.addWidget(self.body)
        self.body.setVisible(self.can_split)

        body.addWidget(build_label_with_info("Cluster size (bit)", _SIZE_INFO))
        size_row = QHBoxLayout()
        size_row.setSpacing(6)
        self.left_edit = self._size_edit(layout[SERIAL_LAYOUT_LEFT_KEY])
        self.center_edit = self._size_edit(layout[SERIAL_LAYOUT_CENTER_KEY])
        self.right_edit = self._size_edit(layout[SERIAL_LAYOUT_RIGHT_KEY])
        for caption, edit in (("Left", self.left_edit), ("Center (each)", self.center_edit),
                              ("Right", self.right_edit)):
            label = QLabel(caption)
            label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 12px;")
            size_row.addWidget(label)
            size_row.addWidget(edit)
            size_row.addSpacing(10)
        size_row.addStretch()
        body.addLayout(size_row)

        self.size_status = QLabel("")
        self.size_status.setWordWrap(True)
        body.addWidget(self.size_status)

        self.bar = _ClusterBar()
        body.addWidget(self.bar)

        body.addWidget(build_label_with_info("Related Pin of cluster #1", _FIRST_INFO))
        first_row = QHBoxLayout()
        self.first_group = QButtonGroup(self)
        self.first_radio = QRadioButton()
        self.last_radio = QRadioButton()
        self.first_group.addButton(self.first_radio)
        self.first_group.addButton(self.last_radio)
        if layout[SERIAL_LAYOUT_FIRST_KEY] == SERIAL_FIRST_PIN_FIRST:
            self.first_radio.setChecked(True)
        else:
            self.last_radio.setChecked(True)
        self.first_radio.toggled.connect(lambda _c: self._on_value_changed())
        first_row.addWidget(self.first_radio)
        first_row.addWidget(self.last_radio)
        first_row.addStretch()
        body.addLayout(first_row)

        self.preview_host = QWidget()
        self.preview_host.setObjectName("transparentRow")
        self.preview_grid = QGridLayout(self.preview_host)
        self.preview_grid.setContentsMargins(0, 0, 0, 0)
        self.preview_grid.setHorizontalSpacing(14)
        self.preview_grid.setVerticalSpacing(2)
        body.addWidget(self.preview_host)

        self.summary_label = QLabel("")
        self.summary_label.setWordWrap(True)
        body.addWidget(self.summary_label)

    def _size_edit(self, value: str) -> QLineEdit:
        edit = QLineEdit(value)
        edit.setFixedWidth(84)
        edit.setAlignment(Qt.AlignRight)
        edit.setPlaceholderText("bit")
        edit.textChanged.connect(lambda _t: self._on_value_changed())
        return edit

    # ------------------------------------------------------------------
    # handlers
    # ------------------------------------------------------------------
    def _on_pattern_changed(self, emit: bool = True) -> None:
        if not self.can_split:
            self._set_label(
                self.match_label,
                "1 bit - written as a single pin()." if self._dbs_bits == 1
                else "DBS output pin Bits is unknown.",
                MUTED_TEXT_COLOR if self._dbs_bits == 1 else ERROR_COLOR,
            )
            return
        # Related Pin 목록/문구는 cluster 개수에 따라 달라질 수 있으므로(bus 슬라이스) _refresh가
        # 크기 입력과 함께 한 번에 계산한다.
        self._refresh()
        if emit:
            self.changed.emit()

    def _on_value_changed(self) -> None:
        self._refresh()
        self.changed.emit()

    @staticmethod
    def _set_label(label: QLabel, text: str, color: str, bold: bool = False) -> None:
        weight = "font-weight: 600;" if bold else ""
        label.setStyleSheet(f"color: {color}; font-size: 11px; {weight}")
        label.setText(text)

    def _mark_edit(self, edit: QLineEdit, error: str | None) -> None:
        edit.setStyleSheet(
            f"QLineEdit {{ border: 1px solid {ERROR_COLOR}; background: #FEF2F2; }}" if error else ""
        )
        edit.setToolTip(error or "")

    # ------------------------------------------------------------------
    # refresh (값이 바뀔 때마다 - 위젯은 다시 만들지 않는다)
    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        if not self.can_split:
            return
        bits = self._dbs_bits
        layout = self.layout_value()
        computed = compute_serial_layout_for_related(
            self._base_name, bits, self._dbs_lsb, layout, self.pattern(), self._candidates_all,
            self._pin_bit_info,
        )
        self._matched = computed["related_names"]
        self._refresh_match_label(computed)
        fe = computed["field_errors"]
        self._mark_edit(self.left_edit, fe.get(SERIAL_LAYOUT_LEFT_KEY))
        self._mark_edit(self.center_edit, fe.get(SERIAL_LAYOUT_CENTER_KEY))
        self._mark_edit(self.right_edit, fe.get(SERIAL_LAYOUT_RIGHT_KEY))

        # 크기 계산 결과 문구
        clusters = computed["clusters"]
        size_error = next((fe[k] for k in (SERIAL_LAYOUT_LEFT_KEY, SERIAL_LAYOUT_CENTER_KEY,
                                           SERIAL_LAYOUT_RIGHT_KEY) if k in fe), None)
        if size_error:
            self._set_label(self.size_status, f"✕ {size_error}", ERROR_COLOR, bold=True)
        elif not clusters:
            self._set_label(self.size_status, "Enter Left / Center / Right sizes.", MUTED_TEXT_COLOR)
        else:
            left, center, right = (layout[SERIAL_LAYOUT_LEFT_KEY], layout[SERIAL_LAYOUT_CENTER_KEY],
                                   layout[SERIAL_LAYOUT_RIGHT_KEY])
            n = computed["center_count"]
            parts = [f"Left {1 if int(left) > 0 else 0}", f"Center {n}",
                     f"Right {1 if int(right) > 0 else 0}"]
            self._set_label(
                self.size_status,
                f"✓ Center: ({bits} − {left} − {right}) / {center} = {n} clusters   ·   "
                f"Total {len(clusters)} clusters ({' + '.join(parts)})",
                SUCCESS_COLOR, bold=True,
            )

        # 그림
        center_val = layout[SERIAL_LAYOUT_CENTER_KEY]
        center_count = computed["center_count"] or 0
        self.bar.set_data(
            clusters, computed["remainder"], bool(computed["remainder"]),
            f"Center  ({center_count} × {center_val} bit)",
            f"LSB  {self._base_name}[{self._dbs_lsb}]",
            f"{self._base_name}[{self._dbs_lsb + bits - 1}]  MSB",
        )

        # 시작 pin 라디오 문구(매치 목록의 실제 첫/마지막 pin 이름으로)
        if self._matched:
            if computed["related_mode"] == SERIAL_RELATED_MODE_BUS:
                first_name, last_name = self._matched[0], self._matched[-1]
            else:
                first_name = self._matched[0].split("[")[0]
                last_name = self._matched[-1].split("[")[0]
        else:
            first_name, last_name = "first", "last"
        self.first_radio.setText(f"First matched pin  ({first_name} → ascending)")
        self.last_radio.setText(f"Last matched pin  ({last_name} → descending)")

        self._refresh_preview(clusters, computed)

    def _refresh_match_label(self, computed: dict) -> None:
        """Related Pin 입력 바로 아래 문구 - 와일드카드 매치 목록 또는 bus 슬라이스 결과."""
        pattern = self.pattern()
        mode = computed["related_mode"]
        names = computed["related_names"]
        self.match_label.setToolTip("")
        if mode is None:
            self._set_label(self.match_label,
                            "Enter a wildcard (e.g. RD_EN_*) or a bus name (e.g. CSEL).",
                            MUTED_TEXT_COLOR)
            return
        if mode == SERIAL_RELATED_MODE_WILDCARD:
            if not names:
                self._set_label(self.match_label,
                                f"'{pattern}' matched no PORT pins ('*' matches digits only).",
                                ERROR_COLOR)
                return
            if len(names) > _MATCH_PREVIEW_COUNT + 1:
                preview = ", ".join(names[:_MATCH_PREVIEW_COUNT]) + ", … , " + names[-1]
            else:
                preview = ", ".join(names)
            self._set_label(self.match_label, f"✓ {len(names)} pin(s) matched: {preview}",
                            SUCCESS_COLOR)
            self.match_label.setToolTip("\n".join(names))
            return

        bus = computed["related_bus"] or {}
        if computed["related_error"]:
            self._set_label(self.match_label, f"✕ {computed['related_error']}", ERROR_COLOR)
            return
        head = f"Bus {bus.get('full_name')} ({bus.get('bits')} bit)"
        if not names:
            self._set_label(self.match_label,
                            f"✓ {head} - split evenly by the cluster count once the sizes are valid.",
                            SUCCESS_COLOR)
            return
        per = bus["bits"] // len(names)
        if len(names) > _MATCH_PREVIEW_COUNT + 1:
            preview = ", ".join(names[:_MATCH_PREVIEW_COUNT]) + ", … , " + names[-1]
        else:
            preview = ", ".join(names)
        self._set_label(
            self.match_label,
            f"✓ {head} / {len(names)} clusters = {per} bit each: {preview}",
            SUCCESS_COLOR,
        )
        self.match_label.setToolTip("\n".join(names))

    def _refresh_preview(self, clusters: list[dict], computed: dict) -> None:
        while self.preview_grid.count():
            item = self.preview_grid.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

        has_size_error = bool(computed["field_errors"]) or not clusters
        self.preview_host.setVisible(not has_size_error)
        if has_size_error:
            self.summary_label.setText("")
            return

        headers = ("#", "Area", "Bits", "DBS output pin bits", "Related Pin")
        for col, text in enumerate(headers):
            label = QLabel(text)
            label.setStyleSheet(f"color: {MUTED_TEXT_COLOR}; font-size: 11px; font-weight: 600;")
            self.preview_grid.addWidget(label, 0, col)

        if len(clusters) > _PREVIEW_HEAD + _PREVIEW_TAIL + 1:
            shown = clusters[:_PREVIEW_HEAD] + [None] + clusters[-_PREVIEW_TAIL:]
        else:
            shown = clusters
        for row, cluster in enumerate(shown, start=1):
            if cluster is None:
                values = ("⋮", "", "", "", "")
            else:
                values = (str(cluster["index"]), cluster["area"], str(cluster["cols"]),
                          cluster["label"], cluster["related"] or "–")
            for col, value in enumerate(values):
                label = QLabel(value)
                style = f"color: {TEXT_COLOR}; font-size: 12px;"
                if col == 3:
                    style += " font-family: monospace;"
                if col == 4 and cluster is not None and not cluster["related"]:
                    style = f"color: {ERROR_COLOR}; font-size: 12px;"
                label.setStyleSheet(style)
                self.preview_grid.addWidget(label, row, col)
        self.preview_grid.setColumnStretch(len(headers), 1)

        bits = self._dbs_bits
        if computed["errors"]:
            self._set_label(self.summary_label, "✕ " + "  ".join(computed["errors"]), ERROR_COLOR, bold=True)
            return
        ranges = compute_serial_set_ranges(self._base_name, bits, self._dbs_lsb, computed["sets"],
                                           self._matched)
        row_errors = [r["error"] for r in ranges["rows"] if r["error"]]
        if row_errors:
            self._set_label(self.summary_label, "✕ " + row_errors[0], ERROR_COLOR, bold=True)
        elif ranges["used_bits"] != bits:
            self._set_label(self.summary_label,
                            f"{ranges['used_bits']} / {bits} bits mapped", WARNING_TEXT, bold=True)
        else:
            self._set_label(
                self.summary_label,
                f"✓ {bits} / {bits} bits mapped · {len(clusters)} clusters ↔ "
                f"{len(self._matched)} Related Pins",
                SUCCESS_COLOR, bold=True,
            )
