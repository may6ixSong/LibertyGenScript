"""
voltage_map_view.py

Voltage Map 입력 패널 (2026-08: Step 3 -> **Step 2 왼쪽 열**로 이동).

예전에는 BST/WST/TIV 세 그룹이 코드에 고정되어 Step 3 Constants 카드 안에 있었지만,
이제는 **사용자가 voltage condition을 원하는 만큼 추가/삭제하고 이름도 직접 정한다**
(config에 아무것도 없을 때만 기본으로 BST/WST/TIV 세 개가 만들어진다). condition 개수가
많아질 수 있으므로 각 condition 카드는 **접었다 펼 수 있다**(기본은 펼침).

Step 2의 각 liberty setting은 여기서 정의한 condition 중 하나를 이름으로 골라, 생성
단계에서 그 condition의 Power Type1..N 값을 voltage_map으로 쓴다. 그래서 이름을 고치거나
condition을 추가/삭제하면 즉시 on_conditions_changed 콜백으로 Step 2 화면에 알려서
liberty setting의 Condition 드롭다운을 다시 채우게 한다.

Power Type 정책은 기존 유지: 개수는 2~3 사이 조절(기본 3), 대표 전압(0.8V/2.2V/1.8V)은
block4의 Port List Volts 매칭 임계값으로 그대로 쓰이고, Power Type별 voltage name은
condition 구분 없이 Power Type당 하나씩이다.

저장 위치는 예전 그대로 config/step3_settings.json의 voltage_map key다
(step3_settings.settings_manager.load_voltage_map / save_voltage_map).
"""

from __future__ import annotations

from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QFormLayout, QFrame, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QVBoxLayout, QWidget,
)

from step3_settings.constants_field_defs import (
    CONDITION_ID_KEY, CONDITION_NAME_KEY, CONDITION_VALUES_KEY, POWER_TYPE_COUNT_KEY,
    POWER_TYPE_COUNT_MAX, POWER_TYPE_COUNT_MIN, VOLTAGE_CONDITIONS_KEY, condition_value_key,
    new_condition, power_type_count_of, power_type_label, voltage_map_name_key,
)
from ui.theme import MUTED_TEXT_COLOR, TEXT_COLOR
from ui.ui_common import add_shadow, build_hint, build_section_header

_HINT_STYLE = f"color: {MUTED_TEXT_COLOR}; font-size: 11px;"

_VOLTAGE_MAP_INFO = (
    "Add one voltage condition per set of voltage_map values you need, and name it "
    "yourself (BST / WST / TIV are only the defaults).\n\n"
    "Each liberty setting on the right selects one of these conditions, and its "
    "voltage_map values are taken from that condition's Power Type1..N values.\n\n"
    "Enter numeric values only (no unit suffix). Power Type Count can be lowered to 2 "
    "when a project has only two power types; the Power Type3 row is then hidden and "
    "excluded from validation, but any value already entered there is kept."
)

_VOLTAGE_NAME_INFO = (
    "One voltage name per Power Type, shared by every voltage condition.\n\n"
    "It is written as voltage_map (VDD_{name}, {value}) in block2 and must match block4's "
    "pg_pin voltage_name exactly."
)

_COLLAPSED_SYMBOL = "▶"  # ▶
_EXPANDED_SYMBOL = "▼"  # ▼


class _ConditionCard(QFrame):
    """
    voltage condition 하나. 헤더(접기/펴기 버튼 + 이름 입력 + Remove)와 본문(Power
    Type1..N 값 입력)으로 이루어지며, 헤더의 버튼으로 본문을 접었다 펼 수 있다.
    """

    def __init__(
        self,
        condition: dict,
        index: int,
        power_type_count: int,
        on_name_changed: Callable[["_ConditionCard"], None],
        on_remove: Callable[["_ConditionCard"], None],
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("entryCard")
        # 접었을 때 카드가 실제로 헤더 높이까지 줄어들도록 세로로는 필요한 만큼만 쓴다.
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        self.condition_id = condition.get(CONDITION_ID_KEY, "")
        self._on_name_changed = on_name_changed
        self._on_remove = on_remove
        self.value_edits: dict[str, QLineEdit] = {}
        self._value_rows: dict[int, tuple[QLabel, QLineEdit]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)
        layout.addLayout(self._build_header_row(condition, index))
        layout.addWidget(self._build_body(condition))

        self.apply_power_type_count(power_type_count)

    # -- 구성 ---------------------------------------------------------------
    def _build_header_row(self, condition: dict, index: int) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.toggle_btn = QPushButton(_EXPANDED_SYMBOL)
        self.toggle_btn.setFixedWidth(32)
        self.toggle_btn.setStyleSheet("font-size: 14px; padding: 2px 4px;")
        self.toggle_btn.setToolTip("Collapse / expand this voltage condition")
        self.toggle_btn.clicked.connect(self._toggle_body)
        row.addWidget(self.toggle_btn)

        self.index_label = QLabel(f"#{index + 1}")
        self.index_label.setStyleSheet(_HINT_STYLE)
        row.addWidget(self.index_label)

        self.name_edit = QLineEdit(str(condition.get(CONDITION_NAME_KEY, "")))
        self.name_edit.setPlaceholderText("Voltage condition name (e.g. BST)")
        self.name_edit.setStyleSheet(f"color: {TEXT_COLOR}; font-weight: 700;")
        self.name_edit.textChanged.connect(lambda _t: self._on_name_changed(self))
        row.addWidget(self.name_edit, stretch=1)

        self.summary_label = QLabel("")
        self.summary_label.setStyleSheet(_HINT_STYLE)
        row.addWidget(self.summary_label)

        remove_btn = QPushButton("Remove")
        remove_btn.clicked.connect(lambda: self._on_remove(self))
        row.addWidget(remove_btn)
        return row

    def _build_body(self, condition: dict) -> QWidget:
        self.body = QWidget()
        self.body.setObjectName("transparentRow")
        grid = QGridLayout(self.body)
        grid.setContentsMargins(38, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)

        values = condition.get(CONDITION_VALUES_KEY) or {}
        for type_index in range(1, POWER_TYPE_COUNT_MAX + 1):
            key = condition_value_key(type_index)
            row_label = QLabel(f"Type{type_index}")
            row_label.setStyleSheet(_HINT_STYLE)
            row_label.setToolTip(power_type_label(type_index))
            edit = QLineEdit(str(values.get(key, "")))
            edit.setMinimumWidth(60)
            edit.textChanged.connect(lambda _t: self._refresh_summary())
            self.value_edits[key] = edit
            self._value_rows[type_index] = (row_label, edit)
            column = (type_index - 1) * 2
            grid.addWidget(row_label, 0, column)
            grid.addWidget(edit, 0, column + 1)
            grid.setColumnStretch(column + 1, 1)
        return self.body

    # -- 동작 ---------------------------------------------------------------
    def _toggle_body(self) -> None:
        self.set_expanded(not self.body.isVisible())

    def set_expanded(self, expanded: bool) -> None:
        self.body.setVisible(expanded)
        self.toggle_btn.setText(_EXPANDED_SYMBOL if expanded else _COLLAPSED_SYMBOL)
        self._refresh_summary()

    def is_expanded(self) -> bool:
        return self.body.isVisible()

    def set_index(self, index: int) -> None:
        self.index_label.setText(f"#{index + 1}")

    def apply_power_type_count(self, count: int) -> None:
        """Power Type 개수에 따라 Type3 입력칸을 보이거나 숨긴다(값 자체는 유지)."""
        for type_index, (row_label, edit) in self._value_rows.items():
            visible = type_index <= count
            row_label.setVisible(visible)
            edit.setVisible(visible)
        self._power_type_count = count
        self._refresh_summary()

    def _refresh_summary(self) -> None:
        """접었을 때도 값이 보이도록 헤더 오른쪽에 짧은 요약을 띄운다."""
        count = getattr(self, "_power_type_count", POWER_TYPE_COUNT_MAX)
        values = [
            self.value_edits[condition_value_key(i)].text().strip() or "-"
            for i in range(1, count + 1)
        ]
        self.summary_label.setText(" / ".join(values) if not self.is_expanded() else "")

    def collect(self) -> dict:
        return {
            CONDITION_ID_KEY: self.condition_id,
            CONDITION_NAME_KEY: self.name_edit.text().strip(),
            CONDITION_VALUES_KEY: {
                key: edit.text().strip() for key, edit in self.value_edits.items()
            },
        }


class VoltageMapPanel(QWidget):
    """
    Voltage Map 카드 전체 (Power Type Count + Power Type별 voltage name + condition 목록).

    Args:
        voltage_map: settings_manager.load_voltage_map() 결과
        on_conditions_changed: condition 목록/이름이 바뀔 때마다 호출되는 콜백. Step 2가
            이걸 받아 liberty setting의 Condition 드롭다운을 다시 채운다. 이름이 바뀐
            경우에는 ("직전 이름", "새 이름") 튜플이 함께 넘어가서, 그 이름을 고르고
            있던 setting의 선택이 새 이름으로 따라갈 수 있다.
    """

    def __init__(
        self, voltage_map: dict,
        on_conditions_changed: Callable[[tuple], None] | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.on_conditions_changed = on_conditions_changed
        self.condition_cards: list[_ConditionCard] = []
        self.name_edits: dict[str, QLineEdit] = {}
        self._known_names: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_card(voltage_map))

        self._rebuild_condition_cards(voltage_map.get(VOLTAGE_CONDITIONS_KEY) or [])

    # ------------------------------------------------------------------
    # 레이아웃
    # ------------------------------------------------------------------
    def _build_card(self, voltage_map: dict) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        add_shadow(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        header.addWidget(build_section_header("Voltage Map", _VOLTAGE_MAP_INFO))
        header.addStretch()
        header.addWidget(QLabel("Power Type Count"))
        self.power_type_count_spin = QSpinBox()
        self.power_type_count_spin.setRange(POWER_TYPE_COUNT_MIN, POWER_TYPE_COUNT_MAX)
        self.power_type_count_spin.setValue(power_type_count_of(voltage_map))
        self.power_type_count_spin.valueChanged.connect(self._on_power_type_count_changed)
        header.addWidget(self.power_type_count_spin)
        layout.addLayout(header)

        layout.addWidget(self._build_voltage_name_frame(voltage_map.get("names", {}) or {}))

        conditions_header = QHBoxLayout()
        conditions_header.addWidget(build_section_header("Voltage Conditions"))
        conditions_header.addStretch()
        self.conditions_summary_label = QLabel("")
        self.conditions_summary_label.setStyleSheet(_HINT_STYLE)
        conditions_header.addWidget(self.conditions_summary_label)
        self.collapse_all_btn = QPushButton("Collapse all")
        self.collapse_all_btn.clicked.connect(self._on_toggle_all)
        conditions_header.addWidget(self.collapse_all_btn)
        add_btn = QPushButton("+ Add Voltage Condition")
        add_btn.clicked.connect(self._on_add_condition)
        conditions_header.addWidget(add_btn)
        layout.addLayout(conditions_header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        container = QWidget()
        container.setObjectName("transparentRow")
        self.conditions_layout = QVBoxLayout(container)
        self.conditions_layout.setContentsMargins(0, 0, 6, 0)
        self.conditions_layout.setSpacing(8)
        self.conditions_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll, stretch=1)

        self.conditions_empty_label = build_hint(
            "No voltage condition yet. Click '+ Add Voltage Condition' - each liberty "
            "setting picks one of them."
        )
        layout.addWidget(self.conditions_empty_label)
        return card

    def _build_voltage_name_frame(self, saved_names: dict) -> QFrame:
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)
        layout.addWidget(build_section_header("Voltage Name", _VOLTAGE_NAME_INFO))

        form = QFormLayout()
        form.setSpacing(6)
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self._name_rows: dict[int, tuple[QLabel, QLineEdit]] = {}
        for type_index in range(1, POWER_TYPE_COUNT_MAX + 1):
            key = voltage_map_name_key(type_index)
            edit = QLineEdit(str(saved_names.get(key, "")))
            self.name_edits[key] = edit
            row_label = QLabel(power_type_label(type_index))
            form.addRow(row_label, edit)
            self._name_rows[type_index] = (row_label, edit)
        layout.addLayout(form)
        return frame

    # ------------------------------------------------------------------
    # condition 카드 관리
    # ------------------------------------------------------------------
    def _rebuild_condition_cards(self, conditions: list[dict]) -> None:
        expanded_state = {card.condition_id: card.is_expanded() for card in self.condition_cards}
        # condition 이름이 바뀌었을 때 "어떤 이름이 어떤 이름으로 바뀌었는지" 알려면
        # 직전 이름을 id별로 들고 있어야 한다 (_on_condition_name_changed 참고).
        self._known_names = {
            str(c.get(CONDITION_ID_KEY, "")): str(c.get(CONDITION_NAME_KEY, "")).strip()
            for c in conditions
        }
        for card in self.condition_cards:
            self.conditions_layout.removeWidget(card)
            card.deleteLater()
        self.condition_cards = []

        count = self.power_type_count_spin.value()
        for index, condition in enumerate(conditions):
            card = _ConditionCard(
                condition, index, count, self._on_condition_name_changed, self._on_remove_condition,
            )
            card.set_expanded(expanded_state.get(card.condition_id, True))
            self.conditions_layout.insertWidget(self.conditions_layout.count() - 1, card)
            self.condition_cards.append(card)

        self._refresh_conditions_summary()
        self._notify_conditions_changed()

    def _refresh_conditions_summary(self) -> None:
        count = len(self.condition_cards)
        self.conditions_summary_label.setText(f"{count} voltage condition(s)")
        self.conditions_empty_label.setVisible(count == 0)
        for index, card in enumerate(self.condition_cards):
            card.set_index(index)

    def _on_add_condition(self) -> None:
        conditions = self._collect_conditions()
        conditions.append(new_condition())
        self._rebuild_condition_cards(conditions)

    def _on_remove_condition(self, card: _ConditionCard) -> None:
        conditions = [
            c for c in self._collect_conditions() if c.get(CONDITION_ID_KEY) != card.condition_id
        ]
        self._rebuild_condition_cards(conditions)

    def _on_condition_name_changed(self, card: "_ConditionCard") -> None:
        """
        이름이 바뀌면 "직전 이름 -> 새 이름"을 함께 알려서, 그 이름을 고르고 있던
        liberty setting의 선택이 끊기지 않고 새 이름으로 따라가게 한다.
        """
        old_name = self._known_names.get(card.condition_id, "")
        new_name = card.name_edit.text().strip()
        self._known_names[card.condition_id] = new_name
        rename = (old_name, new_name) if old_name and old_name != new_name else None
        self._notify_conditions_changed(rename)

    def _on_toggle_all(self) -> None:
        collapse = any(card.is_expanded() for card in self.condition_cards)
        for card in self.condition_cards:
            card.set_expanded(not collapse)
        self.collapse_all_btn.setText("Expand all" if collapse else "Collapse all")

    def _on_power_type_count_changed(self, value: int) -> None:
        for type_index, (row_label, edit) in self._name_rows.items():
            visible = type_index <= value
            row_label.setVisible(visible)
            edit.setVisible(visible)
        for card in self.condition_cards:
            card.apply_power_type_count(value)

    def _notify_conditions_changed(self, rename: tuple[str, str] | None = None) -> None:
        if self.on_conditions_changed:
            self.on_conditions_changed(rename)

    # ------------------------------------------------------------------
    # 값 읽기
    # ------------------------------------------------------------------
    def _collect_conditions(self) -> list[dict]:
        return [card.collect() for card in self.condition_cards]

    def collect(self) -> dict:
        return {
            POWER_TYPE_COUNT_KEY: self.power_type_count_spin.value(),
            VOLTAGE_CONDITIONS_KEY: self._collect_conditions(),
            "names": {key: edit.text().strip() for key, edit in self.name_edits.items()},
        }

    def condition_names(self) -> list[str]:
        """지금 화면에 입력돼 있는 condition 이름 목록 (빈 이름 제외, 순서 유지)."""
        names = []
        for card in self.condition_cards:
            name = card.name_edit.text().strip()
            if name:
                names.append(name)
        return names

    def showEvent(self, event) -> None:  # noqa: N802 - Qt 오버라이드 시그니처
        super().showEvent(event)
        self._on_power_type_count_changed(self.power_type_count_spin.value())
